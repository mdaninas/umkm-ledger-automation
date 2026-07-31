import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from statistics import median
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session, selectinload

from app.audit import record_audit_event
from app.invoice_service import business_local_date, format_idr
from app.models import (
    AccountType,
    ActorType,
    BankTransaction,
    BankTransactionStatus,
    Business,
    Document,
    DocumentExtraction,
    DocumentStatus,
    Invoice,
    InvoiceStatus,
    JournalEntry,
    JournalLine,
    JournalStatus,
    LedgerAccount,
    Reconciliation,
    ReconciliationStatus,
    WeeklyDigest,
    WorkflowRun,
    WorkflowStatus,
)
from app.report_schemas import (
    AutomationMetrics,
    CashflowPoint,
    DashboardReport,
    ExpenseBreakdownItem,
    FinancialOverview,
    OperationalAlert,
    OutstandingInvoiceItem,
    ReconciliationMetrics,
    ReportPeriod,
    WeeklyDigestResponse,
)

ZERO = Decimal("0.00")
PERCENT = Decimal("100")
TWOPLACES = Decimal("0.01")
ACTIVE_RECONCILIATION_STATUSES = (
    ReconciliationStatus.AUTO_MATCHED,
    ReconciliationStatus.CONFIRMED,
)


def resolve_report_period(
    business: Business,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> ReportPeriod:
    local_today = business_local_date(business)
    resolved_end = end_date or local_today
    resolved_start = start_date or resolved_end.replace(day=1)
    if resolved_start > resolved_end:
        raise ValueError("Tanggal mulai tidak boleh setelah tanggal akhir.")
    if (resolved_end - resolved_start).days > 366:
        raise ValueError("Rentang laporan maksimum adalah 367 hari.")
    day_count = (resolved_end - resolved_start).days + 1
    previous_end = resolved_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=day_count - 1)
    return ReportPeriod(
        start_date=resolved_start,
        end_date=resolved_end,
        previous_start_date=previous_start,
        previous_end_date=previous_end,
        label=_period_label(resolved_start, resolved_end),
    )


def build_dashboard_report(
    session: Session,
    *,
    business: Business,
    start_date: date | None = None,
    end_date: date | None = None,
) -> DashboardReport:
    period = resolve_report_period(
        business,
        start_date=start_date,
        end_date=end_date,
    )
    period_rows = _ledger_rows(
        session,
        business_id=business.id,
        start_date=period.start_date,
        end_date=period.end_date,
    )
    previous_rows = _ledger_rows(
        session,
        business_id=business.id,
        start_date=period.previous_start_date,
        end_date=period.previous_end_date,
    )
    balance_rows = _ledger_rows(
        session,
        business_id=business.id,
        end_date=period.end_date,
    )
    opening_rows = _ledger_rows(
        session,
        business_id=business.id,
        end_date=period.start_date - timedelta(days=1),
    )

    current = _financial_totals(period_rows)
    previous = _financial_totals(previous_rows)
    balances = _account_balances(balance_rows)
    available_cash = balances["cash"] + balances["bank"]
    cashflow = _cashflow_points(
        period,
        period_rows,
        opening_balance=_account_balances(opening_rows)["cash_bank"],
    )
    breakdown = _expense_breakdown(period_rows, current["expenses"])
    previous_breakdown = _expense_amounts(previous_rows)
    outstanding = _outstanding_invoices(
        session,
        business_id=business.id,
        as_of=period.end_date,
    )
    automation = _automation_metrics(
        session,
        business_id=business.id,
        period=period,
    )
    reconciliation = _reconciliation_metrics(
        session,
        business_id=business.id,
        period=period,
    )
    alerts = _operational_alerts(
        session,
        business_id=business.id,
        period=period,
        expense_breakdown=breakdown,
        previous_expenses=previous_breakdown,
        outstanding_invoices=outstanding,
    )

    return DashboardReport(
        period=period,
        generated_at=datetime.now(UTC),
        overview=FinancialOverview(
            cash_balance=balances["cash"],
            bank_balance=balances["bank"],
            available_cash=available_cash,
            income=current["income"],
            expenses=current["expenses"],
            net_cash_flow=current["cash_flow"],
            profit_margin_percent=_percentage(
                current["income"] - current["expenses"],
                current["income"],
            ),
            income_change_percent=_change_percentage(
                current["income"], previous["income"]
            ),
            expense_change_percent=_change_percentage(
                current["expenses"], previous["expenses"]
            ),
        ),
        cashflow=cashflow,
        expense_breakdown=breakdown,
        outstanding_invoices=outstanding,
        alerts=alerts,
        automation=automation,
        reconciliation=reconciliation,
        ledger_source_count=len({row["journal_id"] for row in period_rows}),
    )


