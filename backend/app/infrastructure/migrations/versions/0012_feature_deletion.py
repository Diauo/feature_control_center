"""Add soft-delete markers to customer features."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0012_feature_deletion"
down_revision: str | None = "0011_menu_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "customer_feature",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("customer_feature", sa.Column("deleted_at", sa.Integer(), nullable=True))
    op.add_column("customer_feature", sa.Column("deleted_by", sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("customer_feature", recreate="always") as batch_op:
        batch_op.drop_column("deleted_by")
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("is_deleted")
