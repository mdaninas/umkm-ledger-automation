import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import Settings
from app.invoice_demo import seed_invoice_demo
from app.invoice_service import business_local_date, dispatch_outbox_message
from app.models import (
    ApprovalRequest,
    AuditEvent,
    Business,
    InvoiceReminder,
    OutboxMessage,
    OutboxStatus,
    ReminderStatus,
)


def _login(client: TestClient, settings: Settings, *, owner: bool = True) -> str:
    email = settings.demo_owner_email if owner else settings.demo_staff_email
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": settings.demo_owner_password},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def _seed(client: TestClient) -> None:
    with client.app.state.database.session_factory() as session:
        invoices = seed_invoice_demo(session)
        assert len(invoices) == 3


def _run_scheduler(
    client: TestClient,
    token: str,
    *,
    fallback: bool = False,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/invoices/scheduler/run",
        headers={"Authorization": f"Bearer {token}"},
        json={"as_of": "2026-07-31", "force_fallback": fallback},
    )
    assert response.status_code == 200
    return response.json()


def _overdue_invoice(client: TestClient, token: str) -> dict[str, Any]:
    response = client.get(
        "/api/v1/invoices?status=OVERDUE",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    detail = client.get(
        f"/api/v1/invoices/{items[0]['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail.status_code == 200
    return detail.json()


def test_scheduler_uses_business_timezone_and_builds_accurate_draft(
    client: TestClient,
    settings: Settings,
) -> None:
    _seed(client)
    token = _login(client, settings)
    with client.app.state.database.session_factory() as session:
        business = session.scalar(select(Business))
        assert business is not None
        assert business_local_date(
            business,
            now=datetime(2026, 7, 30, 17, 30, tzinfo=UTC),
        ).isoformat() == "2026-07-31"

    result = _run_scheduler(client, token)
    assert result == {
        "as_of": "2026-07-31",
        "businesses_scanned": 1,
        "invoices_scanned": 3,
        "status_updates": 2,
        "drafts_created": 1,
        "fallback_drafts": 0,
    }
    invoice = _overdue_invoice(client, token)
    assert invoice["invoice_number"] == "INV-2026-0730-001"
    assert invoice["status"] == "OVERDUE"
    assert invoice["days_until_due"] <= 0
    reminder = invoice["reminders"][0]
    assert reminder["status"] == "PENDING_APPROVAL"
    assert reminder["source"] == "AI_ASSISTED"
    assert "INV-2026-0730-001" in reminder["body"]
    assert "IDR 2.450.000" in reminder["body"]
    assert "30 Juli 2026" in reminder["body"]
    assert reminder["approval_status"] == "PENDING"
    assert reminder["outbox"] is None

    repeated = _run_scheduler(client, token)
    assert repeated["drafts_created"] == 0
    assert repeated["status_updates"] == 0


def test_deterministic_fallback_is_used_when_copy_provider_fails(
    client: TestClient,
    settings: Settings,
) -> None:
    _seed(client)
    token = _login(client, settings)
    result = _run_scheduler(client, token, fallback=True)
    assert result["fallback_drafts"] == 1
    reminder = _overdue_invoice(client, token)["reminders"][0]
    assert reminder["source"] == "DETERMINISTIC_FALLBACK"
    assert "Semoga Bapak/Ibu dalam keadaan baik." in reminder["body"]
    assert "IDR 2.450.000" in reminder["body"]


def test_approval_creates_one_outbox_and_retry_sends_once(
    client: TestClient,
    settings: Settings,
) -> None:
    _seed(client)
    owner_token = _login(client, settings)
    staff_token = _login(client, settings, owner=False)
    _run_scheduler(client, owner_token)
    reminder = _overdue_invoice(client, owner_token)["reminders"][0]
    reminder_id = reminder["id"]
    headers = {
        "Authorization": f"Bearer {owner_token}",
        "Idempotency-Key": f"approve-reminder-{reminder_id}",
    }

    staff_attempt = client.post(
        f"/api/v1/invoice-reminders/{reminder_id}/approve",
        headers={
            "Authorization": f"Bearer {staff_token}",
            "Idempotency-Key": f"approve-reminder-{reminder_id}",
        },
        json={"comment": "Staff approval"},
    )
    assert staff_attempt.status_code == 403

    with client.app.state.database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(OutboxMessage)) == 0

    approved = client.post(
        f"/api/v1/invoice-reminders/{reminder_id}/approve",
        headers=headers,
        json={"comment": "Nominal dan penerima sudah benar."},
    )
    assert approved.status_code == 200
    approved_reminder = approved.json()["reminders"][0]
    assert approved_reminder["status"] == "QUEUED"
    assert approved_reminder["outbox"]["status"] == "PENDING"
    outbox_id = approved_reminder["outbox"]["id"]

    repeated = client.post(
        f"/api/v1/invoice-reminders/{reminder_id}/approve",
        headers=headers,
        json={"comment": "Retry request"},
    )
    assert repeated.status_code == 200
    with client.app.state.database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(OutboxMessage)) == 1

    different_key = client.post(
        f"/api/v1/invoice-reminders/{reminder_id}/approve",
        headers={
            "Authorization": f"Bearer {owner_token}",
            "Idempotency-Key": f"different-approval-{reminder_id}",
        },
        json={"comment": "Second decision"},
    )
    assert different_key.status_code == 409

    sent_messages: list[str] = []

    def fake_sender(outbox: OutboxMessage, _: Settings) -> None:
        sent_messages.append(str(outbox.id))

    with client.app.state.database.session_factory() as session:
        first = dispatch_outbox_message(
            session,
            outbox_id=uuid.UUID(outbox_id),
            settings=settings,
            sender=fake_sender,
        )
        assert first.status == OutboxStatus.SENT
        second = dispatch_outbox_message(
            session,
            outbox_id=uuid.UUID(outbox_id),
            settings=settings,
            sender=fake_sender,
        )
        assert second.status == OutboxStatus.SENT
        assert sent_messages == [outbox_id]
        reminder_model = session.get(InvoiceReminder, uuid.UUID(reminder_id))
        assert reminder_model is not None
        assert reminder_model.status == ReminderStatus.SENT
        actions = set(
            session.scalars(
                select(AuditEvent.action).where(
                    AuditEvent.entity_id == uuid.UUID(reminder_id)
                )
            )
        )
        assert {
            "invoice.reminder_drafted",
            "invoice.reminder_approved",
            "invoice.reminder_sent",
        } <= actions