def ledger_export_rows(
    session: Session,
    *,
    business_id: uuid.UUID,
    start_date: date,
    end_date: date,
) -> list[dict[str, str]]:
    rows = _ledger_rows(
        session,
        business_id=business_id,
        start_date=start_date,
        end_date=end_date,
    )
    return [
        {
            "tanggal": row["entry_date"].isoformat(),
            "journal_id": str(row["journal_id"]),
            "deskripsi": row["description"],
            "kode_akun": row["account_code"],
            "nama_akun": row["account_name"],
            "debit": f"{_money(row['debit']):.2f}",
            "kredit": f"{_money(row['credit']):.2f}",
            "dokumen_id": str(row["document_id"]),
            "nomor_dokumen": row["document_number"] or "",
            "vendor": row["vendor_name"] or "",
        }
        for row in rows
    ]


def generate_weekly_digest(
    session: Session,
    *,
    business: Business,
    correlation_id: str,
    period_end: date | None = None,
) -> WeeklyDigest:
    resolved_end = period_end or (business_local_date(business) - timedelta(days=1))
    resolved_start = resolved_end - timedelta(days=6)
    existing = session.scalar(
        select(WeeklyDigest).where(
            WeeklyDigest.business_id == business.id,
            WeeklyDigest.period_start == resolved_start,
            WeeklyDigest.period_end == resolved_end,
        )
    )
    if existing is not None:
        return existing

    report = build_dashboard_report(
        session,
        business=business,
        start_date=resolved_start,
        end_date=resolved_end,
    )
    overdue_count = sum(
        1 for invoice in report.outstanding_invoices if invoice.days_overdue > 0
    )
    narrative = (
        f"Pada {report.period.label}, pendapatan tercatat "
        f"{format_idr(report.overview.income, business.currency)} dan beban "
        f"{format_idr(report.overview.expenses, business.currency)}. "
        f"Arus kas bersih periode ini "
        f"{format_idr(report.overview.net_cash_flow, business.currency)}. "
        f"Terdapat {overdue_count} invoice melewati jatuh tempo dan "
        f"{len(report.alerts)} perhatian operasional. Tingkat keberhasilan "
        f"otomatisasi {report.automation.automation_rate_percent:.1f}%."
    )
    digest = WeeklyDigest(
        business_id=business.id,
        period_start=resolved_start,
        period_end=resolved_end,
        narrative=narrative,
        snapshot=report.model_dump(mode="json"),
        source_refs=[
            {
                "type": "ledger",
                "count": report.ledger_source_count,
                "path": (
                    "/api/v1/reports/export.csv"
                    f"?start_date={resolved_start.isoformat()}"
                    f"&end_date={resolved_end.isoformat()}"
                ),
            },
            {
                "type": "invoice",
                "count": len(report.outstanding_invoices),
                "path": "/api/v1/invoices",
            },
            {
                "type": "workflow",
                "count": report.automation.total_workflows,
                "path": "/api/v1/reports/dashboard",
            },
        ],
    )
    session.add(digest)
    session.flush()
    record_audit_event(
        session,
        business_id=business.id,
        actor_type=ActorType.SYSTEM,
        actor_id=None,
        action="report.weekly_digest.generated",
        entity_type="weekly_digest",
        entity_id=digest.id,
        correlation_id=correlation_id,
        metadata={
            "period_start": resolved_start.isoformat(),
            "period_end": resolved_end.isoformat(),
            "ledger_source_count": report.ledger_source_count,
        },
    )
    session.commit()
    return digest


