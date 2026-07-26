import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.audit import record_audit_event
from app.config import Settings
from app.extraction import (
    ExtractionProvider,
    ExtractionResult,
    ExtractionSchemaError,
)
from app.finance import (
    choose_category_account,
    create_or_replace_draft_journal,
    find_duplicate,
    issue_dicts,
    normalize_vendor_name,
    validate_extraction,
)
from app.models import (
    ActorType,
    ApprovalRequest,
    ApprovalStatus,
    Document,
    DocumentExtraction,
    DocumentStatus,
    RiskLevel,
    StepStatus,
    WorkflowRun,
    WorkflowStatus,
    WorkflowStep,
)
from app.storage import ObjectStorage

WORKFLOW_STEPS = (
    "extraction",
    "validation",
    "duplicate_detection",
    "categorization",
    "journal_draft",
    "approval_request",
)


def create_document_workflow(
    session: Session,
    *,
    document: Document,
    correlation_id: str,
) -> WorkflowRun:
    run = WorkflowRun(
        business_id=document.business_id,
        workflow_type="DOCUMENT_INGESTION",
        entity_type="document",
        entity_id=document.id,
        status=WorkflowStatus.PENDING,
        correlation_id=correlation_id,
    )
    run.steps = [
        WorkflowStep(
            step_name=step_name,
            sequence=sequence,
            status=StepStatus.PENDING,
        )
        for sequence, step_name in enumerate(WORKFLOW_STEPS, start=1)
    ]
    session.add(run)
    session.flush()
    return run


def process_document(
    session: Session,
    *,
    document_id: uuid.UUID,
    storage: ObjectStorage,
    provider: ExtractionProvider,
    settings: Settings,
    workflow_run_id: uuid.UUID | None = None,
) -> Document:
    document = session.scalar(
        select(Document).where(Document.id == document_id).with_for_update()
    )
    if document is None:
        raise ValueError("Document does not exist.")

    run = _get_workflow_run(session, document, workflow_run_id)
    run.status = WorkflowStatus.RUNNING
    run.started_at = datetime.now(UTC)
    document.status = DocumentStatus.EXTRACTING
    _audit(
        session,
        document,
        run,
        "document.processing.started",
        {"provider": type(provider).__name__},
    )
    session.commit()

    try:
        result = _extract(session, document, run, storage, provider)
        session.commit()
        _validate(session, document, run, result, settings)
        session.commit()

        duplicate, reason = _detect_duplicate(session, document, run)
        if duplicate:
            document.duplicate_of_id = duplicate.id
            document.duplicate_reason = reason
            document.status = DocumentStatus.NEEDS_REVIEW
            document.review_reason = "A possible duplicate needs a human decision."
            _skip_remaining_steps(run, from_sequence=4, reason="duplicate_requires_review")
            run.status = WorkflowStatus.WAITING_FOR_APPROVAL
            _audit(
                session,
                document,
                run,
                "document.duplicate.detected",
                {"duplicate_of_id": str(duplicate.id), "reason": reason},
            )
            session.commit()
            return document

        if document.validation_errors:
            document.status = DocumentStatus.NEEDS_REVIEW
            document.review_reason = "Validation errors must be corrected."
            _skip_remaining_steps(run, from_sequence=4, reason="validation_errors")
            run.status = WorkflowStatus.WAITING_FOR_APPROVAL
            _audit(
                session,
                document,
                run,
                "document.validation.needs_review",
                {"errors": document.validation_errors},
            )
            session.commit()
            return document

        journal = _categorize_and_draft(session, document, run, result)
        _request_approval(session, document, run, journal.id)
        document.status = DocumentStatus.NEEDS_REVIEW
        document.review_reason = "Review the extraction and draft journal before posting."
        run.status = WorkflowStatus.WAITING_FOR_APPROVAL
        _audit(
            session,
            document,
            run,
            "document.processing.completed",
            {"journal_entry_id": str(journal.id)},
        )
        session.commit()
        return document
    except ExtractionSchemaError:
        session.rollback()
        _mark_failed(session, document_id, run.id, "AI_SCHEMA_INVALID")
        raise
    except Exception:
        session.rollback()
        _mark_failed(session, document_id, run.id, "DOCUMENT_PROCESSING_FAILED")
        raise


