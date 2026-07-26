import re
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings
from app.extraction import ExtractionPayload
from app.models import (
    Document,
    DocumentType,
    JournalEntry,
    JournalLine,
    JournalStatus,
    LedgerAccount,
)

ZERO = Decimal("0.00")


class ValidationIssue(BaseModel):
    code: str
    field: str | None
    message: str
    severity: str


def normalize_vendor_name(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    legal_words = {"pt", "cv", "ud", "tbk", "persero"}
    parts = [part for part in normalized.split() if part not in legal_words]
    return " ".join(parts) or normalized


def validate_extraction(
    payload: ExtractionPayload,
    settings: Settings,
    *,
    today: date | None = None,
) -> tuple[list[ValidationIssue], list[ValidationIssue]]:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    check_date = today or date.today()

    if payload.total <= ZERO:
        errors.append(
            ValidationIssue(
                code="TOTAL_NOT_POSITIVE",
                field="total",
                message="Total must be greater than zero.",
                severity="error",
            )
        )
    if payload.currency.upper() != "IDR":
        errors.append(
            ValidationIssue(
                code="UNSUPPORTED_CURRENCY",
                field="currency",
                message="Only IDR documents are currently supported.",
                severity="error",
            )
        )
    if payload.subtotal is not None and payload.tax is not None:
        difference = abs((payload.subtotal + payload.tax) - payload.total)
        if difference > settings.amount_tolerance:
            errors.append(
                ValidationIssue(
                    code="TOTAL_MISMATCH",
                    field="total",
                    message="Subtotal plus tax does not match the total.",
                    severity="error",
                )
            )
    if (
        payload.transaction_date
        and payload.transaction_date > check_date + timedelta(days=settings.max_future_days)
    ):
        errors.append(
            ValidationIssue(
                code="DATE_TOO_FAR_IN_FUTURE",
                field="transaction_date",
                message="Transaction date is too far in the future.",
                severity="error",
            )
        )
    if payload.document_type == DocumentType.SUPPLIER_INVOICE:
        if not payload.vendor_name:
            warnings.append(
                ValidationIssue(
                    code="VENDOR_MISSING",
                    field="vendor_name",
                    message="Supplier invoice has no vendor name.",
                    severity="warning",
                )
            )
        if not payload.document_number:
            warnings.append(
                ValidationIssue(
                    code="DOCUMENT_NUMBER_MISSING",
                    field="document_number",
                    message="Supplier invoice has no invoice number.",
                    severity="warning",
                )
            )

    low_confidence_fields = sorted(
        field
        for field, score in payload.field_confidences.items()
        if Decimal(str(score)) < settings.minimum_extraction_confidence
    )
    if low_confidence_fields:
        warnings.append(
            ValidationIssue(
                code="LOW_CONFIDENCE",
                field=None,
                message=f"Review low-confidence fields: {', '.join(low_confidence_fields)}.",
                severity="warning",
            )
        )
    warnings.extend(
        ValidationIssue(
            code="PROVIDER_WARNING",
            field=None,
            message=warning,
            severity="warning",
        )
        for warning in payload.warnings
    )
    return errors, warnings


def issue_dicts(issues: list[ValidationIssue]) -> list[dict[str, Any]]:
    return [issue.model_dump(mode="json") for issue in issues]


def find_duplicate(session: Session, document: Document) -> tuple[Document | None, str | None]:
    exact = session.scalar(
        select(Document)
        .where(
            Document.business_id == document.business_id,
            Document.id != document.id,
            Document.sha256 == document.sha256,
            Document.status != "ARCHIVED",
        )
        .order_by(Document.created_at)
    )
    if exact:
        return exact, "EXACT_FILE"

    if not all(
        (
            document.normalized_vendor_name,
            document.document_number,
            document.transaction_date,
            document.total,
        )
    ):
        return None, None
    semantic = session.scalar(
        select(Document)
        .where(
            Document.business_id == document.business_id,
            Document.id != document.id,
            Document.normalized_vendor_name == document.normalized_vendor_name,
            Document.document_number == document.document_number,
            Document.transaction_date == document.transaction_date,
            Document.total == document.total,
            Document.currency == document.currency,
            Document.status != "ARCHIVED",
        )
        .order_by(Document.created_at)
    )
    return (semantic, "SEMANTIC_FIELDS") if semantic else (None, None)


def get_account_by_code(
    session: Session,
    *,
    business_id: uuid.UUID,
    code: str,
) -> LedgerAccount:
    account = session.scalar(
        select(LedgerAccount).where(
            LedgerAccount.business_id == business_id,
            LedgerAccount.code == code,
            LedgerAccount.is_active.is_(True),
        )
    )
    if account is None:
        raise ValueError(f"Ledger account {code} is not configured.")
    return account


def choose_category_account(
    session: Session,
    *,
    business_id: uuid.UUID,
    suggested_code: str | None,
) -> LedgerAccount:
    if suggested_code:
        suggested = session.scalar(
            select(LedgerAccount).where(
                LedgerAccount.business_id == business_id,
                LedgerAccount.code == suggested_code,
                LedgerAccount.is_active.is_(True),
            )
        )
        if suggested:
            return suggested
    return get_account_by_code(session, business_id=business_id, code="6900")


def create_or_replace_draft_journal(
    session: Session,
    *,
    document: Document,
    category_account: LedgerAccount,
) -> JournalEntry:
    if document.total is None or document.transaction_date is None:
        raise ValueError("Document needs a total and transaction date before journal creation.")

    journal = session.scalar(
        select(JournalEntry)
        .options(selectinload(JournalEntry.lines))
        .where(
            JournalEntry.business_id == document.business_id,
            JournalEntry.document_id == document.id,
        )
    )
    if journal and journal.status != JournalStatus.DRAFT:
        raise ValueError("A posted journal cannot be edited.")

    if journal is None:
        journal = JournalEntry(
            business_id=document.business_id,
            document_id=document.id,
            status=JournalStatus.DRAFT,
            entry_date=document.transaction_date,
            description=_journal_description(document),
        )
        session.add(journal)
    else:
        journal.entry_date = document.transaction_date
        journal.description = _journal_description(document)
        journal.lines.clear()

    amount = document.total
    if document.document_type == DocumentType.CUSTOMER_INVOICE:
        debit_account = get_account_by_code(
            session, business_id=document.business_id, code="1100"
        )
        credit_account = get_account_by_code(
            session, business_id=document.business_id, code="4000"
        )
    else:
        debit_account = category_account
        payment = (document.payment_method or "").upper()
        if document.document_type == DocumentType.SUPPLIER_INVOICE and not payment:
            credit_code = "2000"
        elif "BANK" in payment or "TRANSFER" in payment or "CARD" in payment:
            credit_code = "1010"
        else:
            credit_code = "1000"
        credit_account = get_account_by_code(
            session, business_id=document.business_id, code=credit_code
        )

    journal.lines.extend(
        [
            JournalLine(
                ledger_account_id=debit_account.id,
                debit=amount,
                credit=ZERO,
                memo=document.vendor_name,
            ),
            JournalLine(
                ledger_account_id=credit_account.id,
                debit=ZERO,
                credit=amount,
                memo=document.document_number,
            ),
        ]
    )
    assert_balanced(journal.lines)
    session.flush()
    return journal


def assert_balanced(lines: list[JournalLine]) -> None:
    if len(lines) < 2:
        raise ValueError("A journal requires at least two lines.")
    for line in lines:
        if line.debit < ZERO or line.credit < ZERO:
            raise ValueError("Journal amounts cannot be negative.")
        if line.debit > ZERO and line.credit > ZERO:
            raise ValueError("A journal line cannot contain both debit and credit.")
        if line.debit == ZERO and line.credit == ZERO:
            raise ValueError("A journal line cannot be empty.")
    total_debit = sum((line.debit for line in lines), ZERO)
    total_credit = sum((line.credit for line in lines), ZERO)
    if total_debit != total_credit:
        raise ValueError("Journal is not balanced.")


def _journal_description(document: Document) -> str:
    party = document.vendor_name or "Unknown counterparty"
    reference = document.document_number or document.original_filename
    return f"{party} — {reference}"[:255]
