"""Add signed system update state."""

from collections.abc import Sequence
import json
import time

import sqlalchemy as sa
from alembic import op


revision: str = "0007_system_updates"
down_revision: str | None = "0006_platform_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_update",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("source_version", sa.String(length=32), nullable=False),
        sa.Column("target_version", sa.String(length=32), nullable=False),
        sa.Column("package_filename", sa.String(length=255), nullable=True),
        sa.Column("package_sha256", sa.LargeBinary(length=32), nullable=True),
        sa.Column("package_size", sa.Integer(), nullable=True),
        sa.Column("manifest_json", sa.Text(), nullable=False),
        sa.Column("release_notes_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("active_guard", sa.Integer(), nullable=True),
        sa.Column("rollback_compatible", sa.Boolean(), nullable=False),
        sa.Column("backup_filename", sa.String(length=255), nullable=True),
        sa.Column("release_descriptor_json", sa.Text(), nullable=True),
        sa.Column("previous_release_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.Column("actor_display_name", sa.String(length=64), nullable=True),
        sa.Column("client_ip", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.Integer(), nullable=True),
        sa.CheckConstraint("operation IN ('APPLY', 'ROLLBACK')", name="ck_system_update_operation"),
        sa.CheckConstraint(
            "status IN ('READY', 'PENDING', 'APPLYING', 'SUCCEEDED', 'FAILED', 'ROLLED_BACK')",
            name="ck_system_update_status",
        ),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="ck_system_update_progress"),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_system_update_created", "system_update", ["created_at"], unique=False)
    op.create_index(
        "uq_system_update_active",
        "system_update",
        ["active_guard"],
        unique=True,
        sqlite_where=sa.text("active_guard IS NOT NULL"),
    )
    op.create_index(
        "uq_system_update_package_sha",
        "system_update",
        ["package_sha256"],
        unique=True,
        sqlite_where=sa.text("package_sha256 IS NOT NULL"),
    )
    # RAR became a first-class option in this release. Only advance installations
    # that still use the old untouched default; a deliberate administrator choice
    # remains untouched.
    connection = op.get_bind()
    row = connection.execute(
        sa.text("SELECT value_json FROM system_setting WHERE key = :key"),
        {"key": "feature.allowed_package_formats"},
    ).scalar_one_or_none()
    old_default = ["zip", "7z", "tar", "tar_gz", "tar_bz2", "tar_xz"]
    if row is not None:
        try:
            current = json.loads(row)
        except (TypeError, ValueError, json.JSONDecodeError):
            current = None
        if current == old_default:
            connection.execute(
                sa.text(
                    "UPDATE system_setting SET value_json = :value, updated_at = :updated_at "
                    "WHERE key = :key"
                ),
                {
                    "key": "feature.allowed_package_formats",
                    "value": json.dumps(["zip", "7z", "rar", "tar", "tar_gz", "tar_bz2", "tar_xz"]),
                    "updated_at": int(time.time()),
                },
            )


def downgrade() -> None:
    connection = op.get_bind()
    row = connection.execute(
        sa.text("SELECT value_json FROM system_setting WHERE key = :key"),
        {"key": "feature.allowed_package_formats"},
    ).scalar_one_or_none()
    new_default = ["zip", "7z", "rar", "tar", "tar_gz", "tar_bz2", "tar_xz"]
    if row is not None:
        try:
            current = json.loads(row)
        except (TypeError, ValueError, json.JSONDecodeError):
            current = None
        if current == new_default:
            connection.execute(
                sa.text(
                    "UPDATE system_setting SET value_json = :value, updated_at = :updated_at "
                    "WHERE key = :key"
                ),
                {
                    "key": "feature.allowed_package_formats",
                    "value": json.dumps(["zip", "7z", "tar", "tar_gz", "tar_bz2", "tar_xz"]),
                    "updated_at": int(time.time()),
                },
            )
    op.drop_index("uq_system_update_package_sha", table_name="system_update")
    op.drop_index("uq_system_update_active", table_name="system_update")
    op.drop_index("ix_system_update_created", table_name="system_update")
    op.drop_table("system_update")
