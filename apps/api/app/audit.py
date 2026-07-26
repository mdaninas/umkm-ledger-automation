import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import ActorType, AuditEvent


def record_audit_event(
    session: Session,
    *,
    business_id: uuid.UUID,
    actor_type: ActorType,
    actor_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    correlation_id: str,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        business_id=business_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        correlation_id=correlation_id,
        event_metadata=metadata or {},
    )
    session.add(event)
    return event
