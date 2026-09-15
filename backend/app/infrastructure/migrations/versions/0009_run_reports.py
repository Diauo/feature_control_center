"""Add structured per-run business reports."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0009_run_reports"
down_revision: str | None = "0008_scope_paging_update"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "run_report",
        sa.Column("run_request_id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("item_label", sa.String(length=40), nullable=False),
        sa.Column("schema_json", sa.Text(), nullable=False),
        sa.Column("expected_total", sa.Integer(), nullable=True),
        sa.Column("reported_total", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("no_data_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("unfinished_count", sa.Integer(), nullable=False),
        sa.Column("validation_error_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.Integer(), nullable=False),
        sa.Column("completion_requested_at", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.Integer(), nullable=True),
        sa.Column("details_purged_at", sa.Integer(), nullable=True),
        sa.CheckConstraint("status IN ('OPEN', 'COMPLETE', 'INCOMPLETE')", name="ck_run_report_status"),
        sa.CheckConstraint(
            "expected_total IS NULL OR (expected_total >= 0 AND expected_total <= 5000)",
            name="ck_run_report_expected_total",
        ),
        sa.CheckConstraint(
            "reported_total >= 0 AND reported_total <= 5000",
            name="ck_run_report_reported_total",
        ),
        sa.CheckConstraint(
            "success_count >= 0 AND failed_count >= 0 AND no_data_count >= 0 "
            "AND skipped_count >= 0 AND unfinished_count >= 0",
            name="ck_run_report_counts",
        ),
        sa.CheckConstraint("validation_error_count >= 0", name="ck_run_report_validation_errors"),
        sa.ForeignKeyConstraint(["run_request_id"], ["run.request_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_request_id"),
    )
    op.create_table(
        "run_report_item",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_request_id", sa.String(length=32), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=True),
        sa.Column("values_json", sa.Text(), nullable=False),
        sa.Column("reported_at_ms", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('SUCCESS', 'FAILED', 'NO_DATA', 'SKIPPED', 'UNFINISHED')",
            name="ck_run_report_item_status",
        ),
        sa.ForeignKeyConstraint(["run_request_id"], ["run_report.run_request_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_request_id", "sequence", name="uq_run_report_item_sequence"),
    )
    op.create_index(
        "ix_run_report_item_run_sequence",
        "run_report_item",
        ["run_request_id", "sequence"],
        unique=False,
    )
    op.create_index(
        "ix_run_report_item_run_status",
        "run_report_item",
        ["run_request_id", "status", "sequence"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_run_report_item_run_status", table_name="run_report_item")
    op.drop_index("ix_run_report_item_run_sequence", table_name="run_report_item")
    op.drop_table("run_report_item")
    op.drop_table("run_report")
