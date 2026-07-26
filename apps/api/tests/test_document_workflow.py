import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.extraction import ExtractionSchemaError, MockExtractionProvider
from app.models import JournalEntry
from app.workflow import process_document

PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF"


def _login(client: TestClient, settings: Settings, *, owner: bool = True) -> str:
    email = settings.demo_owner_email if owner else settings.demo_staff_email
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": settings.demo_owner_password},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def _upload(
    client: TestClient,
    token: str,
    *,
    content: bytes = PDF,
    filename: str = "receipt.pdf",
    key: str | None = None,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    if key:
        headers["Idempotency-Key"] = key
    response = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": (filename, content, "application/pdf")},
    )
    assert response.status_code in {200, 202}
    return response.json()


def _process(client: TestClient, settings: Settings, document_id: str) -> None:
    with client.app.state.database.session_factory() as session:
        process_document(
            session,
            document_id=uuid.UUID(document_id),
            storage=client.app.state.storage,
            provider=MockExtractionProvider(settings),
            settings=settings,
        )


def test_document_happy_path_is_reviewed_balanced_and_posted_once(
    client: TestClient,
    settings: Settings,
) -> None:
    token = _login(client, settings)
    uploaded = _upload(client, token, key="upload-happy-001")
    assert uploaded["status"] == "QUEUED"
    _process(client, settings, uploaded["id"])

    detail = client.get(
        f"/api/v1/documents/{uploaded['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail.status_code == 200
    document = detail.json()
    assert document["status"] == "NEEDS_REVIEW"
    assert document["latest_extraction"]["provider"] == "mock"
    assert document["journal"]["balanced"] is True
    assert document["journal"]["total_debit"] == "350000.00"
    assert document["approval"]["status"] == "PENDING"
    assert len(document["audit_timeline"]) >= 6

    before_post = client.get(
        "/api/v1/dashboard/summary",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert before_post["posted_journal_count"] == 0
    assert before_post["posted_expenses"] == "0.00"

    account_id = document["proposed_account"]["id"]
    review = client.post(
        f"/api/v1/documents/{uploaded['id']}/review",
        headers={"Authorization": f"Bearer {token}"},
        json={"final_account_id": account_id, "review_comment": "Checked against receipt."},
    )
    assert review.status_code == 200
    assert review.json()["status"] == "READY_TO_POST"

    staff_token = _login(client, settings, owner=False)
    staff_post = client.post(
        f"/api/v1/documents/{uploaded['id']}/post",
        headers={
            "Authorization": f"Bearer {staff_token}",
            "Idempotency-Key": "post-staff-0001",
        },
        json={"comment": "Staff cannot approve"},
    )
    assert staff_post.status_code == 403

    with client.app.state.database.session_factory() as session:
        journal = session.scalar(
            select(JournalEntry).where(
                JournalEntry.document_id == uuid.UUID(uploaded["id"])
            )
        )
        assert journal is not None
        journal.lines[1].credit = 1
        session.commit()

    rejected = client.post(
        f"/api/v1/documents/{uploaded['id']}/post",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "post-happy-001",
        },
        json={"comment": "Approve"},
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == "Journal is not balanced."

    with client.app.state.database.session_factory() as session:
        journal = session.scalar(
            select(JournalEntry).where(
                JournalEntry.document_id == uuid.UUID(uploaded["id"])
            )
        )
        assert journal is not None
        journal.lines[1].credit = journal.lines[0].debit
        session.commit()

    first_post = client.post(
        f"/api/v1/documents/{uploaded['id']}/post",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "post-happy-001",
        },
        json={"comment": "Approved"},
    )
    repeated_post = client.post(
        f"/api/v1/documents/{uploaded['id']}/post",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "post-happy-001",
        },
        json={"comment": "Repeated safely"},
    )
    assert first_post.status_code == repeated_post.status_code == 200
    assert first_post.json()["journal"]["id"] == repeated_post.json()["journal"]["id"]
    assert repeated_post.json()["status"] == "POSTED"

    after_post = client.get(
        "/api/v1/dashboard/summary",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert after_post["posted_journal_count"] == 1
    assert after_post["draft_journal_count"] == 0
    assert after_post["posted_expenses"] == "350000.00"


def test_exact_and_semantic_duplicates_stop_before_journal(
    client: TestClient,
    settings: Settings,
) -> None:
    token = _login(client, settings)
    original = _upload(client, token, key="upload-original-001")
    repeated_upload = _upload(
        client,
        token,
        content=PDF + b"\nignored because request is idempotent",
        key="upload-original-001",
    )
    assert repeated_upload["id"] == original["id"]
    _process(client, settings, original["id"])

    exact = _upload(client, token, key="upload-exact-0001")
    _process(client, settings, exact["id"])
    exact_detail = client.get(
        f"/api/v1/documents/{exact['id']}",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert exact_detail["duplicate_reason"] == "EXACT_FILE"
    assert exact_detail["duplicate_of_id"] == original["id"]
    assert exact_detail["journal"] is None

    semantic = _upload(
        client,
        token,
        content=PDF + b"\n% distinct scan",
        filename="different-scan.pdf",
        key="upload-semantic-01",
    )
    _process(client, settings, semantic["id"])
    semantic_detail = client.get(
        f"/api/v1/documents/{semantic['id']}",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert semantic_detail["duplicate_reason"] == "SEMANTIC_FIELDS"
    assert semantic_detail["duplicate_of_id"] == original["id"]
    assert semantic_detail["journal"] is None


def test_invalid_schema_marks_document_failed(
    client: TestClient,
    settings: Settings,
) -> None:
    class InvalidProvider:
        def extract(self, **_: object) -> Any:
            raise ExtractionSchemaError("bad schema")

    token = _login(client, settings)
    uploaded = _upload(client, token, key="upload-invalid-01")
    with (
        client.app.state.database.session_factory() as session,
        pytest.raises(ExtractionSchemaError),
    ):
        process_document(
            session,
            document_id=uuid.UUID(uploaded["id"]),
            storage=client.app.state.storage,
            provider=InvalidProvider(),
            settings=settings,
        )

    detail = client.get(
        f"/api/v1/documents/{uploaded['id']}",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert detail["status"] == "FAILED"
    assert detail["error_code"] == "AI_SCHEMA_INVALID"
    assert detail["journal"] is None


def test_upload_validates_signature_and_tenant_scope(
    client: TestClient,
    settings: Settings,
) -> None:
    owner_token = _login(client, settings)
    invalid = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {owner_token}"},
        files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
    )
    assert invalid.status_code == 415

    missing = client.get(
        f"/api/v1/documents/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert missing.status_code == 404
