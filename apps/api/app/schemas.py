import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import Role


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class BusinessSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    timezone: str
    currency: str


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    display_name: str


class SessionProfile(BaseModel):
    user: UserSummary
    business: BusinessSummary
    role: Role


class TokenResponse(SessionProfile):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class HealthComponent(BaseModel):
    status: str
    latency_ms: int | None = None
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str
    timestamp: datetime
    components: dict[str, HealthComponent]
