import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.config import Settings
from app.invoice_demo import seed_invoice_demo
from app.models import (
    ActorType,
    AuditEvent,
    BankDirection,
    BankImport,
    BankImportStatus,
    BankTransaction,
    BankTransactionStatus,
    Document,
    DocumentExtraction,
    DocumentSource,
    DocumentStatus,
    DocumentType,
    JournalEntry,
    JournalLine,
    JournalStatus,
    LedgerAccount,
    WeeklyDigest,
    WorkflowRun,
    WorkflowStatus,
)
from app.report_demo import REPORT_ENTRIES, seed_report_demo
from app.seed import DEMO_BUSINESS_ID, DEMO_OWNER_ID


def _owner_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@kopiarunika.demo", "password": "Demo123!"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _account(session: Session, code: str) -> LedgerAccount:
    account = session.scalar(
        select(LedgerAccount).where(
            LedgerAccount.business_id == DEMO_BUSINESS_ID,
            LedgerAccount.code == code,
        )
    )
    assert account is not None
    return account


def _add_journal(
    session: Session,
    *,
    entry_date: date,
    amount: Decimal,
    account_code: str,
    status: JournalStatus = JournalStatus.POSTED,
) -> tuple[Document, JournalEntry]:
    document_id = uuid.uuid4()
    document = Document(
        id=document_id,
        business_id=DEMO_BUSINESS_ID,
        source=DocumentSource.DEMO,
        original_filename=f"report-{document_id}.pdf",
        mime_type="application/pdf",
        storage_key=f"reports/{document_id}.pdf",
        sha256=uuid.uuid4().hex * 2,
        upload_idempotency_key=f"report-{document_id}",
        status=DocumentStatus.POSTED,
        document_type=(
            DocumentType.CUSTOMER_INVOICE
            if account_code == "4000"
            else DocumentType.RECEIPT
        ),
        document_number=f"RPT-{str(document_id)[:8]}",
        vendor_name="Fixture Laporan",
        transaction_date=entry_date,
        currency="IDR",
        subtotal=amount,
        tax=Decimal("0"),
        total=amount,
        extraction_confidence=Decimal("1"),
        created_by=DEMO_OWNER_ID,
        reviewed_by=DEMO_OWNER_ID,
        reviewed_at=datetime.combine(entry_date, datetime.min.time(), tzinfo=UTC),
    )
    session.add(document)
    session.flush()
    bank = _account(session, "1010")
    category = _account(session, account_code)
    journal = JournalEntry(
        business_id=DEMO_BUSINESS_ID,
        document_id=document.id,
        status=status,
        entry_date=entry_date,
        description=f"Fixture {account_code}",
        posted_at=(
            datetime.combine(entry_date, datetime.min.time(), tzinfo=UTC)
            if status == JournalStatus.POSTED
            else None
        ),
        posted_by=DEMO_OWNER_ID if status == JournalStatus.POSTED else None,
    )
    if account_code == "4000":
        journal.lines.extend(
            [
                JournalLine(
                    ledger_account_id=bank.id,
                    debit=amount,
                    credit=Decimal("0"),
                ),
                JournalLine(
                    ledger_account_id=category.id,
                    debit=Decimal("0"),
                    credit=amount,
                ),
            ]
        )
    else:
        journal.lines.extend(
            [
                JournalLine(
                    ledger_account_id=category.id,
                    debit=amount,
                    credit=Decimal("0"),
                ),
                JournalLine(
                    ledger_account_id=bank.id,
                    debit=Decimal("0"),
                    credit=amount,
                ),
            ]
        )
    session.add(journal)
    session.flush()
    return document, journal


