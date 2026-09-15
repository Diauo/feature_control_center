"""Create Phase B feature, configuration, data source, and runtime environment tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0002_phase_b"
down_revision: str | None = "0001_phase_a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feature_definition",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("name_normalized", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name_normalized"),
    )
    op.create_table(
        "runtime_environment",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("resolved_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("python_version", sa.String(length=32), nullable=False),
        sa.Column("requirements_text", sa.Text(), nullable=False),
        sa.Column("resolved_lock_text", sa.Text(), nullable=True),
        sa.Column("wheel_manifest_json", sa.Text(), nullable=True),
        sa.Column("environment_path", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("failure_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.CheckConstraint("status IN ('PREPARING', 'READY', 'FAILED')", name="ck_runtime_environment_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_fingerprint"),
    )
    op.create_index("ix_runtime_environment_status", "runtime_environment", ["status", "updated_at"])
    op.create_table(
        "feature_version",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("feature_definition_id", sa.String(length=32), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("entrypoint", sa.String(length=80), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("metadata_warnings_json", sa.Text(), nullable=False),
        sa.Column("config_schema_json", sa.Text(), nullable=False),
        sa.Column("data_source_schema_json", sa.Text(), nullable=True),
        sa.Column("package_filename", sa.String(length=255), nullable=False),
        sa.Column("package_sha256", sa.LargeBinary(length=32), nullable=False),
        sa.Column("package_size", sa.Integer(), nullable=False),
        sa.Column("package_blob", sa.LargeBinary(), nullable=False),
        sa.Column("source_encoding", sa.String(length=32), nullable=False),
        sa.Column("requirements_text", sa.Text(), nullable=False),
        sa.Column("runtime_environment_id", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("prepare_error", sa.Text(), nullable=True),
        sa.Column("uploaded_by", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('PREPARING', 'READY', 'DEPENDENCY_FAILED')",
            name="ck_feature_version_status",
        ),
        sa.ForeignKeyConstraint(["feature_definition_id"], ["feature_definition.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["runtime_environment_id"], ["runtime_environment.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feature_definition_id", "package_sha256", name="uq_feature_version_package"),
        sa.UniqueConstraint("feature_definition_id", "version_number", name="uq_feature_version_number"),
    )
    op.create_index("ix_feature_version_definition", "feature_version", ["feature_definition_id", "version_number"])
    op.create_index("ix_feature_version_environment", "feature_version", ["runtime_environment_id", "status"])
    op.create_table(
        "feature_version_default_data_source",
        sa.Column("feature_version_id", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.LargeBinary(length=32), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(["feature_version_id"], ["feature_version.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("feature_version_id"),
    )
    op.create_table(
        "customer_feature",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("customer_id", sa.String(length=32), nullable=False),
        sa.Column("feature_definition_id", sa.String(length=32), nullable=False),
        sa.Column("feature_version_id", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_data_source_revision_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.CheckConstraint(
            "status IN ('PREPARING', 'ACTIVE', 'WAITING_DATA_SOURCE', 'DEPENDENCY_FAILED', 'DISABLED')",
            name="ck_customer_feature_status",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["feature_definition_id"], ["feature_definition.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["feature_version_id"], ["feature_version.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_id", "feature_definition_id", name="uq_customer_feature_definition"),
    )
    op.create_index("ix_customer_feature_customer", "customer_feature", ["customer_id", "status"])
    op.create_table(
        "feature_config_value",
        sa.Column("customer_feature_id", sa.String(length=32), nullable=False),
        sa.Column("config_key", sa.String(length=80), nullable=False),
        sa.Column("value_type", sa.String(length=24), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=True),
        sa.Column("encrypted_value", sa.LargeBinary(), nullable=True),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["customer_feature_id"], ["customer_feature.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("customer_feature_id", "config_key"),
    )
    op.create_table(
        "customer_feature_data_source_revision",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("customer_feature_id", sa.String(length=32), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        sa.Column("source_feature_version_id", sa.String(length=32), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.LargeBinary(length=32), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("uploaded_by", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.CheckConstraint("source_kind IN ('DEFAULT', 'UPLOAD')", name="ck_data_source_revision_kind"),
        sa.ForeignKeyConstraint(["customer_feature_id"], ["customer_feature.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_feature_version_id"], ["feature_version.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_feature_id", "revision_number", name="uq_customer_data_source_revision"),
    )
    op.create_index(
        "ix_data_source_customer_created",
        "customer_feature_data_source_revision",
        ["customer_feature_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_data_source_customer_created", table_name="customer_feature_data_source_revision")
    op.drop_table("customer_feature_data_source_revision")
    op.drop_table("feature_config_value")
    op.drop_index("ix_customer_feature_customer", table_name="customer_feature")
    op.drop_table("customer_feature")
    op.drop_table("feature_version_default_data_source")
    op.drop_index("ix_feature_version_environment", table_name="feature_version")
    op.drop_index("ix_feature_version_definition", table_name="feature_version")
    op.drop_table("feature_version")
    op.drop_index("ix_runtime_environment_status", table_name="runtime_environment")
    op.drop_table("runtime_environment")
    op.drop_table("feature_definition")