def serialize_weekly_digest(digest: WeeklyDigest) -> WeeklyDigestResponse:
    return WeeklyDigestResponse(
        id=digest.id,
        period_start=digest.period_start,
        period_end=digest.period_end,
        narrative=digest.narrative,
        snapshot=digest.snapshot,
        source_refs=digest.source_refs,
        generated_at=digest.generated_at,
    )


def _ledger_rows(
    session: Session,
    *,
    business_id: uuid.UUID,
    end_date: date,
    start_date: date | None = None,
) -> Sequence[RowMapping]:
    filters = [
        JournalEntry.business_id == business_id,
        JournalEntry.status == JournalStatus.POSTED,
        JournalEntry.entry_date <= end_date,
    ]
    if start_date is not None:
        filters.append(JournalEntry.entry_date >= start_date)
    return session.execute(
        select(
            JournalEntry.id.label("journal_id"),
            JournalEntry.entry_date,
            JournalEntry.description,
            JournalEntry.document_id,
            Document.document_number,
            Document.vendor_name,
            LedgerAccount.code.label("account_code"),
            LedgerAccount.name.label("account_name"),
            LedgerAccount.account_type,
            JournalLine.debit,
            JournalLine.credit,
        )
        .join(JournalLine, JournalLine.journal_entry_id == JournalEntry.id)
        .join(LedgerAccount, LedgerAccount.id == JournalLine.ledger_account_id)
        .join(Document, Document.id == JournalEntry.document_id)
        .where(*filters)
        .order_by(JournalEntry.entry_date, JournalEntry.id, LedgerAccount.code)
    ).mappings().all()


def _financial_totals(rows: Sequence[RowMapping]) -> dict[str, Decimal]:
    totals = {"income": ZERO, "expenses": ZERO, "cash_flow": ZERO}
    for row in rows:
        debit = _money(row["debit"])
        credit = _money(row["credit"])
        account_type = row["account_type"]
        if account_type == AccountType.REVENUE:
            totals["income"] += credit - debit
        elif account_type == AccountType.EXPENSE:
            totals["expenses"] += debit - credit
        if row["account_code"] in {"1000", "1010"}:
            totals["cash_flow"] += debit - credit
    return {key: _money(value) for key, value in totals.items()}


def _account_balances(rows: Sequence[RowMapping]) -> dict[str, Decimal]:
    cash = bank = ZERO
    for row in rows:
        movement = _money(row["debit"]) - _money(row["credit"])
        if row["account_code"] == "1000":
            cash += movement
        elif row["account_code"] == "1010":
            bank += movement
    return {
        "cash": _money(cash),
        "bank": _money(bank),
        "cash_bank": _money(cash + bank),
    }


def _cashflow_points(
    period: ReportPeriod,
    rows: Sequence[RowMapping],
    *,
    opening_balance: Decimal,
) -> list[CashflowPoint]:
    daily: dict[date, dict[str, Decimal]] = defaultdict(
        lambda: {"inflow": ZERO, "outflow": ZERO}
    )
    for row in rows:
        if row["account_code"] not in {"1000", "1010"}:
            continue
        movement = _money(row["debit"]) - _money(row["credit"])
        if movement >= ZERO:
            daily[row["entry_date"]]["inflow"] += movement
        else:
            daily[row["entry_date"]]["outflow"] += -movement
    points: list[CashflowPoint] = []
    closing = opening_balance
    current = period.start_date
    while current <= period.end_date:
        inflow = _money(daily[current]["inflow"])
        outflow = _money(daily[current]["outflow"])
        net = _money(inflow - outflow)
        closing = _money(closing + net)
        points.append(
            CashflowPoint(
                date=current,
                inflow=inflow,
                outflow=outflow,
                net=net,
                closing_balance=closing,
            )
        )
        current += timedelta(days=1)
    return points


