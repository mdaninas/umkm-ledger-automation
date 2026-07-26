import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.audit import record_audit_event
from app.config import Settings
from app.extraction import ExtractionPayload
from app.finance import (
    assert_balanced,
    create_or_replace_draft_journal,
    issue_dicts,
    normalize_vendor_name,
    validate_extraction,
)
from app.finance_schemas import DocumentDetail, DocumentReviewRequest
from app.models import (
    ActorType,
    ApprovalRequest,
    ApprovalStatus,
    AuditEvent,
    Document,
    DocumentExtraction,
    DocumentStatus,
    JournalEntry,
    JournalLine,
    JournalStatus,
    LedgerAccount,
    RiskLevel,
    WorkflowRun,
    WorkflowStatus,
)
from app.security import AuthContext

ZERO = Decimal("0.00")


def get_document_or_404(
    session: Session,
    *,
    business_id: uuid.UUID,
    document_id: uuid.UUID,
    for_update: bool = False,
) -> Document:
    query = select(Document).where(
        Document.business_id == business_id,
        Document.id == document_id,
    )
    if for_update:
        query = query.with_for_update()
    document = session.scalar(query)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


def review_document(
    session: Session,
    *,
    document: Document,
    payload: DocumentReviewRequest,
    context: AuthContext,
    settings: Settings,
    correlation_id: str,
) -> Document:
    if document.status == DocumentStatus.POSTED:
        raise HTTPException(status_code=409, detail="A posted document cannot be edited.")
    before = _document_snapshot(document)

    if payload.duplicate_decision == "DUPLICATE":
        document.status = DocumentStatus.REJECTED
        document.review_reason = payload.review_comment or "Confirmed as duplicate."
        document.reviewed_by = context.user.id
        document.reviewed_at = datetime.now(UTC)
        _record_user_audit(
            session,
            document=document,
            context=context,
            action="document.duplicate.confirmed",
            correlation_id=correlation_id,
            metadata={"before": before, "decision": "DUPLICATE"},
        )
        session.commit()
        return document
    if payload.duplicate_decision == "DIFFERENT_TRANSACTION":
        document.duplicate_of_id = None
        document.duplicate_reason = None

    _apply_review_fields(document, payload)
    document.normalized_vendor_name = normalize_vendor_name(document.vendor_name)
    extraction_payload = _payload_from_document(document)
    errors, warnings = validate_extraction(extraction_payload, settings)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Correct the document fields before approval.",
                "errors": issue_dicts(errors),
            },
        )
    document.validation_errors = []
    document.validation_warnings = issue_dicts(warnings)

    account_id = payload.final_account_id or document.proposed_account_id
    if account_id is None:
        raise HTTPException(status_code=422, detail="Select a ledger account.")
    account = session.scalar(
        select(LedgerAccount).where(
            LedgerAccount.business_id == document.business_id,
            LedgerAccount.id == account_id,
            LedgerAccount.is_active.is_(True),
        )
    )
    if account is None:
        raise HTTPException(status_code=422, detail="Selected ledger account is invalid.")
    document.final_account_id = account.id
    journal = create_or_replace_draft_journal(
        session,
        document=document,
        category_account=account,
    )
    approval = _ensure_approval(session, document, journal)
    document.status = DocumentStatus.READY_TO_POST
    document.review_reason = payload.review_comment
    document.reviewed_by = context.user.id
    document.reviewed_at = datetime.now(UTC)
    _record_user_audit(
        session,
        document=document,
        context=context,
        action="document.review.completed",
        correlation_id=correlation_id,
        metadata={
            "before": before,
            "after": _document_snapshot(document),
            "journal_entry_id": str(journal.id),
            "approval_request_id": str(approval.id),
        },
    )
    session.commit()
    return document


