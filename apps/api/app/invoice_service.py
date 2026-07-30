import smtplib
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from email.message import EmailMessage
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.audit import record_audit_event
from app.config import Settings
from app.models import (
    ActorType,
    ApprovalRequest,
    ApprovalStatus,
    AuditEvent,
    Business,
    Invoice,
    InvoiceReminder,
    InvoiceStatus,
    OutboxChannel,
    OutboxMessage,
    OutboxStatus,
    ReminderSource,
    ReminderStatus,
    RiskLevel,
)
from app.security import AuthContext

EmailSender = Callable[[OutboxMessage, Settings], None]
ACTIVE_REMINDER_STATUSES = {
    ReminderStatus.PENDING_APPROVAL,
    ReminderStatus.APPROVED,
    ReminderStatus.QUEUED,
}


def business_local_date(
    business: Business,
    *,
    now: datetime | None = None,
) -> date:
    current = now or datetime.now(UTC)
    try:
        timezone = ZoneInfo(business.timezone)
    except ZoneInfoNotFoundError:
        timezone = ZoneInfo("UTC")
    return current.astimezone(timezone).date()


def scan_invoices(
    session: Session,
    *,
    settings: Settings,
    correlation_id: str,
    business_id: uuid.UUID | None = None,
    as_of: date | None = None,
    force_fallback: bool = False,
) -> dict[str, Any]:
    business_query = select(Business)
    if business_id:
        business_query = business_query.where(Business.id == business_id)
    businesses = list(session.scalars(business_query.order_by(Business.created_at)))
    invoices_scanned = status_updates = drafts_created = fallback_drafts = 0
    effective_as_of = as_of

    for business in businesses:
        local_as_of = as_of or business_local_date(business)
        effective_as_of = effective_as_of or local_as_of
        invoices = list(
            session.scalars(
                select(Invoice)
                .options(
                    selectinload(Invoice.customer),
                    selectinload(Invoice.reminders),
                )
                .where(Invoice.business_id == business.id)
                .order_by(Invoice.due_date, Invoice.created_at)
            )
        )
        for invoice in invoices:
            invoices_scanned += 1
            previous_status = invoice.status
            next_status = status_for_date(
                invoice,
                as_of=local_as_of,
                due_soon_days=settings.reminder_due_soon_days,
            )
            if next_status != previous_status:
                invoice.status = next_status
                status_updates += 1
                record_audit_event(
                    session,
                    business_id=business.id,
                    actor_type=ActorType.SYSTEM,
                    actor_id=None,
                    action="invoice.status_updated",
                    entity_type="invoice",
                    entity_id=invoice.id,
                    correlation_id=correlation_id,
                    metadata={
                        "before": previous_status.value,
                        "after": next_status.value,
                        "as_of": local_as_of.isoformat(),
                        "business_timezone": business.timezone,
                    },
                )

            if next_status == InvoiceStatus.OVERDUE and can_create_reminder(
                invoice,
                settings=settings,
            ):
                reminder = create_reminder(
                    session,
                    invoice=invoice,
                    settings=settings,
                    correlation_id=correlation_id,
                    actor_type=ActorType.SYSTEM,
                    actor_id=None,
                    force_fallback=force_fallback,
                )
                drafts_created += 1
                if reminder.source == ReminderSource.DETERMINISTIC_FALLBACK:
                    fallback_drafts += 1

    session.commit()
    return {
        "as_of": effective_as_of or date.today(),
        "businesses_scanned": len(businesses),
        "invoices_scanned": invoices_scanned,
        "status_updates": status_updates,
        "drafts_created": drafts_created,
        "fallback_drafts": fallback_drafts,
    }


def status_for_date(
    invoice: Invoice,
    *,
    as_of: date,
    due_soon_days: int,
) -> InvoiceStatus:
    if invoice.status == InvoiceStatus.PAID:
        return InvoiceStatus.PAID
    if invoice.due_date < as_of:
        return InvoiceStatus.OVERDUE
    if invoice.due_date <= as_of + timedelta(days=due_soon_days):
        return InvoiceStatus.DUE_SOON
    return InvoiceStatus.OUTSTANDING


def can_create_reminder(invoice: Invoice, *, settings: Settings) -> bool:
    if any(reminder.status in ACTIVE_REMINDER_STATUSES for reminder in invoice.reminders):
        return False
    if not invoice.reminders:
        return True
    latest = max(invoice.reminders, key=lambda reminder: reminder.created_at)
    latest_at = _aware_utc(latest.sent_at or latest.created_at)
    return datetime.now(UTC) - latest_at >= timedelta(
        days=settings.reminder_cooldown_days
    )