def _expense_amounts(rows: Sequence[RowMapping]) -> dict[str, Decimal]:
    amounts: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for row in rows:
        if row["account_type"] == AccountType.EXPENSE:
            amounts[row["account_code"]] += _money(row["debit"]) - _money(
                row["credit"]
            )
    return {key: _money(value) for key, value in amounts.items()}


def _expense_breakdown(
    rows: Sequence[RowMapping],
    total_expenses: Decimal,
) -> list[ExpenseBreakdownItem]:
    amounts = _expense_amounts(rows)
    names = {
        row["account_code"]: row["account_name"]
        for row in rows
        if row["account_type"] == AccountType.EXPENSE
    }
    return [
        ExpenseBreakdownItem(
            account_code=code,
            account_name=names[code],
            amount=amount,
            share_percent=_percentage(amount, total_expenses) or ZERO,
        )
        for code, amount in sorted(
            amounts.items(), key=lambda item: item[1], reverse=True
        )
        if amount > ZERO
    ]


def _outstanding_invoices(
    session: Session,
    *,
    business_id: uuid.UUID,
    as_of: date,
) -> list[OutstandingInvoiceItem]:
    invoices = list(
        session.scalars(
            select(Invoice)
            .options(selectinload(Invoice.customer))
            .where(
                Invoice.business_id == business_id,
                Invoice.status != InvoiceStatus.PAID,
            )
            .order_by(Invoice.due_date, Invoice.total.desc())
        )
    )
    items: list[OutstandingInvoiceItem] = []
    for invoice in invoices:
        items.append(
            OutstandingInvoiceItem(
                id=invoice.id,
                invoice_number=invoice.invoice_number,
                customer_name=invoice.customer.name,
                due_date=invoice.due_date,
                days_overdue=max(0, (as_of - invoice.due_date).days),
                status=invoice.status.value,
                total=_money(invoice.total),
                source_url=f"/invoices?invoice={invoice.id}",
            )
        )
    return items[:8]


def _automation_metrics(
    session: Session,
    *,
    business_id: uuid.UUID,
    period: ReportPeriod,
) -> AutomationMetrics:
    start_at = datetime.combine(period.start_date, time.min, tzinfo=UTC)
    end_at = datetime.combine(period.end_date + timedelta(days=1), time.min, tzinfo=UTC)
    workflows = list(
        session.scalars(
            select(WorkflowRun).where(
                WorkflowRun.business_id == business_id,
                WorkflowRun.created_at >= start_at,
                WorkflowRun.created_at < end_at,
            )
        )
    )
    succeeded = sum(run.status == WorkflowStatus.SUCCEEDED for run in workflows)
    failed = sum(
        run.status in {WorkflowStatus.FAILED, WorkflowStatus.DEAD_LETTER}
        for run in workflows
    )
    waiting = sum(
        run.status == WorkflowStatus.WAITING_FOR_APPROVAL for run in workflows
    )
    durations = [
        (run.finished_at - run.started_at).total_seconds()
        for run in workflows
        if run.finished_at is not None
        and run.started_at is not None
        and run.finished_at >= run.started_at
    ]
    extractions = list(
        session.scalars(
            select(DocumentExtraction)
            .join(Document, Document.id == DocumentExtraction.document_id)
            .where(
                Document.business_id == business_id,
                DocumentExtraction.created_at >= start_at,
                DocumentExtraction.created_at < end_at,
            )
        )
    )
    estimated_cost = sum(
        (_money(extraction.usage.get("estimated_cost_idr", 0)) for extraction in extractions),
        ZERO,
    )
    total = len(workflows)
    return AutomationMetrics(
        total_workflows=total,
        succeeded=succeeded,
        failed=failed,
        waiting_review=waiting,
        retry_count=sum(run.retry_count for run in workflows),
        automation_rate_percent=_percentage(Decimal(succeeded), Decimal(total)) or ZERO,
        median_latency_seconds=(
            _money(Decimal(str(median(durations)))) if durations else None
        ),
        estimated_ai_cost_idr=_money(estimated_cost),
    )