def _seed_report_fixture(client: TestClient) -> None:
    with client.app.state.database.session_factory() as session:
        income_document, _ = _add_journal(
            session,
            entry_date=date(2026, 7, 10),
            amount=Decimal("1000000"),
            account_code="4000",
        )
        _add_journal(
            session,
            entry_date=date(2026, 7, 11),
            amount=Decimal("300000"),
            account_code="6100",
        )
        _add_journal(
            session,
            entry_date=date(2026, 6, 15),
            amount=Decimal("200000"),
            account_code="6100",
        )
        _add_journal(
            session,
            entry_date=date(2026, 7, 12),
            amount=Decimal("500000"),
            account_code="6900",
            status=JournalStatus.DRAFT,
        )
        session.add(
            DocumentExtraction(
                document_id=income_document.id,
                provider="mock",
                model="report-fixture",
                prompt_version="v1",
                schema_version="v1",
                raw_structured_output={},
                normalized_output={},
                field_confidences={},
                warnings=[],
                latency_ms=1200,
                usage={"estimated_cost_idr": "4200.00"},
                created_at=datetime(2026, 7, 10, 1, tzinfo=UTC),
            )
        )
        for index, workflow_status in enumerate(
            [
                WorkflowStatus.SUCCEEDED,
                WorkflowStatus.SUCCEEDED,
                WorkflowStatus.FAILED,
            ]
        ):
            started = datetime(2026, 7, 10 + index, 2, tzinfo=UTC)
            session.add(
                WorkflowRun(
                    business_id=DEMO_BUSINESS_ID,
                    workflow_type="DOCUMENT_INGESTION",
                    entity_type="DOCUMENT",
                    entity_id=income_document.id,
                    status=workflow_status,
                    correlation_id=f"report-workflow-{index}",
                    started_at=started,
                    finished_at=started + timedelta(seconds=10 + index * 5),
                    retry_count=2 if workflow_status == WorkflowStatus.FAILED else 0,
                    error_code=(
                        "DEMO_FAILURE"
                        if workflow_status == WorkflowStatus.FAILED
                        else None
                    ),
                    created_at=started,
                )
            )
        bank_import = BankImport(
            business_id=DEMO_BUSINESS_ID,
            filename="report-fixture.csv",
            sha256="b" * 64,
            column_mapping={"date": "date", "amount": "amount"},
            status=BankImportStatus.COMPLETED,
            row_count=2,
            imported_count=2,
            duplicate_count=0,
            error_count=0,
            row_errors=[],
            created_by=DEMO_OWNER_ID,
        )
        session.add(bank_import)
        session.flush()
        session.add_all(
            [
                BankTransaction(
                    business_id=DEMO_BUSINESS_ID,
                    bank_import_id=bank_import.id,
                    row_number=1,
                    external_fingerprint="c" * 64,
                    transaction_date=date(2026, 7, 10),
                    description="Pembayaran pelanggan",
                    amount=Decimal("1000000"),
                    direction=BankDirection.CREDIT,
                    status=BankTransactionStatus.CONFIRMED,
                ),
                BankTransaction(
                    business_id=DEMO_BUSINESS_ID,
                    bank_import_id=bank_import.id,
                    row_number=2,
                    external_fingerprint="d" * 64,
                    transaction_date=date(2026, 7, 1),
                    description="Mutasi tanpa dokumen",
                    amount=Decimal("125000"),
                    direction=BankDirection.DEBIT,
                    status=BankTransactionStatus.UNMATCHED,
                ),
            ]
        )
        seed_invoice_demo(session)
        session.commit()


