"""Create Phase C run queue, append-only events, and Runner heartbeat."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0003_phase_c"
down_revision: str | None = "0002_phase_b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("customer_feature") as batch:
        batch.add_column(sa.Column("max_runtime_seconds", sa.Integer(), nullable=True))

    op.create_table(
        "run",
        sa.Column("request_id", sa.String(length=32), nullable=False),
        sa.Column("customer_id", sa.String(length=32), nullable=False),
        sa.Column("customer_feature_id", sa.String(length=32), nullable=False),
        sa.Column("feature_version_id", sa.String(length=32), nullable=False),
        sa.Column("data_source_revision_id", sa.String(length=32), nullable=True),
        sa.Column("feature_name", sa.String(length=120), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("data_source_filename", sa.String(length=255), nullable=True),
        sa.Column("config_snapshot_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("secret_keys_json", sa.Text(), nullable=False),
        sa.Column("trigger_source", sa.String(length=16), nullable=False),
        sa.Column("trigger_key", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("queued_at", sa.Integer(), nullable=False),
        sa.Column("claimed_at", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.Integer(), nullable=True),
        sa.Column("stop_requested_at", sa.Integer(), nullable=True),
        sa.Column("term_sent_at", sa.Integer(), nullable=True),
        sa.Column("kill_sent_at", sa.Integer(), nullable=True),
        sa.Column("finished_at", sa.Integer(), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("process_id", sa.Integer(), nullable=True),
        sa.Column("failure_summary", sa.Text(), nullable=True),
        sa.Column("stop_reason", sa.String(length=64), nullable=True),
        sa.Column("runner_id", sa.String(length=64), nullable=True),
        sa.Column("runner_heartbeat_at", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.Column("max_runtime_seconds", sa.Integer(), nullable=True),
        sa.Column("last_event_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("final_event_sequence", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'STARTING', 'RUNNING', 'STOPPING', 'SUCCEEDED', "
            "'FAILED', 'STOPPED', 'TIMED_OUT', 'INTERRUPTED')",
            name="ck_run_status",
        ),
        sa.CheckConstraint("trigger_source IN ('MANUAL', 'SCHEDULED')", name="ck_run_trigger_source"),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["customer_feature_id"], ["customer_feature.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["feature_version_id"], ["feature_version.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["data_source_revision_id"], ["customer_feature_data_source_revision.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("request_id"),
        sa.UniqueConstraint("trigger_key", name="uq_run_trigger_key"),
    )
    op.create_index("ix_run_customer_queued", "run", ["customer_id", "queued_at"])
    op.create_index("ix_run_status_queued", "run", ["status", "queued_at"])
    op.create_index("ix_run_customer_feature_status", "run", ["customer_feature_id", "status"])
    op.create_index(
        "uq_run_active_customer_feature",
        "run",
        ["customer_feature_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('QUEUED', 'STARTING', 'RUNNING', 'STOPPING')"),
    )

    op.create_table(
        "run_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_request_id", sa.String(length=32), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("occurred_at_ms", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("context_json", sa.Text(), nullable=False),
        sa.CheckConstraint("level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR')", name="ck_run_event_level"),
        sa.CheckConstraint(
            "source IN ('PLATFORM', 'SDK', 'STDOUT', 'STDERR')", name="ck_run_event_source"
        ),
        sa.ForeignKeyConstraint(["run_request_id"], ["run.request_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_request_id", "sequence", name="uq_run_event_sequence"),
    )
    op.create_index("ix_run_event_run_sequence", "run_event", ["run_request_id", "sequence"])

    op.create_table(
        "runner_heartbeat",
        sa.Column("runner_id", sa.String(length=64), nullable=False),
        sa.Column("instance_token", sa.String(length=64), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.Integer(), nullable=False),
        sa.Column("heartbeat_at", sa.Integer(), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE', 'STOPPING')", name="ck_runner_heartbeat_status"),
        sa.PrimaryKeyConstraint("runner_id"),
    )


def downgrade() -> None:
    op.drop_table("runner_heartbeat")
    op.drop_index("ix_run_event_run_sequence", table_name="run_event")
    op.drop_table("run_event")
    op.drop_index("uq_run_active_customer_feature", table_name="run")
    op.drop_index("ix_run_customer_feature_status", table_name="run")
    op.drop_index("ix_run_status_queued", table_name="run")
    op.drop_index("ix_run_customer_queued", table_name="run")
    op.drop_table("run")
    with op.batch_alter_table("customer_feature") as batch:
        batch.drop_column("max_runtime_seconds")
