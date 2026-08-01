import csv
import hashlib
import io
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.audit import record_audit_event
from app.bank_schemas import BankColumnMapping
from app.config import Settings
from app.finance import normalize_vendor_name
from app.models import (
    ActorType,
    BankDirection,
    BankImport,
    BankImportStatus,
    BankTransaction,
    BankTransactionStatus,
    Document,
    DocumentStatus,
    DocumentType,
    Reconciliation,
    ReconciliationStatus,
)
from app.reliability import trigger_chaos
from app.security import AuthContext

ZERO = Decimal("0.00")
ACTIVE_RECONCILIATION_STATUSES = (
    ReconciliationStatus.AUTO_MATCHED,
    ReconciliationStatus.CONFIRMED,
)


class BankImportValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedBankRow:
    row_number: int
    transaction_date: date
    description: str
    amount: Decimal
    direction: BankDirection
    reference: str | None
    fingerprint: str


@dataclass(frozen=True)
class ScoredDocument:
    document: Document
    score: Decimal
    breakdown: dict[str, Any]


def safe_csv_filename(filename: str | None) -> str:
    original = Path(filename or "bank-statement.csv").name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", original).strip(".-")
    return (cleaned or "bank-statement.csv")[:255]


def import_bank_csv(
    session: Session,
    *,
    context: AuthContext,
    filename: str,
    content: bytes,
    mapping: BankColumnMapping,
    settings: Settings,
    correlation_id: str,
) -> tuple[BankImport, bool]:
    if not content:
        raise BankImportValidationError("The CSV file is empty.")
    if len(content) > settings.max_upload_bytes:
        raise BankImportValidationError("The CSV file exceeds the 10 MB upload limit.")

    file_hash = hashlib.sha256(content).hexdigest()
    existing_import = session.scalar(
        select(BankImport).where(
            BankImport.business_id == context.business_id,
            BankImport.sha256 == file_hash,
        )
    )
    if existing_import is not None:
        return existing_import, True

    inject_malformed_row = trigger_chaos(
        session,
        business_id=context.business_id,
        scenario_key="CSV_ROW_CORRUPTION",
        settings=settings,
    )

    rows, headers = _read_csv(content)
    _validate_mapping_headers(mapping, headers)
    bank_import = BankImport(
        business_id=context.business_id,
        filename=filename,
        sha256=file_hash,
        column_mapping=mapping.model_dump(exclude_none=True),
        status=BankImportStatus.COMPLETED,
        row_count=len(rows),
        imported_count=0,
        duplicate_count=0,
        error_count=0,
        row_errors=[],
        created_by=context.user.id,
    )
    session.add(bank_import)
    session.flush()

    existing_fingerprints = set(
        session.scalars(
            select(BankTransaction.external_fingerprint).where(
                BankTransaction.business_id == context.business_id
            )
        )
    )
    parsed_fingerprints: set[str] = set()
    imported_transactions: list[BankTransaction] = []
    row_errors: list[dict[str, Any]] = []
    duplicate_count = 0

    for row_number, row in enumerate(rows, start=2):
        if inject_malformed_row and row_number == 2:
            row_errors.append(
                {
                    "row": row_number,
                    "code": "CHAOS_ROW_INVALID",
                    "message": "Chaos Mode simulated one malformed CSV row.",
                }
            )
            continue
        try:
            parsed = _parse_row(row_number, row, mapping)
        except BankImportValidationError as exc:
            row_errors.append(
                {
                    "row": row_number,
                    "code": "ROW_INVALID",
                    "message": str(exc),
                }
            )
            continue
        if (
            parsed.fingerprint in existing_fingerprints
            or parsed.fingerprint in parsed_fingerprints
        ):
            duplicate_count += 1
            continue
        parsed_fingerprints.add(parsed.fingerprint)
        transaction = BankTransaction(
            business_id=context.business_id,
            bank_import_id=bank_import.id,
            row_number=parsed.row_number,
            external_fingerprint=parsed.fingerprint,
            transaction_date=parsed.transaction_date,
            description=parsed.description,
            amount=parsed.amount,
            direction=parsed.direction,
            reference=parsed.reference,
            status=BankTransactionStatus.UNMATCHED,
        )
        session.add(transaction)
        imported_transactions.append(transaction)

    bank_import.imported_count = len(imported_transactions)
    bank_import.duplicate_count = duplicate_count
    bank_import.error_count = len(row_errors)
    bank_import.row_errors = row_errors
    bank_import.status = (
        BankImportStatus.COMPLETED_WITH_ERRORS
        if row_errors
        else BankImportStatus.COMPLETED
    )
    session.flush()
    generate_reconciliation_candidates(
        session,
        business_id=context.business_id,
        transactions=imported_transactions,
        settings=settings,
        correlation_id=correlation_id,
    )
    record_audit_event(
        session,
        business_id=context.business_id,
        actor_type=ActorType.USER,
        actor_id=context.user.id,
        action="bank_import.completed",
        entity_type="bank_import",
        entity_id=bank_import.id,
        correlation_id=correlation_id,
        metadata={
            "filename": filename,
            "sha256": file_hash,
            "row_count": bank_import.row_count,
            "imported_count": bank_import.imported_count,
            "duplicate_count": bank_import.duplicate_count,
            "error_count": bank_import.error_count,
        },
    )
    session.commit()
    return bank_import, False


