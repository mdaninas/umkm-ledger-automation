import uuid

from celery import Celery  # type: ignore[import-untyped]
from sqlalchemy import select

from app.config import get_settings
from app.database import Database
from app.extraction import ExtractionSchemaError, build_extraction_provider
from app.models import WorkflowRun, WorkflowStatus
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


@celery_app.task(name="health.ping")
def ping() -> dict[str, str]:
    return {"status": "ok"}


@celery_app.task(
    bind=True,
    name="documents.process",
    max_retries=3,
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
        is_dead_letter = retry_number > self.max_retries
        with database.session_factory() as retry_session:
            run = retry_session.scalar(
                select(WorkflowRun).where(
                    WorkflowRun.id == uuid.UUID(workflow_run_id)
                )
            )
            if run:
                run.retry_count = retry_number
                run.status = (
                    WorkflowStatus.DEAD_LETTER
                    if is_dead_letter
                    else WorkflowStatus.RETRY_SCHEDULED
                )
                retry_session.commit()
        if is_dead_letter:
            raise
        raise self.retry(
            exc=exc,
            countdown=min(60, 2**retry_number),
        ) from exc
    finally:
        database.dispose()
