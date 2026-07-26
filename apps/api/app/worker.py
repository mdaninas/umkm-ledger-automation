from celery import Celery  # type: ignore[import-untyped]

from app.config import get_settings

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