def _get_workflow_run(
    session: Session,
    document: Document,
    workflow_run_id: uuid.UUID | None,
) -> WorkflowRun:
    query = (
        select(WorkflowRun)
        .options(selectinload(WorkflowRun.steps))
        .where(
            WorkflowRun.business_id == document.business_id,
            WorkflowRun.entity_type == "document",
            WorkflowRun.entity_id == document.id,
        )
    )
    if workflow_run_id:
        query = query.where(WorkflowRun.id == workflow_run_id)
    else:
        query = query.order_by(WorkflowRun.created_at.desc())
    run = session.scalar(query)
    if run is None:
        raise ValueError("Document workflow does not exist.")
    return run


def _extract(
    session: Session,
    document: Document,
    run: WorkflowRun,
    storage: ObjectStorage,
    provider: ExtractionProvider,
) -> ExtractionResult:
    step = _start_step(run, 1)
    content = storage.get(document.storage_key)
    result = provider.extract(
        content=content,
        mime_type=document.mime_type,
        filename=document.original_filename,
    )
    payload = result.payload
    normalized = payload.model_dump(mode="json")
    session.add(
        DocumentExtraction(
            document_id=document.id,
            provider=result.provider,
            model=result.model,
            prompt_version=result.prompt_version,
            schema_version=result.schema_version,
            raw_structured_output=result.raw_output,
            normalized_output=normalized,
            field_confidences=payload.field_confidences,
            warnings=payload.warnings,
            latency_ms=result.latency_ms,
            usage=result.usage,
        )
    )
    document.document_type = payload.document_type
    document.document_number = payload.document_number
    document.vendor_name = payload.vendor_name
    document.normalized_vendor_name = normalize_vendor_name(payload.vendor_name)
    document.transaction_date = payload.transaction_date
    document.due_date = payload.due_date
    document.currency = payload.currency.upper()
    document.subtotal = payload.subtotal
    document.tax = payload.tax
    document.total = payload.total
    document.payment_method = payload.payment_method
    document.extraction_confidence = _average_confidence(payload.field_confidences)
    document.status = DocumentStatus.VALIDATING
    _finish_step(
        step,
        {
            "provider": result.provider,
            "model": result.model,
            "latency_ms": result.latency_ms,
        },
    )
    _audit(
        session,
        document,
        run,
        "document.extraction.succeeded",
        {"provider": result.provider, "model": result.model},
    )
    return result


def _validate(
    session: Session,
    document: Document,
    run: WorkflowRun,
    result: ExtractionResult,
    settings: Settings,
) -> None:
    step = _start_step(run, 2)
    errors, warnings = validate_extraction(result.payload, settings)
    document.validation_errors = issue_dicts(errors)
    document.validation_warnings = issue_dicts(warnings)
    _finish_step(step, {"error_count": len(errors), "warning_count": len(warnings)})
    _audit(
        session,
        document,
        run,
        "document.validation.completed",
        {"error_count": len(errors), "warning_count": len(warnings)},
    )


def _detect_duplicate(
    session: Session,
    document: Document,
    run: WorkflowRun,
) -> tuple[Document | None, str | None]:
    step = _start_step(run, 3)
    duplicate, reason = find_duplicate(session, document)
    _finish_step(
        step,
        {
            "is_duplicate": duplicate is not None,
            "reason": reason,
            "duplicate_of_id": str(duplicate.id) if duplicate else None,
        },
    )
    return duplicate, reason