def create_reminder(
    session: Session,
    *,
    invoice: Invoice,
    settings: Settings,
    correlation_id: str,
    actor_type: ActorType,
    actor_id: uuid.UUID | None,
    force_fallback: bool,
) -> InvoiceReminder:
    if invoice.status != InvoiceStatus.OVERDUE:
        raise HTTPException(
            status_code=409,
            detail="Reminder hanya dapat dibuat untuk invoice overdue.",
        )
    if not can_create_reminder(invoice, settings=settings):
        raise HTTPException(
            status_code=409,
            detail=(
                "Reminder aktif atau reminder dalam masa cooldown masih ada untuk "
                "invoice ini."
            ),
        )

    sequence = (
        session.scalar(
            select(func.max(InvoiceReminder.sequence)).where(
                InvoiceReminder.invoice_id == invoice.id
            )
        )
        or 0
    ) + 1
    subject, body, source = compose_reminder(
        invoice,
        force_fallback=force_fallback,
        settings=settings,
    )
    reminder = InvoiceReminder(
        business_id=invoice.business_id,
        invoice_id=invoice.id,
        sequence=sequence,
        subject=subject,
        body=body,
        source=source,
        status=ReminderStatus.PENDING_APPROVAL,
        created_by=actor_id,
    )
    session.add(reminder)
    session.flush()
    approval = ApprovalRequest(
        business_id=invoice.business_id,
        workflow_run_id=None,
        document_id=None,
        entity_type="INVOICE_REMINDER",
        entity_id=reminder.id,
        journal_entry_id=None,
        action_type="SEND_REMINDER",
        payload={
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "recipient_masked": mask_email(invoice.customer.email),
            "before": None,
            "after": {"subject": subject, "body": body},
            "source": source.value,
        },
        reason=(
            f"Kirim pengingat invoice {invoice.invoice_number} kepada "
            f"{invoice.customer.name}."
        ),
        risk_level=RiskLevel.MEDIUM,
        status=ApprovalStatus.PENDING,
    )
    session.add(approval)
    record_audit_event(
        session,
        business_id=invoice.business_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action="invoice.reminder_drafted",
        entity_type="invoice_reminder",
        entity_id=reminder.id,
        correlation_id=correlation_id,
        metadata={
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "sequence": sequence,
            "source": source.value,
            "approval_required": True,
        },
    )
    session.flush()
    return reminder


def compose_reminder(
    invoice: Invoice,
    *,
    force_fallback: bool,
    settings: Settings,
) -> tuple[str, str, ReminderSource]:
    try:
        opening = _ai_assisted_opening(
            customer_name=invoice.customer.name,
            force_failure=force_fallback,
            provider=settings.ai_provider,
        )
        source = ReminderSource.AI_ASSISTED
    except RuntimeError:
        opening = "Semoga Bapak/Ibu dalam keadaan baik."
        source = ReminderSource.DETERMINISTIC_FALLBACK

    amount = format_idr(invoice.total, invoice.currency)
    due_date = format_indonesian_date(invoice.due_date)
    subject = f"Pengingat pembayaran {invoice.invoice_number}"
    body = (
        f"Yth. {invoice.customer.name},\n\n"
        f"{opening}\n\n"
        f"Kami mengingatkan bahwa invoice {invoice.invoice_number} senilai "
        f"{amount} telah jatuh tempo pada {due_date}. Mohon informasikan "
        "apabila pembayaran sudah dilakukan.\n\n"
        "Terima kasih atas perhatian dan kerja samanya.\n\n"
        "Hormat kami,\n"
        "Tim Keuangan Kopi Arunika"
    )
    return subject, body, source


def _ai_assisted_opening(
    *,
    customer_name: str,
    force_failure: bool,
    provider: str,
) -> str:
    if force_failure or provider.lower() != "mock":
        raise RuntimeError("Reminder copy provider unavailable.")
    first_name = customer_name.split()[0]
    return (
        f"Semoga tim {first_name} dalam keadaan baik. "
        "Kami ingin menindaklanjuti pembayaran yang masih tercatat terbuka."
    )


