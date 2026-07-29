"""Create bank import, transaction, and reconciliation tables.

Revision ID: 20260729_0003
Revises: 20260727_0002
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260729_0003"
down_revision: str | None = "20260727_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bank_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("mapping", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "COMPLETED",
                "COMPLETED_WITH_ERRORS",
                name="bankimportstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("imported_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("row_errors", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_id",
            "sha256",
            name="uq_bank_import_business_sha256",
        ),
    )
    op.create_index(
        op.f("ix_bank_imports_business_id"),
        "bank_imports",
        ["business_id"],
        unique=False,
    )

    op.create_table(
        "bank_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("bank_import_id", sa.Uuid(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("external_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column(
            "direction",
            sa.Enum("DEBIT", "CREDIT", name="bankdirection", native_enum=False),
            nullable=False,
        ),
        sa.Column("reference", sa.String(length=160), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "UNMATCHED",
                "SUGGESTED",
                "AUTO_MATCHED",
                "CONFIRMED",
                name="banktransactionstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["bank_import_id"], ["bank_imports.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_id",
            "external_fingerprint",
            name="uq_bank_transaction_business_fingerprint",
        ),
    )
    op.create_index(
        op.f("ix_bank_transactions_bank_import_id"),
        "bank_transactions",
        ["bank_import_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bank_transactions_business_id"),
        "bank_transactions",
        ["business_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bank_transactions_status"),
        "bank_transactions",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bank_transactions_transaction_date"),
        "bank_transactions",
        ["transaction_date"],
        unique=False,
    )

    op.create_table(
        "reconciliations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("bank_transaction_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("score_breakdown", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "SUGGESTED",
                "AUTO_MATCHED",
                "CONFIRMED",
                "REJECTED",
                name="reconciliationstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decision_comment", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["bank_transaction_id"],
            ["bank_transactions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_id",
            "bank_transaction_id",
            "source_type",
            "source_id",
            name="uq_reconciliation_candidate",
        ),
    )
    op.create_index(
        op.f("ix_reconciliations_bank_transaction_id"),
        "reconciliations",
        ["bank_transaction_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reconciliations_business_id"),
        "reconciliations",
        ["business_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reconciliations_source_id"),
        "reconciliations",
        ["source_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reconciliations_status"),
        "reconciliations",
        ["status"],
        unique=False,
    )
    op.create_index(
        "uq_reconciliation_active_bank_transaction",
        "reconciliations",
        ["bank_transaction_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('AUTO_MATCHED', 'CONFIRMED')"),
        sqlite_where=sa.text("status IN ('AUTO_MATCHED', 'CONFIRMED')"),
    )
    op.create_index(
        "uq_reconciliation_active_source",
        "reconciliations",
        ["business_id", "source_type", "source_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('AUTO_MATCHED', 'CONFIRMED')"),
        sqlite_where=sa.text("status IN ('AUTO_MATCHED', 'CONFIRMED')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_reconciliation_active_source",
        table_name="reconciliations",
    )
    op.drop_index(
        "uq_reconciliation_active_bank_transaction",
        table_name="reconciliations",
    )
    op.drop_index(
        op.f("ix_reconciliations_status"),
        table_name="reconciliations",
    )
    op.drop_index(
        op.f("ix_reconciliations_source_id"),
        table_name="reconciliations",
    )
    op.drop_index(
        op.f("ix_reconciliations_business_id"),
        table_name="reconciliations",
    )
    op.drop_index(
        op.f("ix_reconciliations_bank_transaction_id"),
        table_name="reconciliations",
    )
    op.drop_table("reconciliations")
    op.drop_index(
        op.f("ix_bank_transactions_transaction_date"),
        table_name="bank_transactions",
    )
    op.drop_index(
        op.f("ix_bank_transactions_status"),
        table_name="bank_transactions",
    )
    op.drop_index(
        op.f("ix_bank_transactions_business_id"),
        table_name="bank_transactions",
    )
    op.drop_index(
        op.f("ix_bank_transactions_bank_import_id"),
        table_name="bank_transactions",
    )
    op.drop_table("bank_transactions")
    op.drop_index(
        op.f("ix_bank_imports_business_id"),
        table_name="bank_imports",
    )
    op.drop_table("bank_imports")
