from decimal import Decimal
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

CHAOS_ALLOWED_ENVIRONMENTS = frozenset({"development", "demo", "test"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "UMKM Finance Autopilot API"
    environment: str = "development"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    web_origin: str = "http://localhost:3000"

    database_url: str = "sqlite+pysqlite:///./umkm_finance.db"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "umkm_minio"
    s3_secret_key: str = "umkm_minio_password"
    s3_bucket: str = "umkm-documents"
    s3_region: str = "us-east-1"

    max_upload_bytes: int = 10 * 1024 * 1024
    amount_tolerance: Decimal = Decimal("1.00")
    max_future_days: int = 7
    minimum_extraction_confidence: Decimal = Decimal("0.75")
    enqueue_document_tasks: bool = True
    reconciliation_auto_match_threshold: Decimal = Decimal("90")
    reconciliation_review_threshold: Decimal = Decimal("70")
    reconciliation_ambiguity_margin: Decimal = Decimal("10")
    reminder_due_soon_days: int = Field(default=7, ge=1, le=30)
    reminder_cooldown_days: int = Field(default=7, ge=1, le=90)
    reminder_scheduler_hour: int = Field(default=8, ge=0, le=23)
    weekly_digest_scheduler_hour: int = Field(default=7, ge=0, le=23)

    smtp_host: str = "localhost"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_from_email: str = "finance@kopiarunika.demo"
    smtp_timeout_seconds: float = Field(default=5.0, gt=0, le=30)

    ai_provider: str = "mock"
    ai_http_endpoint: str | None = None
    ai_http_api_key: str | None = None
    ai_http_model: str = "finance-document-extractor"
    extraction_prompt_version: str = "finance-inbox-v1"
    extraction_schema_version: str = "document-v1"
    chaos_mode_enabled: bool = True
    document_max_retries: int = Field(default=3, ge=0, le=8)

    jwt_secret: str = "change-this-local-demo-secret-at-least-32-chars"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    demo_owner_email: str = "owner@kopiarunika.demo"
    demo_owner_password: str = "Demo123!"
    demo_staff_email: str = "staff@kopiarunika.demo"
    demo_staff_password: str = "Demo123!"

    healthcheck_externals: bool = True
    healthcheck_timeout_seconds: float = Field(default=1.0, gt=0, le=5)

    @model_validator(mode="after")
    def reject_demo_secret_in_production(self) -> "Settings":
        if (
            self.environment.lower() == "production"
            and self.jwt_secret == "change-this-local-demo-secret-at-least-32-chars"
        ):
            raise ValueError("JWT_SECRET wajib diganti pada environment production")
        if (
            self.chaos_mode_enabled
            and self.environment.lower() not in CHAOS_ALLOWED_ENVIRONMENTS
        ):
            raise ValueError(
                "CHAOS_MODE_ENABLED hanya boleh true pada development, demo, atau test"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