def _reconciliation_metrics(
    session: Session,
    *,
    business_id: uuid.UUID,
    period: ReportPeriod,
) -> ReconciliationMetrics:
    transactions = list(
        session.scalars(
            select(BankTransaction).where(
                BankTransaction.business_id == business_id,
                BankTransaction.transaction_date >= period.start_date,
                BankTransaction.transaction_date <= period.end_date,
            )
        )
    )
    matched = sum(
        transaction.status
        in {BankTransactionStatus.AUTO_MATCHED, BankTransactionStatus.CONFIRMED}
        for transaction in transactions
    )
    total = len(transactions)
    return ReconciliationMetrics(
        total_transactions=total,
        matched_transactions=matched,
        unmatched_transactions=total - matched,
        match_rate_percent=_percentage(Decimal(matched), Decimal(total)) or ZERO,
    )


def _operational_alerts(
    session: Session,
    *,
    business_id: uuid.UUID,
    period: ReportPeriod,
    expense_breakdown: list[ExpenseBreakdownItem],
    previous_expenses: dict[str, Decimal],
    outstanding_invoices: list[OutstandingInvoiceItem],
) -> list[OperationalAlert]:
    alerts: list[OperationalAlert] = []
    overdue = [invoice for invoice in outstanding_invoices if invoice.days_overdue > 0]
    if overdue:
        total = sum((invoice.total for invoice in overdue), ZERO)
        alerts.append(
            OperationalAlert(
                id="overdue-invoices",
                alert_type="OVERDUE_INVOICE",
                severity="HIGH",
                title=f"{len(overdue)} invoice melewati jatuh tempo",
                description=f"Total piutang terlambat {format_idr(total, 'IDR')}.",
                amount=total,
                source_type="INVOICE",
                source_id=overdue[0].id,
                source_url="/invoices?status=OVERDUE",
                rule="Invoice belum dibayar setelah tanggal jatuh tempo.",
            )
        )

    review_documents = list(
        session.scalars(
            select(Document).where(
                Document.business_id == business_id,
                Document.status.in_(
                    [DocumentStatus.NEEDS_REVIEW, DocumentStatus.READY_TO_POST]
                ),
            )
        )
    )
    if review_documents:
        amount = sum((_money(document.total or ZERO) for document in review_documents), ZERO)
        alerts.append(
            OperationalAlert(
                id="document-review-queue",
                alert_type="DOCUMENT_REVIEW",
                severity="MEDIUM",
                title=f"{len(review_documents)} dokumen menunggu keputusan",
                description=f"Nilai gabungan {format_idr(amount, 'IDR')} belum final.",
                amount=amount,
                source_type="DOCUMENT",
                source_id=review_documents[0].id,
                source_url="/inbox?status=NEEDS_REVIEW",
                rule="Dokumen perlu review tidak boleh masuk laporan final.",
            )
        )

    duplicate = session.scalar(
        select(Document)
        .where(
            Document.business_id == business_id,
            Document.duplicate_of_id.is_not(None),
        )
        .order_by(Document.created_at.desc())
    )
    if duplicate is not None:
        alerts.append(
            OperationalAlert(
                id=f"duplicate:{duplicate.id}",
                alert_type="POSSIBLE_DUPLICATE",
                severity="MEDIUM",
                title="Kemungkinan dokumen duplikat",
                description=duplicate.duplicate_reason or "Fingerprint dokumen cocok.",
                amount=_money(duplicate.total) if duplicate.total is not None else None,
                source_type="DOCUMENT",
                source_id=duplicate.id,
                source_url=f"/inbox/{duplicate.id}",
                rule="Hash atau fingerprint semantik cocok dengan dokumen lain.",
            )
        )

    cutoff = period.end_date - timedelta(days=7)
    unmatched = session.scalar(
        select(BankTransaction)
        .where(
            BankTransaction.business_id == business_id,
            BankTransaction.status == BankTransactionStatus.UNMATCHED,
            BankTransaction.transaction_date <= cutoff,
        )
        .order_by(BankTransaction.transaction_date)
    )
    if unmatched is not None:
        alerts.append(
            OperationalAlert(
                id=f"unmatched-bank:{unmatched.id}",
                alert_type="UNMATCHED_BANK_TRANSACTION",
                severity="MEDIUM",
                title="Transaksi bank belum memiliki dokumen",
                description=(
                    f"{unmatched.description} belum cocok selama lebih dari 7 hari."
                ),
                amount=_money(unmatched.amount),
                source_type="BANK_TRANSACTION",
                source_id=unmatched.id,
                source_url=f"/banking?status=UNMATCHED&transaction={unmatched.id}",
                rule="Mutasi bank tidak memiliki sumber setelah 7 hari.",
            )
        )

    mismatch = _amount_mismatch_alert(session, business_id=business_id)
    if mismatch is not None:
        alerts.append(mismatch)

    for item in expense_breakdown:
        baseline = previous_expenses.get(item.account_code, ZERO)
        if baseline <= ZERO:
            continue
        change = _change_percentage(item.amount, baseline)
        if change is not None and change >= Decimal("25"):
            alerts.append(
                OperationalAlert(
                    id=f"expense-spike:{item.account_code}",
                    alert_type="EXPENSE_SPIKE",
                    severity="MEDIUM",
                    title=f"{item.account_name} naik {change:.0f}%",
                    description=(
                        f"Beban periode ini {format_idr(item.amount, 'IDR')} "
                        "dibanding periode sebelumnya."
                    ),
                    amount=item.amount,
                    source_type="LEDGER_ACCOUNT",
                    source_id=None,
                    source_url=f"/dashboard#expense-{item.account_code}",
                    rule="Beban kategori naik minimal 25% dari periode pembanding.",
                )
            )
            break

    severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    return sorted(alerts, key=lambda alert: (severity_order[alert.severity], alert.title))[:7]