def generate_reconciliation_candidates(
    session: Session,
    *,
    business_id: uuid.UUID,
    transactions: list[BankTransaction],
    settings: Settings,
    correlation_id: str,
) -> None:
    if not transactions:
        return
    source_documents = list(
        session.scalars(
            select(Document).where(
                Document.business_id == business_id,
                Document.status == DocumentStatus.POSTED,
                Document.total.is_not(None),
                Document.transaction_date.is_not(None),
                Document.duplicate_of_id.is_(None),
            )
        )
    )
    active_source_ids = set(
        session.scalars(
            select(Reconciliation.source_id).where(
                Reconciliation.business_id == business_id,
                Reconciliation.status.in_(ACTIVE_RECONCILIATION_STATUSES),
            )
        )
    )

    for transaction in transactions:
        scored = sorted(
            (
                score_document_candidate(transaction, document)
                for document in source_documents
                if _direction_matches(transaction, document)
            ),
            key=lambda candidate: (candidate.score, str(candidate.document.id)),
            reverse=True,
        )
        reviewable = [
            candidate
            for candidate in scored
            if candidate.score >= settings.reconciliation_review_threshold
        ]
        if not reviewable:
            transaction.status = BankTransactionStatus.UNMATCHED
            continue

        top = reviewable[0]
        conflicts: list[str] = []
        if top.document.id in active_source_ids:
            conflicts.append("Dokumen sumber sudah digunakan oleh rekonsiliasi aktif.")
        if (
            len(reviewable) > 1
            and top.score - reviewable[1].score
            < settings.reconciliation_ambiguity_margin
        ):
            conflicts.append("Terdapat kandidat lain dengan skor yang berdekatan.")
        auto_match = (
            top.score >= settings.reconciliation_auto_match_threshold
            and not conflicts
        )

        for index, candidate in enumerate(reviewable):
            candidate_conflicts = conflicts if index == 0 else []
            status = (
                ReconciliationStatus.AUTO_MATCHED
                if index == 0 and auto_match
                else ReconciliationStatus.SUGGESTED
            )
            breakdown = {
                **candidate.breakdown,
                "policy": {
                    "review_threshold": str(settings.reconciliation_review_threshold),
                    "auto_match_threshold": str(
                        settings.reconciliation_auto_match_threshold
                    ),
                    "auto_match_eligible": status
                    == ReconciliationStatus.AUTO_MATCHED,
                    "conflicts": candidate_conflicts,
                },
            }
            reconciliation = Reconciliation(
                business_id=business_id,
                bank_transaction_id=transaction.id,
                source_type="DOCUMENT",
                source_id=candidate.document.id,
                score=candidate.score,
                score_breakdown=breakdown,
                status=status,
            )
            session.add(reconciliation)
            session.flush()
            record_audit_event(
                session,
                business_id=business_id,
                actor_type=ActorType.SYSTEM,
                actor_id=None,
                action=(
                    "reconciliation.auto_matched"
                    if status == ReconciliationStatus.AUTO_MATCHED
                    else "reconciliation.suggested"
                ),
                entity_type="reconciliation",
                entity_id=reconciliation.id,
                correlation_id=correlation_id,
                metadata={
                    "bank_transaction_id": str(transaction.id),
                    "source_id": str(candidate.document.id),
                    "score": str(candidate.score),
                },
            )
        if auto_match:
            transaction.status = BankTransactionStatus.AUTO_MATCHED
            active_source_ids.add(top.document.id)
        else:
            transaction.status = BankTransactionStatus.SUGGESTED