def update_reminder(
    session: Session,
    *,
    reminder: InvoiceReminder,
    context: AuthContext,
    subject: str,
    body: str,
    correlation_id: str,
) -> InvoiceReminder:
    if reminder.status != ReminderStatus.PENDING_APPROVAL:
        raise HTTPException(
            status_code=409,
            detail="Hanya draft yang menunggu approval yang dapat diubah.",
        )
    before = {"subject": reminder.subject, "body": reminder.body}
    reminder.subject = subject.strip()
    reminder.body = body.strip()
    approval = reminder_approval(session, reminder)
    if approval is None or approval.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=409, detail="Approval reminder tidak aktif.")
    approval.payload = {
        **approval.payload,
        "before": before,
        "after": {"subject": reminder.subject, "body": reminder.body},
    }
    record_audit_event(
        session,
        business_id=reminder.business_id,
        actor_type=ActorType.USER,
        actor_id=context.user.id,
        action="invoice.reminder_edited",
        entity_type="invoice_reminder",
        entity_id=reminder.id,
        correlation_id=correlation_id,
        metadata={"before": before, "after": approval.payload["after"]},
    )
    session.commit()
    return reminder


def approve_reminder(
    session: Session,
    *,
    reminder: InvoiceReminder,
    context: AuthContext,
    idempotency_key: str,
    comment: str | None,
    correlation_id: str,
) -> OutboxMessage:
    approval = reminder_approval(session, reminder, for_update=True)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval reminder tidak ditemukan.")
    existing_outbox = session.scalar(
        select(OutboxMessage).where(OutboxMessage.reminder_id == reminder.id)
    )
    recorded_key = approval.payload.get("decision_idempotency_key")
    if approval.status == ApprovalStatus.APPROVED and existing_outbox:
        if recorded_key == idempotency_key:
            return existing_outbox
        raise HTTPException(status_code=409, detail="Approval sudah diputuskan.")
    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=409, detail="Approval sudah diputuskan.")

    invoice = session.scalar(
        select(Invoice)
        .options(selectinload(Invoice.customer))
        .where(
            Invoice.business_id == context.business_id,
            Invoice.id == reminder.invoice_id,
        )
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice tidak ditemukan.")

    now = datetime.now(UTC)
    approval.status = ApprovalStatus.APPROVED
    approval.decided_by = context.user.id
    approval.decision_comment = comment
    approval.decided_at = now
    approval.payload = {
        **approval.payload,
        "decision_idempotency_key": idempotency_key,
    }
    reminder.status = ReminderStatus.QUEUED
    reminder.approved_by = context.user.id
    reminder.approved_at = now

    outbox = existing_outbox or OutboxMessage(
        business_id=reminder.business_id,
        reminder=reminder,
        channel=OutboxChannel.EMAIL,
        recipient=invoice.customer.email,
        recipient_masked=mask_email(invoice.customer.email),
        template="invoice-overdue-reminder-v1",
        payload={
            "subject": reminder.subject,
            "body": reminder.body,
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "total": str(invoice.total),
            "currency": invoice.currency,
            "due_date": invoice.due_date.isoformat(),
        },
        idempotency_key=f"invoice-reminder:{reminder.id}:email",
        status=OutboxStatus.PENDING,
    )
    if existing_outbox is None:
        session.add(outbox)
        session.flush()
    record_audit_event(
        session,
        business_id=reminder.business_id,
        actor_type=ActorType.USER,
        actor_id=context.user.id,
        action="invoice.reminder_approved",
        entity_type="invoice_reminder",
        entity_id=reminder.id,
        correlation_id=correlation_id,
        metadata={
            "approval_id": str(approval.id),
            "outbox_id": str(outbox.id),
            "recipient_masked": outbox.recipient_masked,
            "comment": comment,
        },
    )
    session.commit()
    return outbox


def reject_reminder(
    session: Session,
    *,
    reminder: InvoiceReminder,
    context: AuthContext,
    comment: str,
    correlation_id: str,
) -> InvoiceReminder:
    approval = reminder_approval(session, reminder, for_update=True)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval reminder tidak ditemukan.")
    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=409, detail="Approval sudah diputuskan.")
    now = datetime.now(UTC)
    approval.status = ApprovalStatus.REJECTED
    approval.decided_by = context.user.id
    approval.decision_comment = comment
    approval.decided_at = now
    reminder.status = ReminderStatus.REJECTED
    record_audit_event(
        session,
        business_id=reminder.business_id,
        actor_type=ActorType.USER,
        actor_id=context.user.id,
        action="invoice.reminder_rejected",
        entity_type="invoice_reminder",
        entity_id=reminder.id,
        correlation_id=correlation_id,
        metadata={"approval_id": str(approval.id), "comment": comment},
    )
    session.commit()
    return reminder


