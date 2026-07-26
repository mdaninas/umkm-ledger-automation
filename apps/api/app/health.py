import time
from collections.abc import Callable
from typing import Any

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from redis import Redis
from sqlalchemy import text

from app.config import Settings
from app.database import Database
from app.schemas import HealthComponent
from app.worker import celery_app


def _timed_probe(probe: Callable[[], Any]) -> HealthComponent:
    started = time.perf_counter()
    try:
        probe()
    except Exception:
        return HealthComponent(
            status="unhealthy",
            latency_ms=round((time.perf_counter() - started) * 1000),
            detail="Layanan tidak dapat dijangkau.",
        )
    return HealthComponent(
        status="healthy",
        latency_ms=round((time.perf_counter() - started) * 1000),
    )


def probe_components(settings: Settings, database: Database) -> dict[str, HealthComponent]:
    components = {
        "api": HealthComponent(status="healthy", latency_ms=0),
        "database": _timed_probe(
            lambda: _probe_database(database),
        ),
    }

    if not settings.healthcheck_externals:
        skipped = HealthComponent(status="skipped", detail="Dinonaktifkan untuk test.")
        components.update(
            {
                "redis": skipped,
                "object_storage": skipped,
                "worker": skipped,
            }
        )
        return components

    components["redis"] = _timed_probe(
        lambda: Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=settings.healthcheck_timeout_seconds,
            socket_timeout=settings.healthcheck_timeout_seconds,
        ).ping()
    )
    components["object_storage"] = _timed_probe(lambda: _probe_storage(settings))
    components["worker"] = _timed_probe(lambda: _probe_worker(settings))
    return components


def _probe_database(database: Database) -> None:
    with database.engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def _probe_storage(settings: Settings) -> None:
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=Config(
            connect_timeout=settings.healthcheck_timeout_seconds,
            read_timeout=settings.healthcheck_timeout_seconds,
            retries={"max_attempts": 0},
        ),
    )
    client.head_bucket(Bucket=settings.s3_bucket)


def _probe_worker(settings: Settings) -> None:
    inspector = celery_app.control.inspect(timeout=settings.healthcheck_timeout_seconds)
    replies = inspector.ping()
    if not replies:
        raise RuntimeError("worker tidak merespons")