def post_document(
    session: Session,
    *,
    document: Document,
    context: AuthContext,
    idempotency_key: str,
    correlation_id: str,
    comment: str | None,
) -> JournalEntry:
    journal = session.scalar(
        select(JournalEntry)
        .options(selectinload(JournalEntry.lines))
        .where(
            JournalEntry.business_id == document.business_id,
            JournalEntry.document_id == document.id,
        )
        .with_for_update()
    )
    if journal is None:
        raise HTTPException(status_code=409, detail="No draft journal exists.")
    if journal.status == JournalStatus.POSTED:
        return journal
    if document.status != DocumentStatus.READY_TO_POST:
        raise HTTPException(
            status_code=409,
            detail="Review and approve the document fields before posting.",
        )
    if document.duplicate_of_id is not None:
        raise HTTPException(status_code=409, detail="Resolve the duplicate warning first.")

    conflicting = session.scalar(
        select(JournalEntry).where(
            JournalEntry.business_id == document.business_id,
            JournalEntry.post_idempotency_key == idempotency_key,
            JournalEntry.id != journal.id,
        )
    )
    if conflicting:
        raise HTTPException(
            status_code=409,
            detail="This idempotency key was already used for another journal.",
        )
    try:
        assert_balanced(journal.lines)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    now = datetime.now(UTC)
    journal.status = JournalStatus.POSTED
    journal.posted_at = now
    journal.posted_by = context.user.id
    journal.post_idempotency_key = idempotency_key
    document.status = DocumentStatus.POSTED

    approval = session.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.business_id == document.business_id,
            ApprovalRequest.document_id == document.id,
            ApprovalRequest.action_type == "POST_JOURNAL",
        )
    )
    if approval:
        approval.status = ApprovalStatus.APPROVED
        approval.decided_by = context.user.id
        approval.decision_comment = comment
        approval.decided_at = now

    workflow = session.scalar(
        select(WorkflowRun)
        .where(
            WorkflowRun.business_id == document.business_id,
            WorkflowRun.entity_type == "document",
            WorkflowRun.entity_id == document.id,
        )
        .order_by(WorkflowRun.created_at.desc())
    )
    if workflow:
        workflow.status = WorkflowStatus.SUCCEEDED
        workflow.finished_at = now

    _record_user_audit(
        session,
        document=document,
        context=context,
        action="journal.posted",
        correlation_id=correlation_id,
        metadata={
            "journal_entry_id": str(journal.id),
            "idempotency_key": idempotency_key,
            "total": str(document.total),
        },
    )
    session.commit()
    return journal


def reject_approval(
    session: Session,
    *,
    approval: ApprovalRequest,
    context: AuthContext,
    comment: str,
    correlation_id: str,
) -> ApprovalRequest:
    if approval.status != ApprovalStatus.PENDING:
        return approval
    now = datetime.now(UTC)
    approval.status = ApprovalStatus.REJECTED
    approval.decided_by = context.user.id
    approval.decision_comment = comment
    approval.decided_at = now
    document = get_document_or_404(
        session,
        business_id=context.business_id,
        document_id=approval.document_id,
        for_update=True,
    )
    document.status = DocumentStatus.REJECTED
    document.review_reason = comment
    _record_user_audit(
        session,
        document=document,
        context=context,
        action="approval.rejected",
        correlation_id=correlation_id,
        metadata={"approval_request_id": str(approval.id), "comment": comment},
    )
    session.commit()
    return approval