def score_document_candidate(
    transaction: BankTransaction,
    document: Document,
) -> ScoredDocument:
    amount_score, amount_explanation = _score_amount(transaction, document)
    date_score, date_explanation = _score_date(transaction, document)
    vendor_score, vendor_explanation = _score_vendor(transaction, document)
    reference_score, reference_explanation = _score_reference(transaction, document)
    score = amount_score + date_score + vendor_score + reference_score
    return ScoredDocument(
        document=document,
        score=score,
        breakdown={
            "amount": {
                "score": str(amount_score),
                "max_score": "50",
                "explanation": amount_explanation,
            },
            "date": {
                "score": str(date_score),
                "max_score": "20",
                "explanation": date_explanation,
            },
            "vendor": {
                "score": str(vendor_score),
                "max_score": "20",
                "explanation": vendor_explanation,
            },
            "reference": {
                "score": str(reference_score),
                "max_score": "10",
                "explanation": reference_explanation,
            },
        },
    )


def confirm_reconciliation(
    session: Session,
    *,
    reconciliation: Reconciliation,
    context: AuthContext,
    correlation_id: str,
    comment: str | None,
) -> Reconciliation:
    if reconciliation.status == ReconciliationStatus.CONFIRMED:
        return reconciliation
    if reconciliation.status == ReconciliationStatus.REJECTED:
        raise HTTPException(status_code=409, detail="Rejected candidate cannot be confirmed.")

    transaction = session.scalar(
        select(BankTransaction)
        .where(
            BankTransaction.business_id == context.business_id,
            BankTransaction.id == reconciliation.bank_transaction_id,
        )
        .with_for_update()
    )
    if transaction is None:
        raise HTTPException(status_code=404, detail="Bank transaction not found.")
    conflict = session.scalar(
        select(Reconciliation).where(
            Reconciliation.business_id == context.business_id,
            Reconciliation.id != reconciliation.id,
            Reconciliation.status.in_(ACTIVE_RECONCILIATION_STATUSES),
            or_(
                Reconciliation.bank_transaction_id
                == reconciliation.bank_transaction_id,
                (
                    (Reconciliation.source_type == reconciliation.source_type)
                    & (Reconciliation.source_id == reconciliation.source_id)
                ),
            ),
        )
    )
    if conflict is not None:
        raise HTTPException(
            status_code=409,
            detail="The transaction or source is already used by an active reconciliation.",
        )

    now = datetime.now(UTC)
    reconciliation.status = ReconciliationStatus.CONFIRMED
    reconciliation.decided_by = context.user.id
    reconciliation.decision_comment = comment
    reconciliation.decided_at = now
    transaction.status = BankTransactionStatus.CONFIRMED
    for other in session.scalars(
        select(Reconciliation).where(
            Reconciliation.business_id == context.business_id,
            Reconciliation.bank_transaction_id == transaction.id,
            Reconciliation.id != reconciliation.id,
            Reconciliation.status == ReconciliationStatus.SUGGESTED,
        )
    ):
        other.status = ReconciliationStatus.REJECTED

    _record_decision_audit(
        session,
        reconciliation=reconciliation,
        context=context,
        action="reconciliation.confirmed",
        correlation_id=correlation_id,
        comment=comment,
    )
    session.commit()
    return reconciliation


