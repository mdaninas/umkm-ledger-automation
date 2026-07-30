import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db_session
from app.invoice_schemas import (
    InvoiceCountsResponse,
    InvoiceDetailResponse,
    InvoiceListResponse,
    InvoiceSummaryResponse,
    OutboxMessageResponse,
    ReminderApproveRequest,
    ReminderDraftRequest,
    ReminderRejectRequest,
    ReminderResponse,
    ReminderUpdateRequest,
    SchedulerRunRequest,
    SchedulerRunResponse,
)
from app.invoice_service import (
    approve_reminder,
    business_local_date,
    create_reminder,
    get_invoice_or_404,
    get_reminder_or_404,
    reject_reminder,
    reminder_approval,
    scan_invoices,
    serialize_invoice,
    serialize_outbox,
    serialize_reminder,
    update_reminder,
)
from app.models import (
    ActorType,
    Business,
    Customer,
    Invoice,
    InvoiceReminder,
    InvoiceStatus,
    OutboxMessage,
    OutboxStatus,
    ReminderStatus,
    Role,
)
from app.security import AuthContext, get_auth_context

router = APIRouter(tags=["invoices"])


@router.get("/invoices", response_model=InvoiceListResponse)
def list_invoices(
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
    invoice_status: Annotated[InvoiceStatus | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InvoiceListResponse:
    business = session.get(Business, context.business_id)
    if business is None:
        raise HTTPException(status_code=404, detail="Bisnis tidak ditemukan.")
    as_of = business_local_date(business)
    filters = [Invoice.business_id == context.business_id]
    if invoice_status:
        filters.append(Invoice.status == invoice_status)
    if search:
        term = f"%{search.strip()}%"
        filters.append(
            or_(
                Invoice.invoice_number.ilike(term),
                Invoice.customer.has(Customer.name.ilike(term)),
                Invoice.customer.has(Customer.email.ilike(term)),
            )
        )
    total = session.scalar(
        select(func.count()).select_from(Invoice).where(*filters)
    ) or 0
    invoices = list(
        session.scalars(
            select(Invoice)
            .options(
                selectinload(Invoice.customer),
                selectinload(Invoice.reminders).selectinload(
                    InvoiceReminder.outbox_messages
                ),
            )
            .where(*filters)
            .order_by(
                case(
                    (Invoice.status == InvoiceStatus.OVERDUE, 0),
                    (Invoice.status == InvoiceStatus.DUE_SOON, 1),
                    (Invoice.status == InvoiceStatus.OUTSTANDING, 2),
                    else_=3,
                ),
                Invoice.due_date,
                Invoice.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
    )
    return InvoiceListResponse(
        items=[
            InvoiceSummaryResponse.model_validate(
                serialize_invoice(session, invoice, as_of=as_of)
            )
            for invoice in invoices
        ],
        total=total,
        counts=_invoice_counts(session, context.business_id),
        as_of=as_of,
    )


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetailResponse)
def get_invoice(
    invoice_id: uuid.UUID,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> InvoiceDetailResponse:
    invoice = get_invoice_or_404(
        session,
        business_id=context.business_id,
        invoice_id=invoice_id,
    )
    business = session.get(Business, context.business_id)
    assert business is not None
    return InvoiceDetailResponse.model_validate(
        serialize_invoice(
            session,
            invoice,
            as_of=business_local_date(business),
            include_detail=True,
        )
    )


@router.post("/invoices/scheduler/run", response_model=SchedulerRunResponse)
def run_invoice_scheduler(
    payload: SchedulerRunRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> SchedulerRunResponse:
    _require_owner(context)
    result = scan_invoices(
        session,
        settings=request.app.state.settings,
        correlation_id=request.state.correlation_id,
        business_id=context.business_id,
        as_of=payload.as_of,
        force_fallback=payload.force_fallback,
    )
    return SchedulerRunResponse.model_validate(result)


@router.post(
    "/invoices/{invoice_id}/reminder-draft",
    response_model=ReminderResponse,
)
def draft_invoice_reminder(
    invoice_id: uuid.UUID,
    payload: ReminderDraftRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> ReminderResponse:
    invoice = get_invoice_or_404(
        session,
        business_id=context.business_id,
        invoice_id=invoice_id,
    )
    reminder = create_reminder(
        session,
        invoice=invoice,
        settings=request.app.state.settings,
        correlation_id=request.state.correlation_id,
        actor_type=ActorType.USER,
        actor_id=context.user.id,
        force_fallback=payload.force_fallback,
    )
    session.commit()
    approval = reminder_approval(session, reminder)
    return ReminderResponse.model_validate(serialize_reminder(reminder, approval))


@router.patch("/invoice-reminders/{reminder_id}", response_model=ReminderResponse)
def edit_invoice_reminder(
    reminder_id: uuid.UUID,
    payload: ReminderUpdateRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> ReminderResponse:
    reminder = get_reminder_or_404(
        session,
        business_id=context.business_id,
        reminder_id=reminder_id,
    )
    updated = update_reminder(
        session,
        reminder=reminder,
        context=context,
        subject=payload.subject,
        body=payload.body,
        correlation_id=request.state.correlation_id,
    )
    return ReminderResponse.model_validate(
        serialize_reminder(updated, reminder_approval(session, updated))
    )


@router.post(
    "/invoice-reminders/{reminder_id}/approve",
    response_model=InvoiceDetailResponse,
)
def approve_invoice_reminder(
    reminder_id: uuid.UUID,
    payload: ReminderApproveRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=128),
    ],
) -> InvoiceDetailResponse:
    _require_owner(context)
    reminder = get_reminder_or_404(
        session,
        business_id=context.business_id,
        reminder_id=reminder_id,
    )
    outbox = approve_reminder(
        session,
        reminder=reminder,
        context=context,
        idempotency_key=idempotency_key,
        comment=payload.comment,
        correlation_id=request.state.correlation_id,
    )
    if request.app.state.settings.enqueue_document_tasks:
        from app.worker import dispatch_outbox_task

        dispatch_outbox_task.delay(str(outbox.id))
    invoice = get_invoice_or_404(
        session,
        business_id=context.business_id,
        invoice_id=reminder.invoice_id,
    )
    business = session.get(Business, context.business_id)
    assert business is not None
    return InvoiceDetailResponse.model_validate(
        serialize_invoice(
            session,
            invoice,
            as_of=business_local_date(business),
            include_detail=True,
        )
    )


@router.post(
    "/invoice-reminders/{reminder_id}/reject",
    response_model=InvoiceDetailResponse,
)
def reject_invoice_reminder(
    reminder_id: uuid.UUID,
    payload: ReminderRejectRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> InvoiceDetailResponse:
    _require_owner(context)
    reminder = get_reminder_or_404(
        session,
        business_id=context.business_id,
        reminder_id=reminder_id,
    )
    reject_reminder(
        session,
        reminder=reminder,
        context=context,
        comment=payload.comment,
        correlation_id=request.state.correlation_id,
    )
    invoice = get_invoice_or_404(
        session,
        business_id=context.business_id,
        invoice_id=reminder.invoice_id,
    )
    business = session.get(Business, context.business_id)
    assert business is not None
    return InvoiceDetailResponse.model_validate(
        serialize_invoice(
            session,
            invoice,
            as_of=business_local_date(business),
            include_detail=True,
        )
    )


@router.get("/outbox-messages", response_model=list[OutboxMessageResponse])
def list_outbox_messages(
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
    message_status: Annotated[OutboxStatus | None, Query(alias="status")] = None,
) -> list[OutboxMessageResponse]:
    query = select(OutboxMessage).where(
        OutboxMessage.business_id == context.business_id
    )
    if message_status:
        query = query.where(OutboxMessage.status == message_status)
    messages = session.scalars(query.order_by(OutboxMessage.created_at.desc()))
    return [
        OutboxMessageResponse.model_validate(serialize_outbox(message))
        for message in messages
    ]


@router.post(
    "/outbox-messages/{outbox_id}/retry",
    response_model=OutboxMessageResponse,
)
def retry_outbox_message(
    outbox_id: uuid.UUID,
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> OutboxMessageResponse:
    _require_owner(context)
    outbox = session.scalar(
        select(OutboxMessage).where(
            OutboxMessage.business_id == context.business_id,
            OutboxMessage.id == outbox_id,
        )
    )
    if outbox is None:
        raise HTTPException(status_code=404, detail="Pesan outbox tidak ditemukan.")
    if outbox.status == OutboxStatus.SENT:
        return OutboxMessageResponse.model_validate(serialize_outbox(outbox))
    outbox.status = OutboxStatus.PENDING
    outbox.next_attempt_at = None
    outbox.reminder.status = ReminderStatus.QUEUED
    session.commit()
    if request.app.state.settings.enqueue_document_tasks:
        from app.worker import dispatch_outbox_task

        dispatch_outbox_task.delay(str(outbox.id))
    return OutboxMessageResponse.model_validate(serialize_outbox(outbox))


def _invoice_counts(
    session: Session,
    business_id: uuid.UUID,
) -> InvoiceCountsResponse:
    rows = session.execute(
        select(
            Invoice.status,
            func.count(),
            func.coalesce(func.sum(Invoice.total), 0),
        )
        .where(Invoice.business_id == business_id)
        .group_by(Invoice.status)
    )
    by_status = {
        status: (count, Decimal(amount))
        for status, count, amount in rows
    }
    outstanding_amount = sum(
        (
            by_status.get(status, (0, Decimal("0")))[1]
            for status in (
                InvoiceStatus.OUTSTANDING,
                InvoiceStatus.DUE_SOON,
                InvoiceStatus.OVERDUE,
            )
        ),
        Decimal("0"),
    )
    return InvoiceCountsResponse(
        total=sum(count for count, _ in by_status.values()),
        outstanding=by_status.get(InvoiceStatus.OUTSTANDING, (0, Decimal("0")))[0],
        due_soon=by_status.get(InvoiceStatus.DUE_SOON, (0, Decimal("0")))[0],
        overdue=by_status.get(InvoiceStatus.OVERDUE, (0, Decimal("0")))[0],
        paid=by_status.get(InvoiceStatus.PAID, (0, Decimal("0")))[0],
        outstanding_amount=outstanding_amount,
    )


def _require_owner(context: AuthContext) -> None:
    if context.membership.role != Role.OWNER:
        raise HTTPException(
            status_code=403,
            detail="Hanya owner yang dapat memutuskan approval.",
        )
