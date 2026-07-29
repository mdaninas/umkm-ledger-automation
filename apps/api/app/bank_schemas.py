import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import (
    BankDirection,
    BankImportStatus,
    BankTransactionStatus,
    DocumentStatus,
    DocumentType,
    ReconciliationStatus,
)


class BankColumnMapping(BaseModel):
    date: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=120)
    amount: str | None = Field(default=None, min_length=1, max_length=120)
    debit: str | None = Field(default=None, min_length=1, max_length=120)
    credit: str | None = Field(default=None, min_length=1, max_length=120)
    reference: str | None = Field(default=None, min_length=1, max_length=120)
    date_format: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def validate_amount_columns(self) -> "BankColumnMapping":
        uses_signed_amount = self.amount is not None
        uses_split_amount = self.debit is not None or self.credit is not None
        if uses_signed_amount == uses_split_amount:
            raise ValueError(
                "Map either one signed amount column or separate debit and credit columns."
            )
        if uses_split_amount and (self.debit is None or self.credit is None):
            raise ValueError("Both debit and credit columns must be mapped.")
        return self


class BankImportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    sha256: str
    column_mapping: dict[str, Any]
    status: BankImportStatus
    row_count: int
    imported_count: int
    duplicate_count: int
    error_count: int
    row_errors: list[dict[str, Any]]
    created_at: datetime
    duplicate_file: bool = False


class BankImportListResponse(BaseModel):
    items: list[BankImportResponse]
    total: int


class ReconciliationSourceResponse(BaseModel):
    id: uuid.UUID
    document_type: DocumentType
    document_number: str | None
    vendor_name: str | None
    transaction_date: date | None
    total: Decimal | None
    currency: str
    status: DocumentStatus


class ReconciliationResponse(BaseModel):
    id: uuid.UUID
    bank_transaction_id: uuid.UUID
    source_type: str
    source: ReconciliationSourceResponse
    score: Decimal
    score_breakdown: dict[str, Any]
    status: ReconciliationStatus
    decided_by: uuid.UUID | None
    decision_comment: str | None
    decided_at: datetime | None
    created_at: datetime


class BankTransactionResponse(BaseModel):
    id: uuid.UUID
    bank_import_id: uuid.UUID
    row_number: int
    transaction_date: date
    description: str
    amount: Decimal
    direction: BankDirection
    reference: str | None
    status: BankTransactionStatus
    created_at: datetime
    candidates: list[ReconciliationResponse]


class BankTransactionCounts(BaseModel):
    total: int
    unmatched: int
    suggested: int
    matched: int


class BankTransactionListResponse(BaseModel):
    items: list[BankTransactionResponse]
    total: int
    counts: BankTransactionCounts


class ReconciliationListResponse(BaseModel):
    items: list[ReconciliationResponse]
    total: int


class ReconciliationDecisionRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=1000)


class ReconciliationRejectRequest(BaseModel):
    comment: str = Field(min_length=1, max_length=1000)