def reject_reconciliation(
    session: Session,
    *,
    reconciliation: Reconciliation,
    context: AuthContext,
    correlation_id: str,
    comment: str,
) -> Reconciliation:
    if reconciliation.status == ReconciliationStatus.REJECTED:
        return reconciliation
    if reconciliation.status == ReconciliationStatus.CONFIRMED:
        raise HTTPException(
            status_code=409,
            detail="A confirmed reconciliation cannot be rejected.",
        )
    transaction = session.scalar(
        select(BankTransaction)
        .where(
            BankTransaction.business_id == context.business_id,
            BankTransaction.id == reconciliation.bank_transaction_id,
        )
        .with_for_update()
    )
    if transaction is None:
        raise HTTPException(status_code=404, detail="Bank transaction not found.")

    now = datetime.now(UTC)
    reconciliation.status = ReconciliationStatus.REJECTED
    reconciliation.decided_by = context.user.id
    reconciliation.decision_comment = comment
    reconciliation.decided_at = now
    remaining_candidate = session.scalar(
        select(Reconciliation).where(
            Reconciliation.business_id == context.business_id,
            Reconciliation.bank_transaction_id == transaction.id,
            Reconciliation.id != reconciliation.id,
            Reconciliation.status == ReconciliationStatus.SUGGESTED,
        )
    )
    transaction.status = (
        BankTransactionStatus.SUGGESTED
        if remaining_candidate is not None
        else BankTransactionStatus.UNMATCHED
    )
    _record_decision_audit(
        session,
        reconciliation=reconciliation,
        context=context,
        action="reconciliation.rejected",
        correlation_id=correlation_id,
        comment=comment,
    )
    session.commit()
    return reconciliation


def get_reconciliation_or_404(
    session: Session,
    *,
    business_id: uuid.UUID,
    reconciliation_id: uuid.UUID,
    for_update: bool = False,
) -> Reconciliation:
    query = select(Reconciliation).where(
        Reconciliation.business_id == business_id,
        Reconciliation.id == reconciliation_id,
    )
    if for_update:
        query = query.with_for_update()
    reconciliation = session.scalar(query)
    if reconciliation is None:
        raise HTTPException(status_code=404, detail="Reconciliation candidate not found.")
    return reconciliation


def serialize_reconciliations(
    session: Session,
    reconciliations: list[Reconciliation],
) -> list[dict[str, Any]]:
    source_ids = {
        reconciliation.source_id
        for reconciliation in reconciliations
        if reconciliation.source_type == "DOCUMENT"
    }
    business_ids = {reconciliation.business_id for reconciliation in reconciliations}
    documents = {
        document.id: document
        for document in session.scalars(
            select(Document).where(
                Document.id.in_(source_ids),
                Document.business_id.in_(business_ids),
            )
        )
    } if source_ids else {}
    payloads: list[dict[str, Any]] = []
    for reconciliation in reconciliations:
        source = documents.get(reconciliation.source_id)
        if source is None:
            continue
        payloads.append(
            {
                "id": reconciliation.id,
                "bank_transaction_id": reconciliation.bank_transaction_id,
                "source_type": reconciliation.source_type,
                "source": {
                    "id": source.id,
                    "document_type": source.document_type,
                    "document_number": source.document_number,
                    "vendor_name": source.vendor_name,
                    "transaction_date": source.transaction_date,
                    "total": source.total,
                    "currency": source.currency,
                    "status": source.status,
                },
                "score": reconciliation.score,
                "score_breakdown": reconciliation.score_breakdown,
                "status": reconciliation.status,
                "decided_by": reconciliation.decided_by,
                "decision_comment": reconciliation.decision_comment,
                "decided_at": reconciliation.decided_at,
                "created_at": reconciliation.created_at,
            }
        )
    return payloads


def load_transactions_with_candidates(
    session: Session,
    transaction_ids: list[uuid.UUID],
) -> list[BankTransaction]:
    if not transaction_ids:
        return []
    return list(
        session.scalars(
            select(BankTransaction)
            .options(selectinload(BankTransaction.reconciliations))
            .where(BankTransaction.id.in_(transaction_ids))
        )
    )


def _read_csv(content: bytes) -> tuple[list[dict[str, str]], list[str]]:
    try:
        text_content = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BankImportValidationError("CSV must use UTF-8 encoding.") from exc
    try:
        reader = csv.DictReader(io.StringIO(text_content))
        headers = [header.strip() for header in (reader.fieldnames or []) if header]
        if not headers:
            raise BankImportValidationError("CSV header row is missing.")
        rows = [
            {str(key).strip(): (value or "").strip() for key, value in row.items()}
            for row in reader
        ]
    except csv.Error as exc:
        raise BankImportValidationError("CSV structure could not be parsed.") from exc
    return rows, headers


