"""Allow repeatable signed-package installation attempts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0008_scope_paging_update"
down_revision: str | None = "0007_system_updates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("uq_system_update_package_sha", table_name="system_update")
    op.create_index("ix_system_update_package_sha", "system_update", ["package_sha256"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_system_update_package_sha", table_name="system_update")
    op.create_index(
        "uq_system_update_package_sha",
        "system_update",
        ["package_sha256"],
        unique=True,
        sqlite_where=sa.text("package_sha256 IS NOT NULL"),
    )
