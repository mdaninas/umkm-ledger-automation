import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, banking, documents, finance, invoices
from app.api import health as health_routes
from app.config import Settings, get_settings
from app.database import Database
from app.models import Base
from app.observability import configure_logging
from app.storage import build_storage

logger = logging.getLogger("app.http")


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = Database(app_settings.database_url)
        app.state.database = database
        app.state.storage = build_storage(app_settings)
        if app_settings.environment.lower() == "test":
            Base.metadata.create_all(database.engine)
        try:
            yield
        finally:
            database.dispose()

    application = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        description="Document intake, review, approval, and ledger API for UMKM finance.",
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[app_settings.web_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "X-Correlation-ID",
        ],
        expose_headers=["X-Correlation-ID"],
    )

    @application.middleware("http")
    async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000)
        response.headers["X-Correlation-ID"] = correlation_id
        logger.info(
            "request.completed",
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    @application.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "request.failed",
            extra={"correlation_id": getattr(request.state, "correlation_id", "unknown")},
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Terjadi kesalahan internal. Coba lagi atau hubungi administrator.",
                "correlation_id": getattr(request.state, "correlation_id", None),
            },
        )

    application.include_router(health_routes.router, prefix="/health")
    application.include_router(
        health_routes.router,
        prefix=f"{app_settings.api_v1_prefix}/health",
    )
    application.include_router(auth.router, prefix=app_settings.api_v1_prefix)
    application.include_router(documents.router, prefix=app_settings.api_v1_prefix)
    application.include_router(finance.router, prefix=app_settings.api_v1_prefix)
    application.include_router(banking.router, prefix=app_settings.api_v1_prefix)
    application.include_router(invoices.router, prefix=app_settings.api_v1_prefix)

    @application.get("/")
    def root() -> dict[str, str]:
        return {
            "name": app_settings.app_name,
            "docs": "/docs",
            "health": "/api/v1/health",
        }

    return application


app = create_app()