def _validate_mapping_headers(
    mapping: BankColumnMapping,
    headers: list[str],
) -> None:
    mapped_headers = {
        value
        for key, value in mapping.model_dump(exclude_none=True).items()
        if key != "date_format"
    }
    missing = sorted(mapped_headers.difference(headers))
    if missing:
        raise BankImportValidationError(
            f"Mapped columns were not found in the CSV: {', '.join(missing)}."
        )


def _parse_row(
    row_number: int,
    row: dict[str, str],
    mapping: BankColumnMapping,
) -> ParsedBankRow:
    description = row.get(mapping.description, "").strip()
    if not description:
        raise BankImportValidationError("Description is required.")
    transaction_date = _parse_date(row.get(mapping.date, ""), mapping.date_format)
    reference = (
        row.get(mapping.reference, "").strip() or None
        if mapping.reference
        else None
    )

    if mapping.amount:
        signed_amount = _parse_decimal(row.get(mapping.amount, ""))
        if signed_amount == ZERO:
            raise BankImportValidationError("Amount must not be zero.")
        direction = (
            BankDirection.DEBIT if signed_amount < ZERO else BankDirection.CREDIT
        )
        amount = abs(signed_amount)
    else:
        debit = _parse_decimal(row.get(mapping.debit or "", ""), blank_as_zero=True)
        credit = _parse_decimal(row.get(mapping.credit or "", ""), blank_as_zero=True)
        if debit < ZERO or credit < ZERO:
            raise BankImportValidationError(
                "Debit and credit columns must contain positive values."
            )
        if (debit > ZERO) == (credit > ZERO):
            raise BankImportValidationError(
                "Exactly one of debit or credit must contain a value."
            )
        direction = BankDirection.DEBIT if debit > ZERO else BankDirection.CREDIT
        amount = debit if debit > ZERO else credit

    normalized_description = re.sub(r"\s+", " ", description.lower()).strip()
    normalized_reference = (reference or "").lower()
    fingerprint_source = "|".join(
        (
            transaction_date.isoformat(),
            normalized_description,
            str(amount.quantize(Decimal("0.01"))),
            direction.value,
            normalized_reference,
        )
    )
    return ParsedBankRow(
        row_number=row_number,
        transaction_date=transaction_date,
        description=description[:500],
        amount=amount.quantize(Decimal("0.01")),
        direction=direction,
        reference=reference[:160] if reference else None,
        fingerprint=hashlib.sha256(fingerprint_source.encode()).hexdigest(),
    )


def _parse_date(value: str, date_format: str | None) -> date:
    cleaned = value.strip()
    if not cleaned:
        raise BankImportValidationError("Transaction date is required.")
    formats = [date_format] if date_format else []
    formats.extend(("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"))
    for candidate_format in formats:
        if candidate_format is None:
            continue
        try:
            return datetime.strptime(cleaned, candidate_format).date()
        except ValueError:
            continue
    raise BankImportValidationError(f"Invalid transaction date: {cleaned}.")


def _parse_decimal(value: str, *, blank_as_zero: bool = False) -> Decimal:
    cleaned = value.strip()
    if not cleaned:
        if blank_as_zero:
            return ZERO
        raise BankImportValidationError("Amount is required.")
    negative_parentheses = cleaned.startswith("(") and cleaned.endswith(")")
    normalized = re.sub(r"(?i)(idr|rp)", "", cleaned)
    normalized = normalized.replace(" ", "").replace("(", "").replace(")", "")
    if "," in normalized and "." in normalized:
        if normalized.rfind(",") > normalized.rfind("."):
            normalized = normalized.replace(".", "").replace(",", ".")
        else:
            normalized = normalized.replace(",", "")
    elif "," in normalized:
        suffix = normalized.rsplit(",", 1)[1]
        normalized = (
            normalized.replace(",", "")
            if len(suffix) == 3
            else normalized.replace(",", ".")
        )
    elif "." in normalized:
        suffix = normalized.rsplit(".", 1)[1]
        if len(suffix) == 3:
            normalized = normalized.replace(".", "")
    try:
        amount = Decimal(normalized)
    except InvalidOperation as exc:
        raise BankImportValidationError(f"Invalid amount: {cleaned}.") from exc
    return -amount if negative_parentheses else amount