def _amount_mismatch_alert(
    session: Session,
    *,
    business_id: uuid.UUID,
) -> OperationalAlert | None:
    candidates = session.execute(
        select(Reconciliation, BankTransaction)
        .join(BankTransaction, BankTransaction.id == Reconciliation.bank_transaction_id)
        .where(
            Reconciliation.business_id == business_id,
            Reconciliation.status.in_(ACTIVE_RECONCILIATION_STATUSES),
            Reconciliation.source_type == "DOCUMENT",
        )
    ).all()
    for reconciliation, transaction in candidates:
        document = session.scalar(
            select(Document).where(
                Document.business_id == business_id,
                Document.id == reconciliation.source_id,
            )
        )
        if document is None or document.total is None:
            continue
        difference = abs(_money(document.total) - _money(transaction.amount))
        if difference > ZERO:
            return OperationalAlert(
                id=f"amount-mismatch:{reconciliation.id}",
                alert_type="AMOUNT_MISMATCH",
                severity="HIGH",
                title="Nominal dokumen berbeda dari pembayaran",
                description=f"Selisih tercatat {format_idr(difference, 'IDR')}.",
                amount=difference,
                source_type="RECONCILIATION",
                source_id=reconciliation.id,
                source_url=f"/banking?transaction={transaction.id}",
                rule="Nominal dokumen harus sama dengan mutasi yang dicocokkan.",
            )
    return None


def _period_label(start: date, end: date) -> str:
    months = (
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "Mei",
        "Jun",
        "Jul",
        "Agu",
        "Sep",
        "Okt",
        "Nov",
        "Des",
    )
    if start.year == end.year and start.month == end.month:
        return f"{start.day}–{end.day} {months[end.month - 1]} {end.year}"
    return (
        f"{start.day} {months[start.month - 1]} {start.year}–"
        f"{end.day} {months[end.month - 1]} {end.year}"
    )


def _money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _percentage(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == ZERO:
        return None
    return (numerator / denominator * PERCENT).quantize(
        TWOPLACES, rounding=ROUND_HALF_UP
    )


def _change_percentage(current: Decimal, previous: Decimal) -> Decimal | None:
    if previous == ZERO:
        return None
    return _percentage(current - previous, previous)
