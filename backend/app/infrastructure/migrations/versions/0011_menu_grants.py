"""Add per-user menu grants for operator accounts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0011_menu_grants"
down_revision: str | None = "0010_report_limit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_MENU_KEYS = "'workspace', 'runs', 'schedules', 'feature_admin', 'users', 'customers', 'audit', 'settings'"
_LEGACY_OPERATOR_MENUS = ("workspace", "runs", "schedules")


def upgrade() -> None:
    op.create_table(
        "user_menu_grant",
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("menu_key", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.CheckConstraint(f"menu_key IN ({_MENU_KEYS})", name="ck_user_menu_grant_key"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("user_id", "menu_key"),
    )
    for menu_key in _LEGACY_OPERATOR_MENUS:
        op.execute(
            "INSERT INTO user_menu_grant (user_id, menu_key, created_at) "
            f"SELECT id, '{menu_key}', CAST(strftime('%s','now') AS INTEGER) FROM user "
            "WHERE role = 'operator'"
        )


def downgrade() -> None:
    op.drop_table("user_menu_grant")
