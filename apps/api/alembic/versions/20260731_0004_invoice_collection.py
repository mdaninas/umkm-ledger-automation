"""Create customer invoice, reminder, and email outbox tables.

Revision ID: 20260731_0004
Revises: 20260729_0003
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260731_0004"
down_revision: str | None = "20260729_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "approval_requests",
        sa.Column("entity_type", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "approval_requests",
        sa.Column("entity_id", sa.Uuid(), nullable=True),
    )
    op.execute(
        """
        UPDATE approval_requests
        SET entity_type = 'DOCUMENT', entity_id = document_id
        WHERE entity_type IS NULL
        """
    )
    op.alter_column(
        "approval_requests",
        "entity_type",
        existing_type=sa.String(length=40),
        nullable=False,
    )
    op.alter_column(
        "approval_requests",
        "entity_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.alter_column(
        "approval_requests",
        "document_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    op.drop_constraint(
        "uq_approval_document_action",
        "approval_requests",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_approval_entity_action",
        "approval_requests",
        ["business_id", "entity_type", "entity_id", "action_type"],
    )
    op.create_index(
        op.f("ix_approval_requests_entity_type"),
        "approval_requests",
        ["entity_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_requests_entity_id"),
        "approval_requests",
        ["entity_id"],
        unique=False,
    )

    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("phone_masked", sa.String(length=80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_id",
            "email",
            name="uq_customer_business_email",
        ),
    )
    op.create_index(
        op.f("ix_customers_business_id"),
        "customers",
        ["business_id"],
        unique=False,
    )

    op.create_table(
        "invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_number", sa.String(length=120), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column(
            "tax",
            sa.Numeric(precision=18, scale=2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("total", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="IDR",
        ),
        sa.Column(
            "status",
            sa.Enum(
                "OUTSTANDING",
                "DUE_SOON",
                "OVERDUE",
                "PAID",
                name="invoicestatus",
                native_enum=False,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_id",
            "invoice_number",
            name="uq_invoice_business_number",
        ),
    )
    op.create_index(
        op.f("ix_invoices_business_id"),
        "invoices",
        ["business_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_invoices_customer_id"),
        "invoices",
        ["customer_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_invoices_document_id"),
        "invoices",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_invoices_due_date"),
        "invoices",
        ["due_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_invoices_status"),
        "invoices",
        ["status"],
        unique=False,
    )

    op.create_table(
        "invoice_reminders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "AI_ASSISTED",
                "DETERMINISTIC_FALLBACK",
                name="remindersource",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING_APPROVAL",
                "APPROVED",
                "REJECTED",
                "QUEUED",
                "SENT",
                "FAILED",
                name="reminderstatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "invoice_id",
            "sequence",
            name="uq_invoice_reminder_sequence",
        ),
    )
    op.create_index(
        op.f("ix_invoice_reminders_business_id"),
        "invoice_reminders",
        ["business_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_invoice_reminders_invoice_id"),
        "invoice_reminders",
        ["invoice_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_invoice_reminders_status"),
        "invoice_reminders",
        ["status"],
        unique=False,
    )

    op.create_table(
        "outbox_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("reminder_id", sa.Uuid(), nullable=False),
        sa.Column(
            "channel",
            sa.Enum(
                "EMAIL",
                name="outboxchannel",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("recipient_masked", sa.String(length=320), nullable=False),
        sa.Column("template", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "PROCESSING",
                "SENT",
                "FAILED",
                name="outboxstatus",
                native_enum=False,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reminder_id"],
            ["invoice_reminders.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_id",
            "idempotency_key",
            name="uq_outbox_business_idempotency",
        ),
    )
    op.create_index(
        op.f("ix_outbox_messages_business_id"),
        "outbox_messages",
        ["business_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbox_messages_reminder_id"),
        "outbox_messages",
        ["reminder_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbox_messages_status"),
        "outbox_messages",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM approval_requests
        WHERE entity_type = 'INVOICE_REMINDER'
        """
    )
    op.drop_index(op.f("ix_outbox_messages_status"), table_name="outbox_messages")
    op.drop_index(op.f("ix_outbox_messages_reminder_id"), table_name="outbox_messages")
    op.drop_index(op.f("ix_outbox_messages_business_id"), table_name="outbox_messages")
    op.drop_table("outbox_messages")

    op.drop_index(op.f("ix_invoice_reminders_status"), table_name="invoice_reminders")
    op.drop_index(op.f("ix_invoice_reminders_invoice_id"), table_name="invoice_reminders")
    op.drop_index(op.f("ix_invoice_reminders_business_id"), table_name="invoice_reminders")
    op.drop_table("invoice_reminders")

    op.drop_index(op.f("ix_invoices_status"), table_name="invoices")
    op.drop_index(op.f("ix_invoices_due_date"), table_name="invoices")
    op.drop_index(op.f("ix_invoices_document_id"), table_name="invoices")
    op.drop_index(op.f("ix_invoices_customer_id"), table_name="invoices")
    op.drop_index(op.f("ix_invoices_business_id"), table_name="invoices")
    op.drop_table("invoices")

    op.drop_index(op.f("ix_customers_business_id"), table_name="customers")
    op.drop_table("customers")

    op.drop_index(
        op.f("ix_approval_requests_entity_id"),
        table_name="approval_requests",
    )
    op.drop_index(
        op.f("ix_approval_requests_entity_type"),
        table_name="approval_requests",
    )
    op.drop_constraint(
        "uq_approval_entity_action",
        "approval_requests",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_approval_document_action",
        "approval_requests",
        ["business_id", "document_id", "action_type"],
    )
    op.alter_column(
        "approval_requests",
        "document_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.drop_column("approval_requests", "entity_id")
    op.drop_column("approval_requests", "entity_type")
