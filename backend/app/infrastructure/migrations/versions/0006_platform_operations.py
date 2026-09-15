"""Add platform operations, package settings, and audit snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0006_platform_operations"
down_revision: str | None = "0005_phase_d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("audit_log") as batch:
        batch.add_column(sa.Column("actor_role", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("actor_username", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("actor_display_name", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("target_name", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("customer_id", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("customer_name", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("request_method", sa.String(length=10), nullable=True))
        batch.add_column(sa.Column("request_path", sa.String(length=300), nullable=True))
        batch.add_column(sa.Column("request_id", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("user_agent", sa.String(length=512), nullable=True))
        batch.create_index("ix_audit_role", ["actor_role", "occurred_at"])
        batch.create_index("ix_audit_customer", ["customer_id", "occurred_at"])


def downgrade() -> None:
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_index("ix_audit_customer")
        batch.drop_index("ix_audit_role")
        batch.drop_column("user_agent")
        batch.drop_column("request_id")
        batch.drop_column("request_path")
        batch.drop_column("request_method")
        batch.drop_column("customer_name")
        batch.drop_column("customer_id")
        batch.drop_column("target_name")
        batch.drop_column("actor_display_name")
        batch.drop_column("actor_username")
        batch.drop_column("actor_role")
