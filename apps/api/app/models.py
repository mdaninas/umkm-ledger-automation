import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Role(StrEnum):
    OWNER = "owner"
    STAFF = "staff"


class ActorType(StrEnum):
    USER = "user"
    SYSTEM = "system"


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Jakarta")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="IDR")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    memberships: Mapped[list["Membership"]] = relationship(back_populates="business")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user")


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "business_id", name="uq_membership"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[Role] = mapped_column(
        Enum(Role, native_enum=False, length=16), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="memberships")
    business: Mapped[Business] = relationship(back_populates="memberships")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    actor_type: Mapped[ActorType] = mapped_column(
        Enum(ActorType, native_enum=False, length=16), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