def serialize_document_detail(session: Session, document: Document) -> DocumentDetail:
    extraction = session.scalar(
        select(DocumentExtraction)
        .where(DocumentExtraction.document_id == document.id)
        .order_by(DocumentExtraction.created_at.desc())
    )
    workflow = session.scalar(
        select(WorkflowRun)
        .options(selectinload(WorkflowRun.steps))
        .where(
            WorkflowRun.business_id == document.business_id,
            WorkflowRun.entity_type == "document",
            WorkflowRun.entity_id == document.id,
        )
        .order_by(WorkflowRun.created_at.desc())
    )
    journal = session.scalar(
        select(JournalEntry)
        .options(selectinload(JournalEntry.lines).selectinload(JournalLine.account))
        .where(
            JournalEntry.business_id == document.business_id,
            JournalEntry.document_id == document.id,
        )
    )
    approval = session.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.business_id == document.business_id,
            ApprovalRequest.document_id == document.id,
            ApprovalRequest.action_type == "POST_JOURNAL",
        )
    )
    audits = list(
        session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.business_id == document.business_id,
                AuditEvent.entity_type == "document",
                AuditEvent.entity_id == document.id,
            )
            .order_by(AuditEvent.created_at.desc())
        )
    )

    journal_payload = None
    if journal:
        total_debit = sum((line.debit for line in journal.lines), ZERO)
        total_credit = sum((line.credit for line in journal.lines), ZERO)
        journal_payload = {
            "id": journal.id,
            "status": journal.status,
            "entry_date": journal.entry_date,
            "description": journal.description,
            "posted_at": journal.posted_at,
            "lines": [
                {
                    "id": line.id,
                    "account": line.account,
                    "debit": line.debit,
                    "credit": line.credit,
                    "memo": line.memo,
                }
                for line in journal.lines
            ],
            "total_debit": total_debit,
            "total_credit": total_credit,
            "balanced": total_debit == total_credit,
        }
    return DocumentDetail.model_validate(
        {
            **_document_response_dict(document),
            "sha256": document.sha256,
            "due_date": document.due_date,
            "subtotal": document.subtotal,
            "tax": document.tax,
            "payment_method": document.payment_method,
            "validation_errors": document.validation_errors,
            "validation_warnings": document.validation_warnings,
            "proposed_account": document.proposed_account,
            "final_account": document.final_account,
            "latest_extraction": _extraction_dict(extraction) if extraction else None,
            "latest_workflow": _workflow_dict(workflow) if workflow else None,
            "journal": journal_payload,
            "approval": _approval_dict(approval) if approval else None,
            "audit_timeline": [
                {
                    "id": event.id,
                    "actor_type": event.actor_type.value,
                    "actor_id": event.actor_id,
                    "action": event.action,
                    "correlation_id": event.correlation_id,
                    "metadata": event.event_metadata,
                    "created_at": event.created_at,
                }
                for event in audits
            ],
        }
    )


def serialize_approval(approval: ApprovalRequest) -> dict[str, Any]:
    return _approval_dict(approval)


def _apply_review_fields(document: Document, payload: DocumentReviewRequest) -> None:
    fields = (
        "document_type",
        "document_number",
        "vendor_name",
        "transaction_date",
        "due_date",
        "currency",
        "subtotal",
        "tax",
        "total",
        "payment_method",
    )
    provided = payload.model_fields_set
    for field in fields:
        if field in provided:
            setattr(document, field, getattr(payload, field))
    if document.currency:
        document.currency = document.currency.upper()


def _payload_from_document(document: Document) -> ExtractionPayload:
    if document.total is None:
        raise HTTPException(status_code=422, detail="Total is required.")
    return ExtractionPayload(
        document_type=document.document_type,
        document_number=document.document_number,
        vendor_name=document.vendor_name,
        transaction_date=document.transaction_date,
        due_date=document.due_date,
        currency=document.currency,
        subtotal=document.subtotal,
        tax=document.tax,
        total=document.total,
        payment_method=document.payment_method,
        field_confidences={},
        warnings=[],
    )


