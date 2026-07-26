import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import (
    AccountType,
    ApprovalStatus,
    DocumentSource,
    DocumentStatus,
    DocumentType,
    JournalStatus,
    RiskLevel,
    StepStatus,
    WorkflowStatus,
)


class LedgerAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    account_type: AccountType


class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: DocumentSource
    original_filename: str
    mime_type: str
    status: DocumentStatus
    document_type: DocumentType
    document_number: str | None
    vendor_name: str | None
    transaction_date: date | None
    currency: str
    total: Decimal | None
    extraction_confidence: Decimal | None
    duplicate_of_id: uuid.UUID | None
    duplicate_reason: str | None
    review_reason: str | None
    error_code: str | None
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentSummary]
    total: int


class ExtractionResponse(BaseModel):
    id: uuid.UUID
    provider: str
    model: str
    prompt_version: str
    schema_version: str
    normalized_output: dict[str, Any]
    field_confidences: dict[str, Any]
    warnings: list[str]
    latency_ms: int
    usage: dict[str, Any]
    created_at: datetime


class WorkflowStepResponse(BaseModel):
    id: uuid.UUID
    step_name: str
    sequence: int
    status: StepStatus
    output_summary: dict[str, Any]
    error_code: str | None
    started_at: datetime | None
    finished_at: datetime | None


class WorkflowRunResponse(BaseModel):
    id: uuid.UUID
    status: WorkflowStatus
    correlation_id: str
    retry_count: int
    error_code: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    steps: list[WorkflowStepResponse]


class JournalLineResponse(BaseModel):
    id: uuid.UUID
    account: LedgerAccountResponse
    debit: Decimal
    credit: Decimal
    memo: str | None


class JournalEntryResponse(BaseModel):
    id: uuid.UUID
    status: JournalStatus
    entry_date: date
    description: str
    posted_at: datetime | None
    lines: list[JournalLineResponse]
    total_debit: Decimal
    total_credit: Decimal
    balanced: bool


class ApprovalResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    journal_entry_id: uuid.UUID | None
    action_type: str
    reason: str
    risk_level: RiskLevel
    status: ApprovalStatus
    requested_at: datetime
    decided_by: uuid.UUID | None
    decision_comment: str | None
    decided_at: datetime | None


class AuditEventResponse(BaseModel):
    id: uuid.UUID
    actor_type: str
    actor_id: uuid.UUID | None
    action: str
    correlation_id: str
    metadata: dict[str, Any]
    created_at: datetime


class DocumentDetail(DocumentSummary):
    sha256: str
    due_date: date | None
    subtotal: Decimal | None
    tax: Decimal | None
    payment_method: str | None
    validation_errors: list[dict[str, Any]]
    validation_warnings: list[dict[str, Any]]
    proposed_account: LedgerAccountResponse | None
    final_account: LedgerAccountResponse | None
    latest_extraction: ExtractionResponse | None
    latest_workflow: WorkflowRunResponse | None
    journal: JournalEntryResponse | None
    approval: ApprovalResponse | None
    audit_timeline: list[AuditEventResponse]


class DocumentReviewRequest(BaseModel):
    document_type: DocumentType | None = None
    document_number: str | None = Field(default=None, max_length=120)
    vendor_name: str | None = Field(default=None, max_length=255)
    transaction_date: date | None = None
    due_date: date | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    payment_method: str | None = Field(default=None, max_length=80)
    final_account_id: uuid.UUID | None = None
    duplicate_decision: Literal["DUPLICATE", "DIFFERENT_TRANSACTION"] | None = None
    review_comment: str | None = Field(default=None, max_length=1000)


class PostDocumentRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=1000)


class RejectApprovalRequest(BaseModel):
    comment: str = Field(min_length=1, max_length=1000)


class DashboardSummary(BaseModel):
    posted_journal_count: int
    draft_journal_count: int
    needs_review_count: int
    posted_income: Decimal
    posted_expenses: Decimal
    cash_balance: Decimal
    bank_balance: Decimal
