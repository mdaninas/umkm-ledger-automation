import hashlib
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.bank_demo import _build_demo_pdf, seed_bank_demo
from app.config import Settings, get_settings
from app.database import Database
from app.invoice_demo import seed_invoice_demo
from app.models import (
    ActorType,
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
from app.report_service import generate_weekly_digest
from app.seed import DEMO_BUSINESS_ID, DEMO_OWNER_ID, seed_demo
from app.storage import ObjectStorage, build_storage

REPORT_NAMESPACE = uuid.UUID("1ab7d66c-5ccd-48e8-a085-4bbcd3f06f79")

REPORT_ENTRIES = (
    # Previous comparison period.
    ("2026-06-income", date(2026, 6, 12), "Penjualan Juni", "4000", Decimal("110600000")),
    ("2026-06-material", date(2026, 6, 14), "Bahan baku Juni", "6100", Decimal("24330000")),
    ("2026-06-cogs", date(2026, 6, 18), "Harga pokok Juni", "5000", Decimal("20000000")),
    ("2026-06-other", date(2026, 6, 24), "Operasional Juni", "6900", Decimal("18670000")),
    # Current period: income Rp124.8m and expenses Rp79.35m.
    ("2026-07-income-01", date(2026, 7, 1), "Penjualan awal bulan", "4000", Decimal("18500000")),
    ("2026-07-material-01", date(2026, 7, 2), "Biji kopi arabika", "6100", Decimal("10500000")),
    ("2026-07-income-02", date(2026, 7, 5), "Penjualan wholesale", "4000", Decimal("22000000")),
    ("2026-07-cogs", date(2026, 7, 6), "Produksi dan tenaga kerja", "5000", Decimal("21400000")),
    ("2026-07-material-02", date(2026, 7, 8), "Biji kopi robusta", "6100", Decimal("9700000")),
    ("2026-07-income-03", date(2026, 7, 10), "Penjualan gerai", "4000", Decimal("19800000")),
    ("2026-07-rent", date(2026, 7, 12), "Sewa gerai", "6400", Decimal("8200000")),
    ("2026-07-material-03", date(2026, 7, 14), "Bahan baku tambahan", "6100", Decimal("10700000")),
    ("2026-07-income-04", date(2026, 7, 15), "Penjualan event", "4000", Decimal("21000000")),
    ("2026-07-utilities", date(2026, 7, 18), "Utilitas gerai", "6300", Decimal("4000000")),
    ("2026-07-other", date(2026, 7, 20), "Beban operasional lain", "6900", Decimal("14850000")),
    ("2026-07-income-05", date(2026, 7, 21), "Penjualan langganan", "4000", Decimal("20500000")),
    ("2026-07-income-06", date(2026, 7, 27), "Penjualan akhir bulan", "4000", Decimal("23000000")),
)


def seed_report_demo(
    session: Session,
    *,
    settings: Settings,
    storage: ObjectStorage,
) -> list[JournalEntry]:
    business = seed_demo(session, settings)
    seed_bank_demo(session, settings=settings, storage=storage)
    seed_invoice_demo(session)
    journals: list[JournalEntry] = []
    documents: list[Document] = []
    for key, entry_date, label, account_code, amount in REPORT_ENTRIES:
        document_number = f"RPT-{key.upper()}"
        existing = session.scalar(
            select(Document).where(
                Document.business_id == DEMO_BUSINESS_ID,
                Document.document_number == document_number,
            )
        )
        if existing is None:
            existing = _create_report_source(
                session,
                storage=storage,
                key=key,
                entry_date=entry_date,
                label=label,
                account_code=account_code,
                amount=amount,
            )
        journal = session.scalar(
            select(JournalEntry).where(
                JournalEntry.business_id == DEMO_BUSINESS_ID,
                JournalEntry.document_id == existing.id,
            )
        )
        if journal is None:
            raise RuntimeError(f"Jurnal demo laporan {key} tidak ditemukan.")
        documents.append(existing)
        journals.append(journal)

    _seed_workflow_metrics(session, documents)
    session.commit()
    digest = generate_weekly_digest(
        session,
        business=business,
        correlation_id="seed-report-dashboard-demo",
        period_end=date(2026, 7, 31),
    )
    assert isinstance(digest, WeeklyDigest)
    return journals


def _create_report_source(
    session: Session,
    *,
    storage: ObjectStorage,
    key: str,
    entry_date: date,
    label: str,
    account_code: str,
    amount: Decimal,
) -> Document:
    document_id = uuid.uuid5(REPORT_NAMESPACE, f"document:{key}")
    document_number = f"RPT-{key.upper()}"
    pdf_content = _build_demo_pdf(
        {
            "number": document_number,
            "vendor": label,
            "transaction_date": entry_date,
            "total": amount,
        }
    )
    storage_key = f"{DEMO_BUSINESS_ID}/{document_id}/{key}.pdf"
    storage.put(storage_key, pdf_content, "application/pdf")
    account = _account(session, account_code)
    bank = _account(session, "1010")
    is_income = account_code == "4000"
    document = Document(
        id=document_id,
        business_id=DEMO_BUSINESS_ID,
        source=DocumentSource.DEMO,
        original_filename=f"{key}.pdf",
        mime_type="application/pdf",
        storage_key=storage_key,
        sha256=hashlib.sha256(pdf_content).hexdigest(),
        upload_idempotency_key=f"report-demo-{key}",
        status=DocumentStatus.POSTED,
        document_type=(
            DocumentType.CUSTOMER_INVOICE if is_income else DocumentType.RECEIPT
        ),
        document_number=document_number,
        vendor_name=label,
        normalized_vendor_name=label.lower(),
        transaction_date=entry_date,
        currency="IDR",
        subtotal=amount,
        tax=Decimal("0"),
        total=amount,
        payment_method="BANK_TRANSFER",
        extraction_confidence=Decimal("1"),
        proposed_account_id=account.id,
        final_account_id=account.id,
        review_reason="Synthetic source for the reports dashboard demo.",
        created_by=DEMO_OWNER_ID,
        reviewed_by=DEMO_OWNER_ID,
        reviewed_at=datetime.combine(entry_date, datetime.min.time(), tzinfo=UTC),
        created_at=datetime.combine(entry_date, datetime.min.time(), tzinfo=UTC),
    )
    session.add(document)
    session.flush()
    journal = JournalEntry(
        id=uuid.uuid5(REPORT_NAMESPACE, f"journal:{key}"),
        business_id=DEMO_BUSINESS_ID,
        document_id=document.id,
        status=JournalStatus.POSTED,
        entry_date=entry_date,
        description=label,
        posted_at=datetime.combine(entry_date, datetime.min.time(), tzinfo=UTC),
        posted_by=DEMO_OWNER_ID,
        post_idempotency_key=f"report-demo-post-{key}",
    )
    if is_income:
        journal.lines.extend(
            [
                JournalLine(
                    ledger_account_id=bank.id,
                    debit=amount,
                    credit=Decimal("0"),
                    memo=label,
                ),
                JournalLine(
                    ledger_account_id=account.id,
                    debit=Decimal("0"),
                    credit=amount,
                    memo=label,
                ),
            ]
        )
    else:
        journal.lines.extend(
            [
                JournalLine(
                    ledger_account_id=account.id,
                    debit=amount,
                    credit=Decimal("0"),
                    memo=label,
                ),
                JournalLine(
                    ledger_account_id=bank.id,
                    debit=Decimal("0"),
                    credit=amount,
                    memo=label,
                ),
            ]
        )
    session.add(journal)
    session.add(
        DocumentExtraction(
            document_id=document.id,
            provider="mock",
            model="report-demo-v1",
            prompt_version="report-demo-v1",
            schema_version="document-v1",
            raw_structured_output={},
            normalized_output={"total": str(amount), "account_code": account_code},
            field_confidences={"total": 1, "account_code": 1},
            warnings=[],
            latency_ms=900 + (entry_date.day * 37),
            usage={
                "estimated_cost_idr": "10835.29",
                "synthetic": True,
            },
            created_at=datetime.combine(entry_date, datetime.min.time(), tzinfo=UTC),
        )
    )
    record_audit_event(
        session,
        business_id=DEMO_BUSINESS_ID,
        actor_type=ActorType.SYSTEM,
        actor_id=None,
        action="demo.report_source.seeded",
        entity_type="document",
        entity_id=document.id,
        correlation_id="seed-report-dashboard-demo",
        metadata={"synthetic_data": True, "account_code": account_code},
    )
    session.flush()
    return document


def _seed_workflow_metrics(session: Session, documents: list[Document]) -> None:
    for index in range(25):
        correlation_id = f"report-demo-workflow-{index:02d}"
        existing = session.scalar(
            select(WorkflowRun).where(WorkflowRun.correlation_id == correlation_id)
        )
        if existing is not None:
            continue
        started = datetime(2026, 7, 1, 1, tzinfo=UTC) + timedelta(
            days=index,
            seconds=index * 31,
        )
        if index < 23:
            status = WorkflowStatus.SUCCEEDED
            retry_count = 0
            error_code = None
            finished_at = started + timedelta(seconds=12 + index % 9)
        elif index == 23:
            status = WorkflowStatus.FAILED
            retry_count = 3
            error_code = "DEMO_PROVIDER_TIMEOUT"
            finished_at = started + timedelta(seconds=38)
        else:
            status = WorkflowStatus.WAITING_FOR_APPROVAL
            retry_count = 0
            error_code = None
            finished_at = None
        session.add(
            WorkflowRun(
                id=uuid.uuid5(REPORT_NAMESPACE, f"workflow:{index}"),
                business_id=DEMO_BUSINESS_ID,
                workflow_type="DOCUMENT_INGESTION",
                entity_type="DOCUMENT",
                entity_id=documents[index % len(documents)].id,
                status=status,
                correlation_id=correlation_id,
                started_at=started,
                finished_at=finished_at,
                retry_count=retry_count,
                error_code=error_code,
                created_at=started,
            )
        )


def _account(session: Session, code: str) -> LedgerAccount:
    account = session.scalar(
        select(LedgerAccount).where(
            LedgerAccount.business_id == DEMO_BUSINESS_ID,
            LedgerAccount.code == code,
        )
    )
    if account is None:
        raise RuntimeError(f"Demo ledger account {code} is missing.")
    return account


def main() -> None:
    settings = get_settings()
    database = Database(settings.database_url)
    storage = build_storage(settings)
    try:
        with database.session_factory() as session:
            journals = seed_report_demo(
                session,
                settings=settings,
                storage=storage,
            )
            print(f"Dashboard laporan siap: {len(journals)} jurnal sintetis.")
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