def test_cooldown_and_rejection_are_enforced(
    client: TestClient,
    settings: Settings,
) -> None:
    _seed(client)
    token = _login(client, settings)
    _run_scheduler(client, token)
    invoice = _overdue_invoice(client, token)
    reminder = invoice["reminders"][0]

    rejected = client.post(
        f"/api/v1/invoice-reminders/{reminder['id']}/reject",
        headers={"Authorization": f"Bearer {token}"},
        json={"comment": "Pelanggan meminta penundaan."},
    )
    assert rejected.status_code == 200
    assert rejected.json()["reminders"][0]["status"] == "REJECTED"
    with client.app.state.database.session_factory() as session:
        approval = session.scalar(
            select(ApprovalRequest).where(
                ApprovalRequest.entity_id == uuid.UUID(reminder["id"])
            )
        )
        assert approval is not None
        assert approval.status.value == "REJECTED"
        assert session.scalar(select(func.count()).select_from(OutboxMessage)) == 0

    blocked = client.post(
        f"/api/v1/invoices/{invoice['id']}/reminder-draft",
        headers={"Authorization": f"Bearer {token}"},
        json={"force_fallback": False},
    )
    assert blocked.status_code == 409
    assert "cooldown" in blocked.json()["detail"].lower()

    with client.app.state.database.session_factory() as session:
        reminder_model = session.get(InvoiceReminder, uuid.UUID(reminder["id"]))
        assert reminder_model is not None
        reminder_model.created_at = datetime.now(UTC) - timedelta(
            days=settings.reminder_cooldown_days + 1
        )
        session.commit()

    after_cooldown = client.post(
        f"/api/v1/invoices/{invoice['id']}/reminder-draft",
        headers={"Authorization": f"Bearer {token}"},
        json={"force_fallback": False},
    )
    assert after_cooldown.status_code == 200
    assert after_cooldown.json()["sequence"] == 2


def test_invoice_demo_seed_is_idempotent(
    client: TestClient,
) -> None:
    _seed(client)
    _seed(client)
    with client.app.state.database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(InvoiceReminder)) == 0
        from app.models import Customer, Invoice

        assert session.scalar(select(func.count()).select_from(Customer)) == 3
        assert session.scalar(select(func.count()).select_from(Invoice)) == 3
