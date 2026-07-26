"""Create document workflow, extraction, ledger, and approval tables.

Revision ID: 20260727_0002
Revises: 20260727_0001
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260727_0002"
down_revision: str | None = "20260727_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ledger_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column(
            "account_type",
            sa.Enum(
                "ASSET",
                "LIABILITY",
                "EQUITY",
                "REVENUE",
                "EXPENSE",
                name="accounttype",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("business_id", "code", name="uq_account_business_code"),
    )
    op.create_index(
        op.f("ix_ledger_accounts_business_id"),
        "ledger_accounts",
        ["business_id"],
        unique=False,
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column(
            "source",
            sa.Enum("UPLOAD", "DEMO", name="documentsource", native_enum=False),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("upload_idempotency_key", sa.String(length=128), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "UPLOADED",
                "QUEUED",
                "EXTRACTING",
                "VALIDATING",
                "NEEDS_REVIEW",
                "READY_TO_POST",
                "REJECTED",
                "FAILED",
                "POSTED",
                "ARCHIVED",
                name="documentstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "document_type",
            sa.Enum(
                "RECEIPT",
                "SUPPLIER_INVOICE",
                "CUSTOMER_INVOICE",
                "BANK_STATEMENT",
                "UNKNOWN",
                name="documenttype",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("document_number", sa.String(length=120), nullable=True),
        sa.Column("vendor_name", sa.String(length=255), nullable=True),
        sa.Column("normalized_vendor_name", sa.String(length=255), nullable=True),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("tax", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("total", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("payment_method", sa.String(length=80), nullable=True),
        sa.Column("extraction_confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("validation_warnings", sa.JSON(), nullable=False),
        sa.Column("duplicate_of_id", sa.Uuid(), nullable=True),
        sa.Column("duplicate_reason", sa.String(length=255), nullable=True),
        sa.Column("proposed_account_id", sa.Uuid(), nullable=True),
        sa.Column("final_account_id", sa.Uuid(), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["duplicate_of_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["final_account_id"], ["ledger_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["proposed_account_id"], ["ledger_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_id",
            "upload_idempotency_key",
            name="uq_document_business_upload_key",
        ),
    )
    op.create_index(
        op.f("ix_documents_business_id"), "documents", ["business_id"], unique=False
    )
    op.create_index(op.f("ix_documents_created_at"), "documents", ["created_at"], unique=False)
    op.create_index(op.f("ix_documents_sha256"), "documents", ["sha256"], unique=False)
    op.create_index(op.f("ix_documents_status"), "documents", ["status"], unique=False)

    op.create_table(
        "document_extractions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("schema_version", sa.String(length=40), nullable=False),
        sa.Column("raw_structured_output", sa.JSON(), nullable=False),
        sa.Column("normalized_output", sa.JSON(), nullable=False),
        sa.Column("field_confidences", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("usage", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_document_extractions_document_id"),
        "document_extractions",
        ["document_id"],
        unique=False,
    )

    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_type", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "RUNNING",
                "WAITING_FOR_APPROVAL",
                "RETRY_SCHEDULED",
                "SUCCEEDED",
                "FAILED",
                "DEAD_LETTER",
                name="workflowstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_workflow_runs_business_id"),
        "workflow_runs",
        ["business_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_runs_correlation_id"),
        "workflow_runs",
        ["correlation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_runs_entity_id"), "workflow_runs", ["entity_id"], unique=False
    )

    op.create_table(
        "workflow_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("step_name", sa.String(length=80), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "RUNNING",
                "SUCCEEDED",
                "FAILED",
                "SKIPPED",
                name="stepstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("input_summary", sa.JSON(), nullable=False),
        sa.Column("output_summary", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workflow_run_id", "sequence", name="uq_workflow_step_sequence"
        ),
    )
    op.create_index(
        op.f("ix_workflow_steps_workflow_run_id"),
        "workflow_steps",
        ["workflow_run_id"],
        unique=False,
    )

    op.create_table(
        "journal_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "POSTED",
                "REVERSED",
                name="journalstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posted_by", sa.Uuid(), nullable=True),
        sa.Column("post_idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("reversal_of_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["posted_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["reversal_of_id"], ["journal_entries.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_id", "document_id", name="uq_journal_document"
        ),
        sa.UniqueConstraint(
            "business_id",
            "post_idempotency_key",
            name="uq_journal_business_post_key",
        ),
    )
    op.create_index(
        op.f("ix_journal_entries_business_id"),
        "journal_entries",
        ["business_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_journal_entries_document_id"),
        "journal_entries",
        ["document_id"],
        unique=False,
    )

    op.create_table(
        "journal_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=False),
        sa.Column("ledger_account_id", sa.Uuid(), nullable=False),
        sa.Column("debit", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("credit", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("memo", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"], ["journal_entries.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["ledger_account_id"], ["ledger_accounts.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_journal_lines_journal_entry_id"),
        "journal_lines",
        ["journal_entry_id"],
        unique=False,
    )

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=True),
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "risk_level",
            sa.Enum("LOW", "MEDIUM", "HIGH", name="risklevel", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "APPROVED",
                "REJECTED",
                "EXPIRED",
                "CANCELLED",
                name="approvalstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decision_comment", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"], ["journal_entries.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"], ["workflow_runs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_id",
            "document_id",
            "action_type",
            name="uq_approval_document_action",
        ),
    )
    op.create_index(
        op.f("ix_approval_requests_business_id"),
        "approval_requests",
        ["business_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_requests_document_id"),
        "approval_requests",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_requests_status"),
        "approval_requests",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_approval_requests_status"), table_name="approval_requests")
    op.drop_index(
        op.f("ix_approval_requests_document_id"), table_name="approval_requests"
    )
    op.drop_index(
        op.f("ix_approval_requests_business_id"), table_name="approval_requests"
    )
    op.drop_table("approval_requests")
    op.drop_index(
        op.f("ix_journal_lines_journal_entry_id"), table_name="journal_lines"
    )
    op.drop_table("journal_lines")
    op.drop_index(
        op.f("ix_journal_entries_document_id"), table_name="journal_entries"
    )
    op.drop_index(
        op.f("ix_journal_entries_business_id"), table_name="journal_entries"
    )
    op.drop_table("journal_entries")
    op.drop_index(
        op.f("ix_workflow_steps_workflow_run_id"), table_name="workflow_steps"
    )
    op.drop_table("workflow_steps")
    op.drop_index(op.f("ix_workflow_runs_entity_id"), table_name="workflow_runs")
    op.drop_index(
        op.f("ix_workflow_runs_correlation_id"), table_name="workflow_runs"
    )
    op.drop_index(op.f("ix_workflow_runs_business_id"), table_name="workflow_runs")
    op.drop_table("workflow_runs")
    op.drop_index(
        op.f("ix_document_extractions_document_id"), table_name="document_extractions"
    )
    op.drop_table("document_extractions")
    op.drop_index(op.f("ix_documents_status"), table_name="documents")
    op.drop_index(op.f("ix_documents_sha256"), table_name="documents")
    op.drop_index(op.f("ix_documents_created_at"), table_name="documents")
    op.drop_index(op.f("ix_documents_business_id"), table_name="documents")
    op.drop_table("documents")
    op.drop_index(
        op.f("ix_ledger_accounts_business_id"), table_name="ledger_accounts"
    )
    op.drop_table("ledger_accounts")
