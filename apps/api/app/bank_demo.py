import hashlib
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.config import Settings, get_settings
from app.database import Database
from app.finance import normalize_vendor_name
from app.models import (
    ActorType,
    Document,
    DocumentSource,
    DocumentStatus,
    DocumentType,
    JournalEntry,
    JournalLine,
    JournalStatus,
    LedgerAccount,
)
from app.seed import DEMO_BUSINESS_ID, DEMO_OWNER_ID, seed_demo
from app.storage import ObjectStorage, build_storage

DEMO_PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF"
DEMO_SOURCES = (
    {
        "id": uuid.UUID("a94a7299-43e4-43e7-9c08-9135c0d4f38d"),
        "number": "BANK-DEMO-001",
        "vendor": "CV Biji Nusantara",
        "transaction_date": date(2026, 7, 25),
        "total": Decimal("350000.00"),
        "document_type": DocumentType.RECEIPT,
        "account_code": "6100",
    },
    {
        "id": uuid.UUID("1c7e3f54-8e67-4495-a496-83741d94ee44"),
        "number": "BANK-DEMO-002",
        "vendor": "PT Sinar Kemasan",
        "transaction_date": date(2026, 7, 18),
        "total": Decimal("825000.00"),
        "document_type": DocumentType.SUPPLIER_INVOICE,
        "account_code": "6900",
    },
)


def seed_bank_demo(
    session: Session,
    *,
    settings: Settings,
    storage: ObjectStorage,
) -> list[Document]:
    seed_demo(session, settings)
    documents: list[Document] = []
    for source in DEMO_SOURCES:
        existing = session.scalar(
            select(Document).where(
                Document.business_id == DEMO_BUSINESS_ID,
                Document.document_number == source["number"],
            )
        )
        if existing is not None:
            if existing.status != DocumentStatus.POSTED:
                raise RuntimeError(
                    f"Demo source {source['number']} exists but is not posted."
                )
            documents.append(existing)
            continue
        documents.append(_create_posted_source(session, storage=storage, source=source))
    session.commit()
    return documents


def _create_posted_source(
    session: Session,
    *,
    storage: ObjectStorage,
    source: dict[str, object],
) -> Document:
    document_id = source["id"]
    if not isinstance(document_id, uuid.UUID):
        raise TypeError("Demo source id must be a UUID.")
    document_number = str(source["number"])
    vendor = str(source["vendor"])
    transaction_date = source["transaction_date"]
    total = source["total"]
    document_type = source["document_type"]
    if not isinstance(transaction_date, date):
        raise TypeError("Demo transaction date must be a date.")
    if not isinstance(total, Decimal):
        raise TypeError("Demo total must be a decimal.")
    if not isinstance(document_type, DocumentType):
        raise TypeError("Demo document type must be a DocumentType.")

    filename = f"{document_number.lower()}.pdf"
    storage_key = f"{DEMO_BUSINESS_ID}/{document_id}/{filename}"
    storage.put(storage_key, DEMO_PDF, "application/pdf")
    now = datetime.now(UTC)
    category_account = _account(session, str(source["account_code"]))
    document = Document(
        id=document_id,
        business_id=DEMO_BUSINESS_ID,
        source=DocumentSource.DEMO,
        original_filename=filename,
        mime_type="application/pdf",
        storage_key=storage_key,
        sha256=hashlib.sha256(DEMO_PDF + document_number.encode()).hexdigest(),
        upload_idempotency_key=f"demo-source-{document_number.lower()}",
        status=DocumentStatus.POSTED,
        document_type=document_type,
        document_number=document_number,
        vendor_name=vendor,
        normalized_vendor_name=normalize_vendor_name(vendor),
        transaction_date=transaction_date,
        currency="IDR",
        subtotal=total,
        tax=Decimal("0.00"),
        total=total,
        payment_method="BANK_TRANSFER",
        extraction_confidence=Decimal("1.0000"),
        proposed_account_id=category_account.id,
        final_account_id=category_account.id,
        review_reason="Synthetic source for the bank reconciliation demo.",
        created_by=DEMO_OWNER_ID,
        reviewed_by=DEMO_OWNER_ID,
        reviewed_at=now,
    )
    session.add(document)
    session.flush()

    bank_account = _account(session, "1010")
    journal = JournalEntry(
        business_id=DEMO_BUSINESS_ID,
        document_id=document.id,
        status=JournalStatus.POSTED,
        entry_date=transaction_date,
        description=f"{vendor} — {document_number}",
        posted_at=now,
        posted_by=DEMO_OWNER_ID,
        post_idempotency_key=f"demo-post-{document_number.lower()}",
    )
    journal.lines.extend(
        [
            JournalLine(
                ledger_account_id=category_account.id,
                debit=total,
                credit=Decimal("0.00"),
                memo=vendor,
            ),
            JournalLine(
                ledger_account_id=bank_account.id,
                debit=Decimal("0.00"),
                credit=total,
                memo=document_number,
            ),
        ]
    )
    session.add(journal)
    record_audit_event(
        session,
        business_id=DEMO_BUSINESS_ID,
        actor_type=ActorType.SYSTEM,
        actor_id=None,
        action="demo.reconciliation_source.seeded",
        entity_type="document",
        entity_id=document.id,
        correlation_id="seed-bank-reconciliation-demo",
        metadata={
            "document_number": document_number,
            "synthetic_data": True,
        },
    )
    return document


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
            documents = seed_bank_demo(
                session,
                settings=settings,
                storage=storage,
            )
            ready = ", ".join(
                document.document_number or str(document.id) for document in documents
            )
            print(f"Sumber demo rekonsiliasi siap: {ready}")
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