def _direction_matches(transaction: BankTransaction, document: Document) -> bool:
    if document.document_type == DocumentType.CUSTOMER_INVOICE:
        return transaction.direction == BankDirection.CREDIT
    return transaction.direction == BankDirection.DEBIT


def _score_amount(
    transaction: BankTransaction,
    document: Document,
) -> tuple[Decimal, str]:
    if document.total is None:
        return ZERO, "Dokumen tidak memiliki nominal."
    difference = abs(transaction.amount - document.total)
    if difference == ZERO:
        return Decimal("50"), "Nominal sama persis."
    ratio = difference / max(document.total, Decimal("1"))
    if ratio <= Decimal("0.01"):
        return Decimal("40"), "Selisih nominal tidak lebih dari 1%."
    if ratio <= Decimal("0.05"):
        return Decimal("20"), "Selisih nominal tidak lebih dari 5%."
    return ZERO, "Nominal berbeda lebih dari 5%."


def _score_date(
    transaction: BankTransaction,
    document: Document,
) -> tuple[Decimal, str]:
    if document.transaction_date is None:
        return ZERO, "Dokumen tidak memiliki tanggal."
    distance = abs((transaction.transaction_date - document.transaction_date).days)
    if distance == 0:
        return Decimal("20"), "Tanggal transaksi sama."
    if distance <= 2:
        return Decimal("15"), f"Jarak tanggal {distance} hari."
    if distance <= 5:
        return Decimal("10"), f"Jarak tanggal {distance} hari."
    if distance <= 10:
        return Decimal("5"), f"Jarak tanggal {distance} hari."
    return ZERO, f"Jarak tanggal {distance} hari."


def _score_vendor(
    transaction: BankTransaction,
    document: Document,
) -> tuple[Decimal, str]:
    source_vendor = normalize_vendor_name(document.vendor_name)
    transaction_text = normalize_vendor_name(transaction.description)
    if not source_vendor or not transaction_text:
        return ZERO, "Nama pihak tidak tersedia untuk dibandingkan."
    if source_vendor == transaction_text:
        return Decimal("20"), "Nama pihak sama setelah normalisasi."
    if source_vendor in transaction_text or transaction_text in source_vendor:
        return Decimal("18"), "Nama pihak ditemukan pada deskripsi bank."
    similarity = Decimal(
        str(round(SequenceMatcher(None, source_vendor, transaction_text).ratio(), 4))
    )
    if similarity >= Decimal("0.75"):
        return Decimal("15"), "Nama pihak sangat mirip."
    if similarity >= Decimal("0.50"):
        return Decimal("8"), "Nama pihak memiliki kemiripan sebagian."
    return ZERO, "Nama pihak tidak cukup mirip."


def _score_reference(
    transaction: BankTransaction,
    document: Document,
) -> tuple[Decimal, str]:
    if not document.document_number:
        return ZERO, "Dokumen tidak memiliki nomor referensi."
    document_reference = re.sub(
        r"[^a-z0-9]",
        "",
        document.document_number.lower(),
    )
    bank_text = re.sub(
        r"[^a-z0-9]",
        "",
        f"{transaction.reference or ''} {transaction.description}".lower(),
    )
    if document_reference and document_reference in bank_text:
        return Decimal("10"), "Nomor dokumen ditemukan pada transaksi bank."
    return ZERO, "Nomor dokumen tidak ditemukan pada transaksi bank."


def _record_decision_audit(
    session: Session,
    *,
    reconciliation: Reconciliation,
    context: AuthContext,
    action: str,
    correlation_id: str,
    comment: str | None,
) -> None:
    record_audit_event(
        session,
        business_id=context.business_id,
        actor_type=ActorType.USER,
        actor_id=context.user.id,
        action=action,
        entity_type="reconciliation",
        entity_id=reconciliation.id,
        correlation_id=correlation_id,
        metadata={
            "bank_transaction_id": str(reconciliation.bank_transaction_id),
            "source_id": str(reconciliation.source_id),
            "score": str(reconciliation.score),
            "comment": comment,
        },
    )
