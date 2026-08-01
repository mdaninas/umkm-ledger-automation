import uuid

from celery import Celery  # type: ignore[import-untyped]
from celery.schedules import crontab  # type: ignore[import-untyped]
from sqlalchemy import select

from app.config import get_settings
from app.database import Database
from app.eval_service import execute_evaluation_run
from app.extraction import ExtractionSchemaError, build_extraction_provider
from app.invoice_service import dispatch_outbox_message, scan_invoices
from app.models import Business
from app.reliability import schedule_retry
from app.report_service import generate_weekly_digest
from app.storage import build_storage
from app.workflow import process_document

settings = get_settings()

celery_app = Celery(
    "umkm_finance_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Jakarta",
    enable_utc=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
)
celery_app.conf.beat_schedule = {
    "scan-overdue-invoices-daily": {
        "task": "invoices.scan_overdue",
        "schedule": crontab(
            hour=settings.reminder_scheduler_hour,
            minute=0,
        ),
    },
    "generate-weekly-digests": {
        "task": "reports.generate_weekly_digest",
        "schedule": crontab(
            day_of_week="monday",
            hour=settings.weekly_digest_scheduler_hour,
            minute=0,
        ),
    },
}


@celery_app.task(name="health.ping")
def ping() -> dict[str, str]:
    return {"status": "ok"}


@celery_app.task(name="evals.run")
def run_evaluation_task(run_id: str) -> dict[str, str]:
    database = Database(settings.database_url)
    try:
        with database.session_factory() as session:
            run = execute_evaluation_run(
                session,
                run_id=uuid.UUID(run_id),
                settings=settings,
            )
            return {"run_id": run_id, "status": run.status.value}
    finally:
        database.dispose()


@celery_app.task(
    bind=True,
    name="documents.process",
    max_retries=None,
)
def process_document_task(
    self,  # type: ignore[no-untyped-def]
    document_id: str,
    workflow_run_id: str,
) -> dict[str, str]:
    database = Database(settings.database_url)
    storage = build_storage(settings)
    provider = build_extraction_provider(settings)
    try:
        with database.session_factory() as session:
            try:
                document = process_document(
                    session,
                    document_id=uuid.UUID(document_id),
                    workflow_run_id=uuid.UUID(workflow_run_id),
                    storage=storage,
                    provider=provider,
                    settings=settings,
                )
            except ExtractionSchemaError:
                return {"document_id": document_id, "status": "FAILED"}
            return {"document_id": document_id, "status": document.status.value}
    except Exception as exc:
        retry_number = self.request.retries + 1
        with database.session_factory() as retry_session:
            _, delay, is_dead_letter = schedule_retry(
                retry_session,
                run_id=uuid.UUID(workflow_run_id),
                retry_number=retry_number,
                max_retries=settings.document_max_retries,
            )
        if is_dead_letter:
            raise
        raise self.retry(
            exc=exc,
            countdown=delay,
            max_retries=settings.document_max_retries,
        ) from exc
    finally:
        database.dispose()


@celery_app.task(
    bind=True,
    name="outbox.dispatch",
    max_retries=3,
)
def dispatch_outbox_task(
    self,  # type: ignore[no-untyped-def]
    outbox_id: str,
) -> dict[str, str]:
    database = Database(settings.database_url)
    try:
        with database.session_factory() as session:
            try:
                outbox = dispatch_outbox_message(
                    session,
                    outbox_id=uuid.UUID(outbox_id),
                    settings=settings,
                    correlation_id=f"outbox-{outbox_id}",
                )
            except Exception as exc:
                raise self.retry(
                    exc=exc,
                    countdown=min(300, 2 ** (self.request.retries + 1) * 10),
                ) from exc
            return {"outbox_id": outbox_id, "status": outbox.status.value}
    finally:
        database.dispose()


@celery_app.task(name="invoices.scan_overdue")
def scan_overdue_invoices_task() -> dict[str, str | int]:
    database = Database(settings.database_url)
    try:
        with database.session_factory() as session:
            result = scan_invoices(
                session,
                settings=settings,
                correlation_id=f"scheduler-{uuid.uuid4()}",
            )
            return {
                "as_of": result["as_of"].isoformat(),
                "businesses_scanned": result["businesses_scanned"],
                "invoices_scanned": result["invoices_scanned"],
                "status_updates": result["status_updates"],
                "drafts_created": result["drafts_created"],
            }
    finally:
        database.dispose()


@celery_app.task(name="reports.generate_weekly_digest")
def generate_weekly_digest_task() -> dict[str, int]:
    database = Database(settings.database_url)
    generated = 0
    try:
        with database.session_factory() as session:
            businesses = list(session.scalars(select(Business).order_by(Business.id)))
            for business in businesses:
                generate_weekly_digest(
                    session,
                    business=business,
                    correlation_id=f"weekly-digest-{business.id}-{uuid.uuid4()}",
                )
                generated += 1
        return {"businesses_processed": generated}
    finally:
        database.dispose()
