"""Create Phase D schedules and Scheduler heartbeat."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0005_phase_d"
down_revision: str | None = "0004_log_retention"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scheduled_task",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("customer_id", sa.String(length=32), nullable=False),
        sa.Column("customer_feature_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("cron_expression", sa.String(length=120), nullable=False),
        sa.Column("timezone", sa.String(length=80), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("next_run_at", sa.Integer(), nullable=True),
        sa.Column("last_scheduled_for", sa.Integer(), nullable=True),
        sa.Column("last_handled_at", sa.Integer(), nullable=True),
        sa.Column("last_run_request_id", sa.String(length=32), nullable=True),
        sa.Column("last_outcome", sa.String(length=32), nullable=True),
        sa.Column("last_message", sa.String(length=500), nullable=True),
        sa.Column("missed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.CheckConstraint(
            "last_outcome IS NULL OR last_outcome IN ('ENQUEUED', 'MISSED', 'SKIPPED_ACTIVE', "
            "'SKIPPED_UNAVAILABLE', 'QUEUE_FULL', 'DUPLICATE')",
            name="ck_scheduled_task_last_outcome",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["customer_feature_id"], ["customer_feature.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scheduled_task_customer", "scheduled_task", ["customer_id", "created_at"])
    op.create_index("ix_scheduled_task_due", "scheduled_task", ["is_enabled", "next_run_at"])
    op.create_index("ix_scheduled_task_feature", "scheduled_task", ["customer_feature_id", "is_enabled"])

    op.create_table(
        "scheduler_heartbeat",
        sa.Column("scheduler_id", sa.String(length=64), nullable=False),
        sa.Column("instance_token", sa.String(length=64), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.Integer(), nullable=False),
        sa.Column("heartbeat_at", sa.Integer(), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE', 'STOPPING')", name="ck_scheduler_heartbeat_status"),
        sa.PrimaryKeyConstraint("scheduler_id"),
    )


def downgrade() -> None:
    op.drop_table("scheduler_heartbeat")
    op.drop_index("ix_scheduled_task_feature", table_name="scheduled_task")
    op.drop_index("ix_scheduled_task_due", table_name="scheduled_task")
    op.drop_index("ix_scheduled_task_customer", table_name="scheduled_task")
    op.drop_table("scheduled_task")