def test_dashboard_reconciles_posted_ledger_and_period_filter(client: TestClient) -> None:
    _seed_report_fixture(client)
    response = client.get(
        "/api/v1/reports/dashboard?start_date=2026-07-01&end_date=2026-07-31",
        headers=_owner_headers(client),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["overview"]["income"] == "1000000.00"
    assert payload["overview"]["expenses"] == "300000.00"
    assert payload["overview"]["net_cash_flow"] == "700000.00"
    assert payload["overview"]["bank_balance"] == "500000.00"
    assert payload["ledger_source_count"] == 2
    assert len(payload["cashflow"]) == 31
    assert payload["cashflow"][-1]["closing_balance"] == "500000.00"
    assert payload["expense_breakdown"][0]["account_code"] == "6100"
    assert payload["expense_breakdown"][0]["share_percent"] == "100.00"


def test_dashboard_exposes_actionable_alerts_and_operational_metrics(
    client: TestClient,
) -> None:
    _seed_report_fixture(client)
    response = client.get(
        "/api/v1/reports/dashboard?start_date=2026-07-01&end_date=2026-07-31",
        headers=_owner_headers(client),
    )
    payload = response.json()
    alert_types = {alert["alert_type"] for alert in payload["alerts"]}
    assert "EXPENSE_SPIKE" in alert_types
    assert "OVERDUE_INVOICE" in alert_types
    assert "UNMATCHED_BANK_TRANSACTION" in alert_types
    assert all(alert["source_url"].startswith("/") for alert in payload["alerts"])
    assert all(alert["rule"] for alert in payload["alerts"])
    assert payload["automation"] == {
        "total_workflows": 3,
        "succeeded": 2,
        "failed": 1,
        "waiting_review": 0,
        "retry_count": 2,
        "automation_rate_percent": "66.67",
        "median_latency_seconds": "15.00",
        "estimated_ai_cost_idr": "4200.00",
    }
    assert payload["reconciliation"]["total_transactions"] == 2
    assert payload["reconciliation"]["matched_transactions"] == 1
    assert payload["reconciliation"]["match_rate_percent"] == "50.00"


def test_weekly_digest_is_idempotent_and_audited(client: TestClient) -> None:
    _seed_report_fixture(client)
    headers = _owner_headers(client)
    first = client.post(
        "/api/v1/reports/weekly-digests/run",
        headers=headers,
        json={"period_end": "2026-07-12"},
    )
    second = client.post(
        "/api/v1/reports/weekly-digests/run",
        headers=headers,
        json={"period_end": "2026-07-12"},
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert "pendapatan tercatat IDR 1.000.000" in first.json()["narrative"]
    assert first.json()["source_refs"][0]["type"] == "ledger"
    with client.app.state.database.session_factory() as session:
        assert session.scalar(select(WeeklyDigest)) is not None
        events = list(
            session.scalars(
                select(AuditEvent).where(
                    AuditEvent.action == "report.weekly_digest.generated"
                )
            )
        )
        assert len(events) == 1
        assert events[0].actor_type == ActorType.SYSTEM


def test_report_csv_matches_filter_and_excludes_drafts(client: TestClient) -> None:
    _seed_report_fixture(client)
    response = client.get(
        "/api/v1/reports/export.csv?start_date=2026-07-01&end_date=2026-07-31",
        headers=_owner_headers(client),
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "laporan-2026-07-01-2026-07-31.csv" in response.headers[
        "content-disposition"
    ]
    assert response.text.startswith("\ufefftanggal,journal_id")
    assert "Fixture 4000" in response.text
    assert "Fixture 6100" in response.text
    assert "Fixture 6900" not in response.text


def test_reports_are_authenticated_and_validate_period(client: TestClient) -> None:
    assert client.get("/api/v1/reports/dashboard").status_code == 401
    response = client.get(
        "/api/v1/reports/dashboard?start_date=2026-08-01&end_date=2026-07-01",
        headers=_owner_headers(client),
    )
    assert response.status_code == 422
    assert "Tanggal mulai" in response.json()["detail"]


def test_report_demo_seed_is_idempotent(
    client: TestClient,
    settings: Settings,
) -> None:
    with client.app.state.database.session_factory() as session:
        first = seed_report_demo(
            session,
            settings=settings,
            storage=client.app.state.storage,
        )
        second = seed_report_demo(
            session,
            settings=settings,
            storage=client.app.state.storage,
        )
        report_documents = session.scalar(
            select(func.count(Document.id)).where(
                Document.upload_idempotency_key.like("report-demo-%")
            )
        )
        report_workflows = session.scalar(
            select(func.count(WorkflowRun.id)).where(
                WorkflowRun.correlation_id.like("report-demo-workflow-%")
            )
        )
        digest_count = session.scalar(select(func.count(WeeklyDigest.id)))

    assert len(first) == len(second) == len(REPORT_ENTRIES)
    assert report_documents == len(REPORT_ENTRIES)
    assert report_workflows == 25
    assert digest_count == 1
