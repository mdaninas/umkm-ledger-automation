import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.bank_demo import seed_bank_demo
from app.bank_service import score_document_candidate
from app.config import Settings
from app.finance import normalize_vendor_name
from app.models import (
    ActorType,
    AuditEvent,
    BankDirection,
    BankTransaction,
    Document,
    DocumentSource,
    DocumentStatus,
    DocumentType,
    JournalEntry,
    Reconciliation,
    ReconciliationStatus,
)
from app.seed import DEMO_OWNER_ID


def _login(client: TestClient, settings: Settings) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": settings.demo_owner_email,
            "password": settings.demo_owner_password,
        },
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def _create_source(
    client: TestClient,
    *,
    vendor: str,
    document_number: str,
    transaction_date: date,
    total: Decimal,
    document_type: DocumentType = DocumentType.RECEIPT,
) -> uuid.UUID:
    document_id = uuid.uuid4()
    with client.app.state.database.session_factory() as session:
        session.add(
            Document(
                id=document_id,
                business_id=uuid.UUID("d8f899b6-6dd9-4a91-82fe-d97e8076c9cf"),
                source=DocumentSource.DEMO,
                original_filename=f"{document_number}.pdf",
                mime_type="application/pdf",
                storage_key=f"demo/{document_id}.pdf",
                sha256=uuid.uuid4().hex + uuid.uuid4().hex,
                status=DocumentStatus.POSTED,
                document_type=document_type,
                document_number=document_number,
                vendor_name=vendor,
                normalized_vendor_name=normalize_vendor_name(vendor),
                transaction_date=transaction_date,
                currency="IDR",
                total=total,
                payment_method="BANK_TRANSFER",
                created_by=DEMO_OWNER_ID,
                reviewed_by=DEMO_OWNER_ID,
            )
        )
        session.commit()
    return document_id


def _upload_csv(
    client: TestClient,
    token: str,
    content: bytes,
    *,
    filename: str = "mutasi.csv",
) -> Any:
    return client.post(
        "/api/v1/bank-imports",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (filename, content, "text/csv")},
        data={
            "mapping": (
                '{"date":"tanggal","description":"deskripsi","debit":"debit",'
                '"credit":"kredit","reference":"referensi"}'
            )
        },
    )