def _categorize_and_draft(
    session: Session,
    document: Document,
    run: WorkflowRun,
    result: ExtractionResult,
):  # type: ignore[no-untyped-def]
    category_step = _start_step(run, 4)
    account = choose_category_account(
        session,
        business_id=document.business_id,
        suggested_code=result.payload.suggested_account_code,
    )
    document.proposed_account_id = account.id
    _finish_step(category_step, {"account_id": str(account.id), "account_code": account.code})

    journal_step = _start_step(run, 5)
    journal = create_or_replace_draft_journal(
        session,
        document=document,
        category_account=account,
    )
    _finish_step(journal_step, {"journal_entry_id": str(journal.id)})
    _audit(
        session,
        document,
        run,
        "journal.draft.created",
        {"journal_entry_id": str(journal.id), "account_code": account.code},
    )
    return journal


def _request_approval(
    session: Session,
    document: Document,
    run: WorkflowRun,
    journal_entry_id: uuid.UUID,
) -> None:
    step = _start_step(run, 6)
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
            workflow_run_id=run.id,
            document_id=document.id,
            journal_entry_id=journal_entry_id,
            action_type="POST_JOURNAL",
            payload={"journal_entry_id": str(journal_entry_id)},
            reason="Post the reviewed document as a balanced journal entry.",
            risk_level=RiskLevel.MEDIUM,
            status=ApprovalStatus.PENDING,
        )
        session.add(approval)
        session.flush()
    _finish_step(step, {"approval_request_id": str(approval.id)})
    _audit(
        session,
        document,
        run,
        "approval.requested",
        {"approval_request_id": str(approval.id)},
    )


def _start_step(run: WorkflowRun, sequence: int) -> WorkflowStep:
    step = next(item for item in run.steps if item.sequence == sequence)
    step.status = StepStatus.RUNNING
    step.started_at = datetime.now(UTC)
    return step


def _finish_step(step: WorkflowStep, output: dict[str, object]) -> None:
    step.status = StepStatus.SUCCEEDED
    step.output_summary = output
    step.finished_at = datetime.now(UTC)


def _skip_remaining_steps(run: WorkflowRun, *, from_sequence: int, reason: str) -> None:
    for step in run.steps:
        if step.sequence >= from_sequence and step.status == StepStatus.PENDING:
            step.status = StepStatus.SKIPPED
            step.output_summary = {"reason": reason}
            step.finished_at = datetime.now(UTC)


def _mark_failed(
    session: Session,
    document_id: uuid.UUID,
    workflow_run_id: uuid.UUID,
    error_code: str,
) -> None:
    document = session.get(Document, document_id)
    run = session.scalar(
        select(WorkflowRun)
        .options(selectinload(WorkflowRun.steps))
        .where(WorkflowRun.id == workflow_run_id)
    )
    if document is None or run is None:
        return
    document.status = DocumentStatus.FAILED
    document.error_code = error_code
    run.status = WorkflowStatus.FAILED
    run.error_code = error_code
    run.finished_at = datetime.now(UTC)
    running_step = next(
        (step for step in run.steps if step.status == StepStatus.RUNNING),
        None,
    )
    if running_step:
        running_step.status = StepStatus.FAILED
        running_step.error_code = error_code
        running_step.finished_at = datetime.now(UTC)
    _audit(session, document, run, "document.processing.failed", {"error_code": error_code})
    session.commit()


def _average_confidence(values: dict[str, float]) -> Decimal | None:
    if not values:
        return None
    return Decimal(str(sum(values.values()) / len(values))).quantize(Decimal("0.0001"))


def _audit(
    session: Session,
    document: Document,
    run: WorkflowRun,
    action: str,
    metadata: dict[str, object],
) -> None:
    record_audit_event(
        session,
        business_id=document.business_id,
        actor_type=ActorType.SYSTEM,
        actor_id=None,
        action=action,
        entity_type="document",
        entity_id=document.id,
        correlation_id=run.correlation_id,
        metadata={**metadata, "workflow_run_id": str(run.id)},
    )
