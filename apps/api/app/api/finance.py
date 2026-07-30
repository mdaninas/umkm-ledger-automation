import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db_session
from app.document_service import (
    get_document_or_404,
    post_document,
    reject_approval,
    serialize_approval,
    serialize_document_detail,
)
from app.finance_schemas import (
    ApprovalResponse,
    DashboardSummary,
    DocumentDetail,
    LedgerAccountResponse,
    PostDocumentRequest,
    RejectApprovalRequest,
)
from app.models import (
    AccountType,
    ApprovalRequest,
    ApprovalStatus,
    Document,
    DocumentStatus,
    JournalEntry,
    JournalLine,
    JournalStatus,
    LedgerAccount,
    Role,
)
from app.security import AuthContext, get_auth_context

router = APIRouter(tags=["finance"])
ZERO = Decimal("0.00")


@router.get("/accounts", response_model=list[LedgerAccountResponse])
def list_accounts(
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> list[LedgerAccount]:
    return list(
        session.scalars(
            select(LedgerAccount)
            .where(
                LedgerAccount.business_id == context.business_id,
                LedgerAccount.is_active.is_(True),
            )
            .order_by(LedgerAccount.code)
        )
    )


@router.get("/approvals", response_model=list[ApprovalResponse])
def list_approvals(
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
    approval_status: ApprovalStatus | None = None,
) -> list[dict[str, object]]:
    query = select(ApprovalRequest).where(
        ApprovalRequest.business_id == context.business_id
    )
    if approval_status:
        query = query.where(ApprovalRequest.status == approval_status)
    approvals = session.scalars(query.order_by(ApprovalRequest.requested_at.desc()))
    return [serialize_approval(approval) for approval in approvals]


@router.get("/approvals/{approval_id}", response_model=DocumentDetail)
def get_approval(
    approval_id: uuid.UUID,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> DocumentDetail:
    approval = _approval_or_404(session, context.business_id, approval_id)
    _require_document_approval(approval)
    assert approval.document_id is not None
    document = get_document_or_404(
        session,
        business_id=context.business_id,
        document_id=approval.document_id,
    )
    return serialize_document_detail(session, document)


@router.post("/approvals/{approval_id}/approve", response_model=DocumentDetail)
def approve_request(
    approval_id: uuid.UUID,
    payload: PostDocumentRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=128),
    ],
) -> DocumentDetail:
    _require_owner(context)
    approval = _approval_or_404(session, context.business_id, approval_id)
    _require_document_approval(approval)
    assert approval.document_id is not None
    document = get_document_or_404(
        session,
        business_id=context.business_id,
        document_id=approval.document_id,
        for_update=True,
    )
    post_document(
        session,
        document=document,
        context=context,
        idempotency_key=idempotency_key,
        correlation_id=request.state.correlation_id,
        comment=payload.comment,
    )
    return serialize_document_detail(session, document)


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalResponse)
def reject_request(
    approval_id: uuid.UUID,
    payload: RejectApprovalRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, object]:
    _require_owner(context)
    approval = _approval_or_404(session, context.business_id, approval_id)
    _require_document_approval(approval)
    rejected = reject_approval(
        session,
        approval=approval,
        context=context,
        comment=payload.comment,
        correlation_id=request.state.correlation_id,
    )
    return serialize_approval(rejected)


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> DashboardSummary:
    posted_count = _count_journals(session, context.business_id, JournalStatus.POSTED)
    draft_count = _count_journals(session, context.business_id, JournalStatus.DRAFT)
    needs_review_count = session.scalar(
        select(func.count())
        .select_from(Document)
        .where(
            Document.business_id == context.business_id,
            Document.status.in_(
                [DocumentStatus.NEEDS_REVIEW, DocumentStatus.READY_TO_POST]
            ),
        )
    ) or 0
    rows = session.execute(
        select(
            LedgerAccount.code,
            LedgerAccount.account_type,
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        )
        .join(JournalLine, JournalLine.ledger_account_id == LedgerAccount.id)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .where(
            JournalEntry.business_id == context.business_id,
            JournalEntry.status == JournalStatus.POSTED,
        )
        .group_by(LedgerAccount.code, LedgerAccount.account_type)
    )
    income = expenses = cash = bank = ZERO
    for code, account_type, debit, credit in rows:
        debit_amount = Decimal(debit)
        credit_amount = Decimal(credit)
        if account_type == AccountType.REVENUE:
            income += credit_amount - debit_amount
        elif account_type == AccountType.EXPENSE:
            expenses += debit_amount - credit_amount
        if code == "1000":
            cash += debit_amount - credit_amount
        elif code == "1010":
            bank += debit_amount - credit_amount
    return DashboardSummary(
        posted_journal_count=posted_count,
        draft_journal_count=draft_count,
        needs_review_count=needs_review_count,
        posted_income=income,
        posted_expenses=expenses,
        cash_balance=cash,
        bank_balance=bank,
    )


def _approval_or_404(
    session: Session,
    business_id: uuid.UUID,
    approval_id: uuid.UUID,
) -> ApprovalRequest:
    approval = session.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.business_id == business_id,
            ApprovalRequest.id == approval_id,
        )
    )
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval request not found.")
    return approval


def _require_owner(context: AuthContext) -> None:
    if context.membership.role != Role.OWNER:
        raise HTTPException(status_code=403, detail="Only an owner can decide approvals.")


def _require_document_approval(approval: ApprovalRequest) -> None:
    if approval.entity_type != "DOCUMENT" or approval.document_id is None:
        raise HTTPException(
            status_code=409,
            detail="Use the invoice reminder endpoint for this approval.",
        )


def _count_journals(
    session: Session,
    business_id: uuid.UUID,
    journal_status: JournalStatus,
) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(JournalEntry)
            .where(
                JournalEntry.business_id == business_id,
                JournalEntry.status == journal_status,
            )
        )
        or 0
    )