def dispatch_outbox_message(
    session: Session,
    *,
    outbox_id: uuid.UUID,
    settings: Settings,
    sender: EmailSender | None = None,
    correlation_id: str | None = None,
) -> OutboxMessage:
    outbox = session.scalar(
        select(OutboxMessage)
        .options(
            selectinload(OutboxMessage.reminder).selectinload(
                InvoiceReminder.invoice
            )
        )
        .where(OutboxMessage.id == outbox_id)
        .with_for_update()
    )
    if outbox is None:
        raise RuntimeError("Outbox message not found.")
    if outbox.status == OutboxStatus.SENT:
        return outbox
    approval = session.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.business_id == outbox.business_id,
            ApprovalRequest.entity_type == "INVOICE_REMINDER",
            ApprovalRequest.entity_id == outbox.reminder_id,
            ApprovalRequest.action_type == "SEND_REMINDER",
        )
    )
    if approval is None or approval.status != ApprovalStatus.APPROVED:
        raise RuntimeError("External message cannot be sent without approval.")

    outbox.status = OutboxStatus.PROCESSING
    outbox.attempt_count += 1
    outbox.last_error = None
    session.commit()
    try:
        (sender or send_smtp_email)(outbox, settings)
    except Exception as exc:
        outbox.status = OutboxStatus.FAILED
        outbox.last_error = str(exc)[:255]
        outbox.next_attempt_at = datetime.now(UTC) + timedelta(minutes=5)
        outbox.reminder.status = ReminderStatus.FAILED
        record_audit_event(
            session,
            business_id=outbox.business_id,
            actor_type=ActorType.SYSTEM,
            actor_id=None,
            action="invoice.reminder_delivery_failed",
            entity_type="invoice_reminder",
            entity_id=outbox.reminder_id,
            correlation_id=correlation_id or f"outbox-{outbox.id}",
            metadata={
                "outbox_id": str(outbox.id),
                "attempt_count": outbox.attempt_count,
                "error": outbox.last_error,
            },
        )
        session.commit()
        raise

    now = datetime.now(UTC)
    outbox.status = OutboxStatus.SENT
    outbox.sent_at = now
    outbox.next_attempt_at = None
    outbox.reminder.status = ReminderStatus.SENT
    outbox.reminder.sent_at = now
    record_audit_event(
        session,
        business_id=outbox.business_id,
        actor_type=ActorType.SYSTEM,
        actor_id=None,
        action="invoice.reminder_sent",
        entity_type="invoice_reminder",
        entity_id=outbox.reminder_id,
        correlation_id=correlation_id or f"outbox-{outbox.id}",
        metadata={
            "outbox_id": str(outbox.id),
            "channel": outbox.channel.value,
            "recipient_masked": outbox.recipient_masked,
            "attempt_count": outbox.attempt_count,
        },
    )
    session.commit()
    return outbox


def send_smtp_email(outbox: OutboxMessage, settings: Settings) -> None:
    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = outbox.recipient
    message["Subject"] = str(outbox.payload["subject"])
    message["Message-ID"] = f"<invoice-reminder-{outbox.reminder_id}@kopiarunika.demo>"
    message.set_content(str(outbox.payload["body"]))
    with smtplib.SMTP(
        settings.smtp_host,
        settings.smtp_port,
        timeout=settings.smtp_timeout_seconds,
    ) as client:
        client.send_message(message)


