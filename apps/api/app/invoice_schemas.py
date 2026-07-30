import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models import (
    ApprovalStatus,
    InvoiceStatus,
    OutboxChannel,
    OutboxStatus,
    ReminderSource,
    ReminderStatus,
)


class CustomerResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    phone_masked: str | None


class OutboxMessageResponse(BaseModel):
    id: uuid.UUID
    channel: OutboxChannel
    recipient_masked: str
    template: str
    status: OutboxStatus
    attempt_count: int
    next_attempt_at: datetime | None
    last_error: str | None
    sent_at: datetime | None
    created_at: datetime


class ReminderResponse(BaseModel):
    id: uuid.UUID
    invoice_id: uuid.UUID
    sequence: int
    subject: str
    body: str
    source: ReminderSource
    status: ReminderStatus
    approval_id: uuid.UUID | None
    approval_status: ApprovalStatus | None
    decision_comment: str | None
    approved_at: datetime | None
    sent_at: datetime | None
    created_at: datetime
    updated_at: datetime
    outbox: OutboxMessageResponse | None


class InvoiceSummaryResponse(BaseModel):
    id: uuid.UUID
    invoice_number: str
    customer: CustomerResponse
    issue_date: date
    due_date: date
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    currency: str
    status: InvoiceStatus
    paid_at: datetime | None
    days_until_due: int
    latest_reminder_status: ReminderStatus | None
    created_at: datetime
    updated_at: datetime


class InvoiceDetailResponse(InvoiceSummaryResponse):
    reminders: list[ReminderResponse]
    audit_timeline: list[dict[str, object]]


class InvoiceCountsResponse(BaseModel):
    total: int
    outstanding: int
    due_soon: int
    overdue: int
    paid: int
    outstanding_amount: Decimal


class InvoiceListResponse(BaseModel):
    items: list[InvoiceSummaryResponse]
    total: int
    counts: InvoiceCountsResponse
    as_of: date


class SchedulerRunRequest(BaseModel):
    as_of: date | None = None
    force_fallback: bool = False


class SchedulerRunResponse(BaseModel):
    as_of: date
    businesses_scanned: int
    invoices_scanned: int
    status_updates: int
    drafts_created: int
    fallback_drafts: int


class ReminderDraftRequest(BaseModel):
    force_fallback: bool = False


class ReminderUpdateRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=5000)


class ReminderApproveRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=1000)


class ReminderRejectRequest(BaseModel):
    comment: str = Field(min_length=1, max_length=1000)
