"""Make the per-run report limit configurable."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0010_report_limit"
down_revision: str | None = "0009_run_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_ITEM_COLUMNS = (
    "id",
    "run_request_id",
    "sequence",
    "status",
    "reason",
    "reason_code",
    "values_json",
    "reported_at_ms",
)


def upgrade() -> None:
    _backup_and_drop_items()
    with op.batch_alter_table("run_report", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_run_report_expected_total", type_="check")
        batch_op.drop_constraint("ck_run_report_reported_total", type_="check")
        batch_op.create_check_constraint(
            "ck_run_report_expected_total",
            "expected_total IS NULL OR (expected_total >= 0 AND expected_total <= 1000000)",
        )
        batch_op.create_check_constraint(
            "ck_run_report_reported_total",
            "reported_total >= 0 AND reported_total <= 1000000",
        )
    _recreate_and_restore_items()


def downgrade() -> None:
    connection = op.get_bind()
    incompatible = connection.execute(
        sa.text(
            "SELECT 1 FROM run_report "
            "WHERE expected_total > 5000 OR reported_total > 5000 LIMIT 1"
        )
    ).scalar()
    if incompatible is not None:
        raise RuntimeError("存在超过 5000 条的运行报表，不能安全降级到旧数据库约束")
    _backup_and_drop_items()
    with op.batch_alter_table("run_report", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_run_report_expected_total", type_="check")
        batch_op.drop_constraint("ck_run_report_reported_total", type_="check")
        batch_op.create_check_constraint(
            "ck_run_report_expected_total",
            "expected_total IS NULL OR (expected_total >= 0 AND expected_total <= 5000)",
        )
        batch_op.create_check_constraint(
            "ck_run_report_reported_total",
            "reported_total >= 0 AND reported_total <= 5000",
        )
    _recreate_and_restore_items()


def _backup_and_drop_items() -> None:
    op.create_table(
        "_run_report_item_0010_backup",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_request_id", sa.String(length=32), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=True),
        sa.Column("values_json", sa.Text(), nullable=False),
        sa.Column("reported_at_ms", sa.Integer(), nullable=False),
    )
    columns = ", ".join(_ITEM_COLUMNS)
    op.execute(
        sa.text(
            f"INSERT INTO _run_report_item_0010_backup ({columns}) "
            f"SELECT {columns} FROM run_report_item"
        )
    )
    op.drop_index("ix_run_report_item_run_status", table_name="run_report_item")
    op.drop_index("ix_run_report_item_run_sequence", table_name="run_report_item")
    op.drop_table("run_report_item")


def _recreate_and_restore_items() -> None:
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
    columns = ", ".join(_ITEM_COLUMNS)
    op.execute(
        sa.text(
            f"INSERT INTO run_report_item ({columns}) "
            f"SELECT {columns} FROM _run_report_item_0010_backup ORDER BY id"
        )
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
    op.drop_table("_run_report_item_0010_backup")