def get_invoice_or_404(
    session: Session,
    *,
    business_id: uuid.UUID,
    invoice_id: uuid.UUID,
) -> Invoice:
    invoice = session.scalar(
        select(Invoice)
        .options(
            selectinload(Invoice.customer),
            selectinload(Invoice.reminders).selectinload(
                InvoiceReminder.outbox_messages
            ),
        )
        .where(
            Invoice.business_id == business_id,
            Invoice.id == invoice_id,
        )
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice tidak ditemukan.")
    return invoice


def get_reminder_or_404(
    session: Session,
    *,
    business_id: uuid.UUID,
    reminder_id: uuid.UUID,
) -> InvoiceReminder:
    reminder = session.scalar(
        select(InvoiceReminder)
        .options(
            selectinload(InvoiceReminder.invoice).selectinload(Invoice.customer),
            selectinload(InvoiceReminder.outbox_messages),
        )
        .where(
            InvoiceReminder.business_id == business_id,
            InvoiceReminder.id == reminder_id,
        )
        .with_for_update()
    )
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder tidak ditemukan.")
    return reminder


def reminder_approval(
    session: Session,
    reminder: InvoiceReminder,
    *,
    for_update: bool = False,
) -> ApprovalRequest | None:
    query = select(ApprovalRequest).where(
        ApprovalRequest.business_id == reminder.business_id,
        ApprovalRequest.entity_type == "INVOICE_REMINDER",
        ApprovalRequest.entity_id == reminder.id,
        ApprovalRequest.action_type == "SEND_REMINDER",
    )
    if for_update:
        query = query.with_for_update()
    return session.scalar(query)


def serialize_invoice(
    session: Session,
    invoice: Invoice,
    *,
    as_of: date,
    include_detail: bool = False,
) -> dict[str, Any]:
    reminders = list(invoice.reminders)
    approvals = {
        approval.entity_id: approval
        for approval in session.scalars(
            select(ApprovalRequest).where(
                ApprovalRequest.business_id == invoice.business_id,
                ApprovalRequest.entity_type == "INVOICE_REMINDER",
                ApprovalRequest.entity_id.in_(
                    [reminder.id for reminder in reminders]
                ),
            )
        )
    } if reminders else {}
    latest_status = reminders[0].status if reminders else None
    payload: dict[str, Any] = {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "customer": {
            "id": invoice.customer.id,
            "name": invoice.customer.name,
            "email": invoice.customer.email,
            "phone_masked": invoice.customer.phone_masked,
        },
        "issue_date": invoice.issue_date,
        "due_date": invoice.due_date,
        "subtotal": invoice.subtotal,
        "tax": invoice.tax,
        "total": invoice.total,
        "currency": invoice.currency,
        "status": invoice.status,
        "paid_at": invoice.paid_at,
        "days_until_due": (invoice.due_date - as_of).days,
        "latest_reminder_status": latest_status,
        "created_at": invoice.created_at,
        "updated_at": invoice.updated_at,
    }
    if include_detail:
        payload["reminders"] = [
            serialize_reminder(reminder, approvals.get(reminder.id))
            for reminder in reminders
        ]
        entity_ids = [invoice.id, *(reminder.id for reminder in reminders)]
        events = list(
            session.scalars(
                select(AuditEvent)
                .where(
                    AuditEvent.business_id == invoice.business_id,
                    AuditEvent.entity_id.in_(entity_ids),
                )
                .order_by(AuditEvent.created_at.desc())
            )
        )
        payload["audit_timeline"] = [
            {
                "id": event.id,
                "actor_type": event.actor_type.value,
                "action": event.action,
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "correlation_id": event.correlation_id,
                "metadata": event.event_metadata,
                "created_at": event.created_at,
            }
            for event in events
        ]
    return payload


def serialize_reminder(
    reminder: InvoiceReminder,
    approval: ApprovalRequest | None,
) -> dict[str, Any]:
    outbox = reminder.outbox_messages[0] if reminder.outbox_messages else None
    return {
        "id": reminder.id,
        "invoice_id": reminder.invoice_id,
        "sequence": reminder.sequence,
        "subject": reminder.subject,
        "body": reminder.body,
        "source": reminder.source,
        "status": reminder.status,
        "approval_id": approval.id if approval else None,
        "approval_status": approval.status if approval else None,
        "decision_comment": approval.decision_comment if approval else None,
        "approved_at": reminder.approved_at,
        "sent_at": reminder.sent_at,
        "created_at": reminder.created_at,
        "updated_at": reminder.updated_at,
        "outbox": serialize_outbox(outbox) if outbox else None,
    }


def serialize_outbox(outbox: OutboxMessage) -> dict[str, Any]:
    return {
        "id": outbox.id,
        "channel": outbox.channel,
        "recipient_masked": outbox.recipient_masked,
        "template": outbox.template,
        "status": outbox.status,
        "attempt_count": outbox.attempt_count,
        "next_attempt_at": outbox.next_attempt_at,
        "last_error": outbox.last_error,
        "sent_at": outbox.sent_at,
        "created_at": outbox.created_at,
    }


def format_idr(amount: Decimal, currency: str) -> str:
    rounded = amount.quantize(Decimal("1"))
    grouped = f"{int(rounded):,}".replace(",", ".")
    return f"{currency} {grouped}"


def format_indonesian_date(value: date) -> str:
    months = (
        "Januari",
        "Februari",
        "Maret",
        "April",
        "Mei",
        "Juni",
        "Juli",
        "Agustus",
        "September",
        "Oktober",
        "November",
        "Desember",
    )
    return f"{value.day} {months[value.month - 1]} {value.year}"


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    masked_local = (
        local[:1] + "*"
        if len(local) <= 2
        else local[:2] + "*" * min(4, len(local) - 2)
    )
    return f"{masked_local}@{domain}"


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
