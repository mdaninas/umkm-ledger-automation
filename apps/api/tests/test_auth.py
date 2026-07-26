import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import Settings
from app.models import AuditEvent, Business, LedgerAccount, Membership, User
from app.security import create_access_token
from app.seed import seed_demo


def test_demo_owner_can_login_and_read_tenant_profile(
    client: TestClient,
    settings: Settings,
) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": settings.demo_owner_email, "password": settings.demo_owner_password},
        headers={"X-Correlation-ID": "test-login-owner"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["business"]["name"] == "Kopi Arunika"
    assert payload["business"]["currency"] == "IDR"
    assert payload["role"] == "owner"
    assert payload["access_token"]
    assert response.headers["X-Correlation-ID"] == "test-login-owner"

    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["user"]["email"] == settings.demo_owner_email

    with client.app.state.database.session_factory() as session:
        audit = session.scalar(
            select(AuditEvent).where(
                AuditEvent.business_id == uuid.UUID(payload["business"]["id"]),
                AuditEvent.action == "auth.login.succeeded",
            )
        )
        assert audit is not None
        assert audit.correlation_id == "test-login-owner"


def test_login_rejects_invalid_password(client: TestClient, settings: Settings) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": settings.demo_owner_email, "password": "WrongPass123!"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Email atau password tidak cocok."


def test_protected_endpoint_requires_token(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_signed_token_cannot_cross_tenant(client: TestClient, settings: Settings) -> None:
    with client.app.state.database.session_factory() as session:
        user = session.scalar(select(User).where(User.email == settings.demo_owner_email))
        assert user is not None
        token, _ = create_access_token(
            user_id=user.id,
            business_id=uuid.uuid4(),
            settings=settings,
        )

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Akses bisnis tidak ditemukan."


def test_seed_is_idempotent(client: TestClient, settings: Settings) -> None:
    with client.app.state.database.session_factory() as session:
        seed_demo(session, settings)
        seed_demo(session, settings)
        assert session.scalar(select(func.count()).select_from(Business)) == 1
        assert session.scalar(select(func.count()).select_from(User)) == 2
        assert session.scalar(select(func.count()).select_from(Membership)) == 2
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1
        assert session.scalar(select(func.count()).select_from(LedgerAccount)) == 13
