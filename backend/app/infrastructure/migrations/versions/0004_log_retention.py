"""Add observable retention state for automatically purged run logs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0004_log_retention"
down_revision: str | None = "0003_phase_c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("run") as batch:
        batch.add_column(sa.Column("logs_purged_at", sa.Integer(), nullable=True))
        batch.create_index("ix_run_log_retention", ["logs_purged_at", "finished_at"])


def downgrade() -> None:
    with op.batch_alter_table("run") as batch:
        batch.drop_index("ix_run_log_retention")
        batch.drop_column("logs_purged_at")