def test_csv_import_is_deduplicated_and_routes_transactions_by_score(
    client: TestClient,
    settings: Settings,
) -> None:
    token = _login(client, settings)
    auto_source_id = _create_source(
        client,
        vendor="CV Biji Nusantara",
        document_number="RCT-2026-0725-001",
        transaction_date=date(2026, 7, 25),
        total=Decimal("350000.00"),
    )
    suggested_source_id = _create_source(
        client,
        vendor="PT Sinar Kemasan",
        document_number="INV-2026-0720-008",
        transaction_date=date(2026, 7, 18),
        total=Decimal("825000.00"),
        document_type=DocumentType.SUPPLIER_INVOICE,
    )
    content = (
        b"tanggal,deskripsi,debit,kredit,referensi\n"
        b"2026-07-25,CV Biji Nusantara RCT-2026-0725-001,350000,,"
        b"RCT-2026-0725-001\n"
        b"2026-07-20,Sinar Packaging,825000,,\n"
        b"2026-07-22,Transfer tanpa dokumen,1200000,,OPS-0722\n"
        b"tanggal-rusak,Baris rusak,75000,,ERR-001\n"
    )

    imported = _upload_csv(client, token, content)
    assert imported.status_code == 201
    summary = imported.json()
    assert summary["row_count"] == 4
    assert summary["imported_count"] == 3
    assert summary["duplicate_count"] == 0
    assert summary["error_count"] == 1
    assert summary["row_errors"][0]["row"] == 5
    assert summary["status"] == "COMPLETED_WITH_ERRORS"

    transactions_response = client.get(
        "/api/v1/bank-transactions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert transactions_response.status_code == 200
    transactions = transactions_response.json()
    assert transactions["counts"] == {
        "total": 3,
        "unmatched": 1,
        "suggested": 1,
        "matched": 1,
    }
    by_amount = {item["amount"]: item for item in transactions["items"]}

    auto_matched = by_amount["350000.00"]
    assert auto_matched["status"] == "AUTO_MATCHED"
    assert auto_matched["candidates"][0]["source"]["id"] == str(auto_source_id)
    assert Decimal(auto_matched["candidates"][0]["score"]) >= Decimal("90")
    assert (
        auto_matched["candidates"][0]["score_breakdown"]["amount"]["score"]
        == "50"
    )
    assert (
        auto_matched["candidates"][0]["score_breakdown"]["policy"][
            "auto_match_eligible"
        ]
        is True
    )

    suggested = by_amount["825000.00"]
    assert suggested["status"] == "SUGGESTED"
    assert suggested["candidates"][0]["source"]["id"] == str(suggested_source_id)
    assert Decimal("70") <= Decimal(suggested["candidates"][0]["score"]) < Decimal(
        "90"
    )
    assert by_amount["1200000.00"]["status"] == "UNMATCHED"
    assert by_amount["1200000.00"]["candidates"] == []

    repeated = _upload_csv(client, token, content)
    assert repeated.status_code == 200
    assert repeated.json()["id"] == summary["id"]
    assert repeated.json()["duplicate_file"] is True
    after_repeat = client.get(
        "/api/v1/bank-transactions",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert after_repeat["counts"]["total"] == 3
    imports = client.get(
        "/api/v1/bank-imports",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert imports["total"] == 1


def test_manual_decisions_are_audited_and_active_matches_are_unique(
    client: TestClient,
    settings: Settings,
) -> None:
    token = _login(client, settings)
    first_source = _create_source(
        client,
        vendor="UD Toko Kertas",
        document_number="DOC-A",
        transaction_date=date(2026, 7, 15),
        total=Decimal("500000.00"),
    )
    second_source = _create_source(
        client,
        vendor="Toko Kertas Nusantara",
        document_number="DOC-B",
        transaction_date=date(2026, 7, 15),
        total=Decimal("500000.00"),
    )
    content = (
        b"tanggal,deskripsi,debit,kredit,referensi\n"
        b"2026-07-15,Toko Kertas,500000,,\n"
    )
    imported = _upload_csv(client, token, content, filename="ambiguous.csv")
    assert imported.status_code == 201
    transactions = client.get(
        "/api/v1/bank-transactions",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["items"]
    assert len(transactions) == 1
    assert transactions[0]["status"] == "SUGGESTED"
    candidates = transactions[0]["candidates"]
    assert {item["source"]["id"] for item in candidates} == {
        str(first_source),
        str(second_source),
    }
    assert candidates[0]["score_breakdown"]["policy"]["conflicts"]

    confirmed_id = candidates[0]["id"]
    confirmed = client.post(
        f"/api/v1/reconciliations/{confirmed_id}/confirm",
        headers={"Authorization": f"Bearer {token}"},
        json={"comment": "Nominal dan bukti transfer sudah diperiksa."},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "CONFIRMED"

    repeated_confirm = client.post(
        f"/api/v1/reconciliations/{confirmed_id}/confirm",
        headers={"Authorization": f"Bearer {token}"},
        json={"comment": "Permintaan yang sama."},
    )
    assert repeated_confirm.status_code == 200
    other_candidate_id = candidates[1]["id"]
    conflicting = client.post(
        f"/api/v1/reconciliations/{other_candidate_id}/confirm",
        headers={"Authorization": f"Bearer {token}"},
        json={"comment": "Tidak boleh menggandakan match."},
    )
    assert conflicting.status_code == 409

    with client.app.state.database.session_factory() as session:
        active_count = session.scalar(
            select(func.count())
            .select_from(Reconciliation)
            .where(
                Reconciliation.bank_transaction_id
                == uuid.UUID(transactions[0]["id"]),
                Reconciliation.status.in_(
                    [
                        ReconciliationStatus.AUTO_MATCHED,
                        ReconciliationStatus.CONFIRMED,
                    ]
                ),
            )
        )
        assert active_count == 1
        audit = session.scalar(
            select(AuditEvent).where(
                AuditEvent.entity_id == uuid.UUID(confirmed_id),
                AuditEvent.action == "reconciliation.confirmed",
                AuditEvent.actor_type == ActorType.USER,
            )
        )
        assert audit is not None


def test_reject_keeps_transaction_unmatched_and_records_audit(
    client: TestClient,
    settings: Settings,
) -> None:
    token = _login(client, settings)
    _create_source(
        client,
        vendor="PT Sinar Kemasan",
        document_number="INV-REJECT",
        transaction_date=date(2026, 7, 18),
        total=Decimal("825000.00"),
    )
    content = (
        b"tanggal,deskripsi,debit,kredit,referensi\n"
        b"2026-07-20,Sinar Packaging,825000,,\n"
    )
    assert _upload_csv(client, token, content, filename="reject.csv").status_code == 201
    transaction = client.get(
        "/api/v1/bank-transactions",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["items"][0]
    candidate_id = transaction["candidates"][0]["id"]
    rejected = client.post(
        f"/api/v1/reconciliations/{candidate_id}/reject",
        headers={"Authorization": f"Bearer {token}"},
        json={"comment": "Deskripsi bank bukan untuk invoice ini."},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    refreshed = client.get(
        "/api/v1/bank-transactions",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["items"][0]
    assert refreshed["status"] == "UNMATCHED"
    with client.app.state.database.session_factory() as session:
        audit = session.scalar(
            select(AuditEvent).where(
                AuditEvent.entity_id == uuid.UUID(candidate_id),
                AuditEvent.action == "reconciliation.rejected",
            )
        )
        assert audit is not None


def test_golden_scoring_covers_exact_drift_alias_ambiguous_and_no_match() -> None:
    source = Document(
        id=uuid.uuid4(),
        business_id=uuid.uuid4(),
        source=DocumentSource.DEMO,
        original_filename="source.pdf",
        mime_type="application/pdf",
        storage_key="demo/source.pdf",
        sha256="a" * 64,
        status=DocumentStatus.POSTED,
        document_type=DocumentType.RECEIPT,
        document_number="RCT-2026-0725-001",
        vendor_name="CV Biji Nusantara",
        normalized_vendor_name="biji nusantara",
        transaction_date=date(2026, 7, 25),
        currency="IDR",
        total=Decimal("350000.00"),
        created_by=uuid.uuid4(),
    )

    def transaction(
        *,
        description: str,
        transaction_date: date,
        amount: Decimal,
        reference: str | None = None,
    ) -> BankTransaction:
        return BankTransaction(
            id=uuid.uuid4(),
            business_id=source.business_id,
            bank_import_id=uuid.uuid4(),
            row_number=2,
            external_fingerprint=uuid.uuid4().hex + uuid.uuid4().hex,
            transaction_date=transaction_date,
            description=description,
            amount=amount,
            direction=BankDirection.DEBIT,
            reference=reference,
        )

    exact = score_document_candidate(
        transaction(
            description="CV Biji Nusantara",
            transaction_date=date(2026, 7, 25),
            amount=Decimal("350000.00"),
            reference="RCT-2026-0725-001",
        ),
        source,
    )
    date_drift = score_document_candidate(
        transaction(
            description="CV Biji Nusantara",
            transaction_date=date(2026, 7, 27),
            amount=Decimal("350000.00"),
        ),
        source,
    )
    vendor_alias = score_document_candidate(
        transaction(
            description="Biji Nusantara Coffee",
            transaction_date=date(2026, 7, 25),
            amount=Decimal("350000.00"),
        ),
        source,
    )
    ambiguous = score_document_candidate(
        transaction(
            description="Nusantara",
            transaction_date=date(2026, 7, 28),
            amount=Decimal("350000.00"),
        ),
        source,
    )
    no_match = score_document_candidate(
        transaction(
            description="Vendor lain",
            transaction_date=date(2026, 6, 1),
            amount=Decimal("990000.00"),
        ),
        source,
    )

    assert exact.score >= Decimal("90")
    assert date_drift.score >= Decimal("70")
    assert vendor_alias.breakdown["vendor"]["score"] == "18"
    assert Decimal("70") <= ambiguous.score < Decimal("90")
    assert no_match.score < Decimal("70")

    high_confidence_cases = [
        score_document_candidate(
            transaction(
                description=f"CV Biji Nusantara cabang {index}",
                transaction_date=date(2026, 7, 25),
                amount=Decimal("350000.00"),
                reference="RCT-2026-0725-001",
            ),
            source,
        )
        for index in range(20)
    ]
    true_high_confidence = sum(
        candidate.score >= Decimal("90") for candidate in high_confidence_cases
    )
    precision = Decimal(true_high_confidence) / Decimal(len(high_confidence_cases))
    assert precision >= Decimal("0.95")


def test_bank_demo_seed_is_repeatable_on_a_clean_database(
    client: TestClient,
    settings: Settings,
) -> None:
    with client.app.state.database.session_factory() as session:
        first = seed_bank_demo(
            session,
            settings=settings,
            storage=client.app.state.storage,
        )
        second = seed_bank_demo(
            session,
            settings=settings,
            storage=client.app.state.storage,
        )
        assert [document.id for document in first] == [
            document.id for document in second
        ]
        journal_count = session.scalar(
            select(func.count()).select_from(JournalEntry)
        )
        assert journal_count == 2