def _ensure_approval(
    session: Session,
    document: Document,
    journal: JournalEntry,
) -> ApprovalRequest:
    approval = session.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.business_id == document.business_id,
            ApprovalRequest.document_id == document.id,
            ApprovalRequest.action_type == "POST_JOURNAL",
        )
    )
    if approval is None:
        approval = ApprovalRequest(
            business_id=document.business_id,
            document_id=document.id,
            journal_entry_id=journal.id,
            action_type="POST_JOURNAL",
            payload={"journal_entry_id": str(journal.id)},
            reason="Post the reviewed document as a balanced journal entry.",
            risk_level=RiskLevel.MEDIUM,
            status=ApprovalStatus.PENDING,
        )
        session.add(approval)
        session.flush()
    else:
        approval.journal_entry_id = journal.id
        approval.status = ApprovalStatus.PENDING
        approval.decided_by = None
        approval.decision_comment = None
        approval.decided_at = None
    return approval


def _document_snapshot(document: Document) -> dict[str, Any]:
    return {
        "status": document.status.value,
        "document_type": document.document_type.value,
        "document_number": document.document_number,
        "vendor_name": document.vendor_name,
        "transaction_date": document.transaction_date.isoformat()
        if document.transaction_date
        else None,
        "currency": document.currency,
        "total": str(document.total) if document.total is not None else None,
        "final_account_id": str(document.final_account_id)
        if document.final_account_id
        else None,
    }


def _document_response_dict(document: Document) -> dict[str, Any]:
    return {
        "id": document.id,
        "source": document.source,
        "original_filename": document.original_filename,
        "mime_type": document.mime_type,
        "status": document.status,
        "document_type": document.document_type,
        "document_number": document.document_number,
        "vendor_name": document.vendor_name,
        "transaction_date": document.transaction_date,
        "currency": document.currency,
        "total": document.total,
        "extraction_confidence": document.extraction_confidence,
        "duplicate_of_id": document.duplicate_of_id,
        "duplicate_reason": document.duplicate_reason,
        "review_reason": document.review_reason,
        "error_code": document.error_code,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
    }


def _extraction_dict(extraction: DocumentExtraction) -> dict[str, Any]:
    return {
        "id": extraction.id,
        "provider": extraction.provider,
        "model": extraction.model,
        "prompt_version": extraction.prompt_version,
        "schema_version": extraction.schema_version,
        "normalized_output": extraction.normalized_output,
        "field_confidences": extraction.field_confidences,
        "warnings": extraction.warnings,
        "latency_ms": extraction.latency_ms,
        "usage": extraction.usage,
        "created_at": extraction.created_at,
    }


def _workflow_dict(workflow: WorkflowRun) -> dict[str, Any]:
    return {
        "id": workflow.id,
        "status": workflow.status,
        "correlation_id": workflow.correlation_id,
        "retry_count": workflow.retry_count,
        "error_code": workflow.error_code,
        "started_at": workflow.started_at,
        "finished_at": workflow.finished_at,
        "created_at": workflow.created_at,
        "steps": [
            {
                "id": step.id,
                "step_name": step.step_name,
                "sequence": step.sequence,
                "status": step.status,
                "output_summary": step.output_summary,
                "error_code": step.error_code,
                "started_at": step.started_at,
                "finished_at": step.finished_at,
            }
            for step in workflow.steps
        ],
    }


def _approval_dict(approval: ApprovalRequest) -> dict[str, Any]:
    return {
        "id": approval.id,
        "document_id": approval.document_id,
        "journal_entry_id": approval.journal_entry_id,
        "action_type": approval.action_type,
        "reason": approval.reason,
        "risk_level": approval.risk_level,
        "status": approval.status,
        "requested_at": approval.requested_at,
        "decided_by": approval.decided_by,
        "decision_comment": approval.decision_comment,
        "decided_at": approval.decided_at,
    }


def _record_user_audit(
    session: Session,
    *,
    document: Document,
    context: AuthContext,
    action: str,
    correlation_id: str,
    metadata: dict[str, Any],
) -> None:
    record_audit_event(
        session,
        business_id=document.business_id,
        actor_type=ActorType.USER,
        actor_id=context.user.id,
        action=action,
        entity_type="document",
        entity_id=document.id,
        correlation_id=correlation_id,
        metadata=metadata,
    )
