"""Add workflow replay, chaos controls, and persisted evaluation runs.

Revision ID: 20260802_0006
Revises: 20260731_0005
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260802_0006"
down_revision: str | None = "20260731_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_extractions",
        sa.Column("workflow_run_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_document_extractions_workflow_run_id",
        "document_extractions",
        "workflow_runs",
        ["workflow_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_document_extractions_workflow_run_id"),
        "document_extractions",
        ["workflow_run_id"],
    )
    op.create_unique_constraint(
        "uq_document_extraction_workflow_run",
        "document_extractions",
        ["document_id", "workflow_run_id"],
    )
    op.create_table(
        "workflow_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("safe_resume_sequence", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("retry_delay_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_run_id", "attempt_number", name="uq_workflow_attempt_number"),
    )
    op.create_index(
        op.f("ix_workflow_attempts_workflow_run_id"), "workflow_attempts", ["workflow_run_id"]
    )

    op.create_table(
        "chaos_scenario_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("scenario_key", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("trigger_count", sa.Integer(), nullable=False),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enabled_by", sa.Uuid(), nullable=True),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["enabled_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("business_id", "scenario_key", name="uq_chaos_scenario_business_key"),
    )
    op.create_index(
        op.f("ix_chaos_scenario_states_business_id"), "chaos_scenario_states", ["business_id"]
    )

    op.create_table(
        "evaluation_cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version", sa.String(length=40), nullable=False),
        sa.Column("case_key", sa.String(length=100), nullable=False),
        sa.Column("case_type", sa.String(length=40), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("expected_output", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_version", "case_key", name="uq_evaluation_case_dataset_key"),
    )
    op.create_index(
        op.f("ix_evaluation_cases_dataset_version"), "evaluation_cases", ["dataset_version"]
    )
    op.create_index(op.f("ix_evaluation_cases_case_type"), "evaluation_cases", ["case_type"])

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_evaluation_runs_business_id"), "evaluation_runs", ["business_id"])
    op.create_index(op.f("ix_evaluation_runs_status"), "evaluation_runs", ["status"])
    op.create_index(
        op.f("ix_evaluation_runs_correlation_id"), "evaluation_runs", ["correlation_id"]
    )

    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_run_id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_case_id", sa.Uuid(), nullable=False),
        sa.Column("actual_output", sa.JSON(), nullable=False),
        sa.Column("scores", sa.JSON(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("usage", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_case_id"], ["evaluation_cases.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evaluation_run_id", "evaluation_case_id", name="uq_evaluation_result_run_case"
        ),
    )
    op.create_index(
        op.f("ix_evaluation_results_evaluation_run_id"), "evaluation_results", ["evaluation_run_id"]
    )
    op.create_index(
        op.f("ix_evaluation_results_evaluation_case_id"),
        "evaluation_results",
        ["evaluation_case_id"],
    )
    op.create_index(op.f("ix_evaluation_results_passed"), "evaluation_results", ["passed"])


def downgrade() -> None:
    op.drop_table("evaluation_results")
    op.drop_table("evaluation_runs")
    op.drop_table("evaluation_cases")
    op.drop_table("chaos_scenario_states")
    op.drop_table("workflow_attempts")
    op.drop_constraint(
        "uq_document_extraction_workflow_run",
        "document_extractions",
        type_="unique",
    )
    op.drop_index(
        op.f("ix_document_extractions_workflow_run_id"),
        table_name="document_extractions",
    )
    op.drop_constraint(
        "fk_document_extractions_workflow_run_id",
        "document_extractions",
        type_="foreignkey",
    )
    op.drop_column("document_extractions", "workflow_run_id")
