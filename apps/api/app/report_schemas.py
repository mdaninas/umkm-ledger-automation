import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class ReportPeriod(BaseModel):
    start_date: date
    end_date: date
    previous_start_date: date
    previous_end_date: date
    label: str


class FinancialOverview(BaseModel):
    cash_balance: Decimal
    bank_balance: Decimal
    available_cash: Decimal
    income: Decimal
    expenses: Decimal
    net_cash_flow: Decimal
    profit_margin_percent: Decimal | None
    income_change_percent: Decimal | None
    expense_change_percent: Decimal | None


class CashflowPoint(BaseModel):
    date: date
    inflow: Decimal
    outflow: Decimal
    net: Decimal
    closing_balance: Decimal


class ExpenseBreakdownItem(BaseModel):
    account_code: str
    account_name: str
    amount: Decimal
    share_percent: Decimal


class OutstandingInvoiceItem(BaseModel):
    id: uuid.UUID
    invoice_number: str
    customer_name: str
    due_date: date
    days_overdue: int
    status: str
    total: Decimal
    source_url: str


class OperationalAlert(BaseModel):
    id: str
    alert_type: str
    severity: Literal["HIGH", "MEDIUM", "LOW"]
    title: str
    description: str
    amount: Decimal | None = None
    source_type: str
    source_id: uuid.UUID | None = None
    source_url: str
    rule: str


class AutomationMetrics(BaseModel):
    total_workflows: int
    succeeded: int
    failed: int
    waiting_review: int
    retry_count: int
    automation_rate_percent: Decimal
    median_latency_seconds: Decimal | None
    estimated_ai_cost_idr: Decimal


class ReconciliationMetrics(BaseModel):
    total_transactions: int
    matched_transactions: int
    unmatched_transactions: int
    match_rate_percent: Decimal


class DashboardReport(BaseModel):
    period: ReportPeriod
    generated_at: datetime
    overview: FinancialOverview
    cashflow: list[CashflowPoint]
    expense_breakdown: list[ExpenseBreakdownItem]
    outstanding_invoices: list[OutstandingInvoiceItem]
    alerts: list[OperationalAlert]
    automation: AutomationMetrics
    reconciliation: ReconciliationMetrics
    ledger_source_count: int


class WeeklyDigestResponse(BaseModel):
    id: uuid.UUID
    period_start: date
    period_end: date
    narrative: str
    snapshot: dict[str, object]
    source_refs: list[dict[str, object]]
    generated_at: datetime


class WeeklyDigestRunRequest(BaseModel):
    period_end: date | None = None
