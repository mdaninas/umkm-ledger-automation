import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.config import Settings, get_settings
from app.database import Database
from app.models import ActorType, Business, Membership, Role, User
from app.security import hash_password

DEMO_BUSINESS_ID = uuid.UUID("d8f899b6-6dd9-4a91-82fe-d97e8076c9cf")
DEMO_OWNER_ID = uuid.UUID("fa55cc88-2e70-4cc4-a24b-7525915ca5e2")
DEMO_STAFF_ID = uuid.UUID("bb5f827b-714b-4b1e-bf37-804762085029")


def seed_demo(session: Session, settings: Settings) -> Business:
    business = session.get(Business, DEMO_BUSINESS_ID)
    created = business is None
    if business is None:
        business = Business(
            id=DEMO_BUSINESS_ID,
            name="Kopi Arunika",
            timezone="Asia/Jakarta",
            currency="IDR",
        )
        session.add(business)
        session.flush()

    _ensure_demo_user(
        session,
        user_id=DEMO_OWNER_ID,
        email=settings.demo_owner_email,
        password=settings.demo_owner_password,
        display_name="Ayu Arunika",
        business=business,
        role=Role.OWNER,
    )
    _ensure_demo_user(
        session,
        user_id=DEMO_STAFF_ID,
        email=settings.demo_staff_email,
        password=settings.demo_staff_password,
        display_name="Bima Admin",
        business=business,
        role=Role.STAFF,
    )

    if created:
        record_audit_event(
            session,
            business_id=business.id,
            actor_type=ActorType.SYSTEM,
            actor_id=None,
            action="demo.seeded",
            entity_type="business",
            entity_id=business.id,
            correlation_id="seed-kopi-arunika",
            metadata={"synthetic_data": True},
        )

    session.commit()
    return business


def _ensure_demo_user(
    session: Session,
    *,
    user_id: uuid.UUID,
    email: str,
    password: str,
    display_name: str,
    business: Business,
    role: Role,
) -> None:
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            id=user_id,
            email=email,
            password_hash=hash_password(password),
            display_name=display_name,
        )
        session.add(user)

    membership = session.scalar(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.business_id == business.id,
        )
    )
    if membership is None:
        session.add(Membership(user=user, business=business, role=role))


def main() -> None:
    settings = get_settings()
    database = Database(settings.database_url)
    try:
        with database.session_factory() as session:
            business = seed_demo(session, settings)
            print(f"Seed siap: {business.name} ({business.id})")
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
