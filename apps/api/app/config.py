from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
