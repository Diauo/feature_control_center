from __future__ import annotations

from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text as sql_text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "user"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'operator')", name="ck_user_role"),
        Index("ix_user_active_role", "is_active", "role"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    username_normalized: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    security_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)
    last_login_at: Mapped[int | None] = mapped_column(Integer)

    customer_links: Mapped[list[UserCustomerModel]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="UserCustomerModel.user_id",
        lazy="selectin",
    )
    menu_grants: Mapped[list[UserMenuGrantModel]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="UserMenuGrantModel.user_id",
        lazy="selectin",
    )


class CustomerModel(Base):
    __tablename__ = "customer"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)

    user_links: Mapped[list[UserCustomerModel]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class UserCustomerModel(Base):
    __tablename__ = "user_customer"
    __table_args__ = (UniqueConstraint("user_id", "customer_id", name="uq_user_customer"),)

    user_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,
    )
    customer_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("customer.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("user.id", ondelete="SET NULL"))
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)

    user: Mapped[UserModel] = relationship(
        back_populates="customer_links",
        foreign_keys=[user_id],
    )
    customer: Mapped[CustomerModel] = relationship(back_populates="user_links")


class UserMenuGrantModel(Base):
    __tablename__ = "user_menu_grant"
    __table_args__ = (
        CheckConstraint(
            "menu_key IN ('workspace', 'runs', 'schedules', 'feature_admin', 'users', 'customers', 'audit', 'settings')",
            name="ck_user_menu_grant_key",
        ),
    )

    user_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,
    )
    menu_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("user.id", ondelete="SET NULL"))
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)

    user: Mapped[UserModel] = relationship(
        back_populates="menu_grants",
        foreign_keys=[user_id],
    )


class SessionModel(Base):
    __tablename__ = "session"
    __table_args__ = (
        UniqueConstraint("token_digest", name="uq_session_token_digest"),
        Index("ix_session_user_active", "user_id", "revoked_at", "absolute_expires_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    token_digest: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    user_security_version: Mapped[int] = mapped_column(Integer, nullable=False)
    csrf_secret: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    last_seen_at: Mapped[int] = mapped_column(Integer, nullable=False)
    idle_expires_at: Mapped[int] = mapped_column(Integer, nullable=False)
    absolute_expires_at: Mapped[int] = mapped_column(Integer, nullable=False)
    reauthenticated_at: Mapped[int | None] = mapped_column(Integer)
    revoked_at: Mapped[int | None] = mapped_column(Integer)
    revoked_reason: Mapped[str | None] = mapped_column(String(64))
    created_ip: Mapped[str] = mapped_column(String(64), nullable=False)
    user_agent_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)

    user: Mapped[UserModel] = relationship(lazy="joined")


class BootstrapStateModel(Base):
    __tablename__ = "bootstrap_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_digest: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    used_at: Mapped[int | None] = mapped_column(Integer)


class LoginRateLimitModel(Base):
    __tablename__ = "login_rate_limit"

    bucket_key: Mapped[bytes] = mapped_column(LargeBinary(32), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, nullable=False)
    window_started_at: Mapped[int] = mapped_column(Integer, nullable=False)
    last_failure_at: Mapped[int] = mapped_column(Integer, nullable=False)
    locked_until: Mapped[int] = mapped_column(Integer, nullable=False)


class SystemSettingModel(Base):
    __tablename__ = "system_setting"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("user.id", ondelete="SET NULL"))


class AuditLogModel(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_occurred_at", "occurred_at"),
        Index("ix_audit_actor", "actor_user_id", "occurred_at"),
        Index("ix_audit_action", "action", "occurred_at"),
        Index("ix_audit_role", "actor_role", "occurred_at"),
        Index("ix_audit_customer", "customer_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("user.id", ondelete="SET NULL"))
    actor_role: Mapped[str | None] = mapped_column(String(16))
    actor_username: Mapped[str | None] = mapped_column(String(64))
    actor_display_name: Mapped[str | None] = mapped_column(String(64))
    session_id: Mapped[str | None] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[str | None] = mapped_column(String(64))
    target_name: Mapped[str | None] = mapped_column(String(120))
    customer_id: Mapped[str | None] = mapped_column(String(32))
    customer_name: Mapped[str | None] = mapped_column(String(120))
    client_ip: Mapped[str] = mapped_column(String(64), nullable=False)
    request_method: Mapped[str | None] = mapped_column(String(10))
    request_path: Mapped[str | None] = mapped_column(String(300))
    request_id: Mapped[str | None] = mapped_column(String(32))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    user_agent_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class FeatureDefinitionModel(Base):
    __tablename__ = "feature_definition"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("user.id", ondelete="SET NULL"))


class RuntimeEnvironmentModel(Base):
    __tablename__ = "runtime_environment"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PREPARING', 'READY', 'FAILED')",
            name="ck_runtime_environment_status",
        ),
        Index("ix_runtime_environment_status", "status", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    resolved_fingerprint: Mapped[str | None] = mapped_column(String(64))
    python_version: Mapped[str] = mapped_column(String(32), nullable=False)
    requirements_text: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_lock_text: Mapped[str | None] = mapped_column(Text)
    wheel_manifest_json: Mapped[str | None] = mapped_column(Text)
    environment_path: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    failure_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)


class FeatureVersionModel(Base):
    __tablename__ = "feature_version"
    __table_args__ = (
        UniqueConstraint("feature_definition_id", "version_number", name="uq_feature_version_number"),
        UniqueConstraint("feature_definition_id", "package_sha256", name="uq_feature_version_package"),
        CheckConstraint(
            "status IN ('PREPARING', 'READY', 'DEPENDENCY_FAILED')",
            name="ck_feature_version_status",
        ),
        Index("ix_feature_version_definition", "feature_definition_id", "version_number"),
        Index("ix_feature_version_environment", "runtime_environment_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    feature_definition_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("feature_definition.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    entrypoint: Mapped[str] = mapped_column(String(80), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_warnings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    config_schema_json: Mapped[str] = mapped_column(Text, nullable=False)
    data_source_schema_json: Mapped[str | None] = mapped_column(Text)
    package_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    package_sha256: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    package_size: Mapped[int] = mapped_column(Integer, nullable=False)
    package_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, deferred=True)
    source_encoding: Mapped[str] = mapped_column(String(32), nullable=False)
    requirements_text: Mapped[str] = mapped_column(Text, nullable=False)
    runtime_environment_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("runtime_environment.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    prepare_error: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("user.id", ondelete="SET NULL"))
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)


class FeatureVersionDefaultDataSourceModel(Base):
    __tablename__ = "feature_version_default_data_source"

    feature_version_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("feature_version.id", ondelete="CASCADE"), primary_key=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, deferred=True)


class CustomerFeatureModel(Base):
    __tablename__ = "customer_feature"
    __table_args__ = (
        UniqueConstraint("customer_id", "feature_definition_id", name="uq_customer_feature_definition"),
        CheckConstraint(
            "status IN ('PREPARING', 'ACTIVE', 'WAITING_DATA_SOURCE', 'DEPENDENCY_FAILED', 'DISABLED')",
            name="ck_customer_feature_status",
        ),
        Index("ix_customer_feature_customer", "customer_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("customer.id", ondelete="CASCADE"), nullable=False
    )
    feature_definition_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("feature_definition.id", ondelete="CASCADE"), nullable=False
    )
    feature_version_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("feature_version.id", ondelete="RESTRICT"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    max_runtime_seconds: Mapped[int | None] = mapped_column(Integer)
    current_data_source_revision_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("user.id", ondelete="SET NULL"))


class FeatureConfigValueModel(Base):
    __tablename__ = "feature_config_value"

    customer_feature_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("customer_feature.id", ondelete="CASCADE"), primary_key=True
    )
    config_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value_type: Mapped[str] = mapped_column(String(24), nullable=False)
    value_json: Mapped[str | None] = mapped_column(Text)
    encrypted_value: Mapped[bytes | None] = mapped_column(LargeBinary)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("user.id", ondelete="SET NULL"))


class CustomerFeatureDataSourceRevisionModel(Base):
    __tablename__ = "customer_feature_data_source_revision"
    __table_args__ = (
        UniqueConstraint("customer_feature_id", "revision_number", name="uq_customer_data_source_revision"),
        CheckConstraint("source_kind IN ('DEFAULT', 'UPLOAD')", name="ck_data_source_revision_kind"),
        Index("ix_data_source_customer_created", "customer_feature_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    customer_feature_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("customer_feature.id", ondelete="CASCADE"), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_feature_version_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("feature_version.id", ondelete="SET NULL")
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, deferred=True)
    uploaded_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("user.id", ondelete="SET NULL"))
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)


class ScheduledTaskModel(Base):
    __tablename__ = "scheduled_task"
    __table_args__ = (
        CheckConstraint(
            "last_outcome IS NULL OR last_outcome IN ('ENQUEUED', 'MISSED', 'SKIPPED_ACTIVE', "
            "'SKIPPED_UNAVAILABLE', 'QUEUE_FULL', 'DUPLICATE')",
            name="ck_scheduled_task_last_outcome",
        ),
        Index("ix_scheduled_task_customer", "customer_id", "created_at"),
        Index("ix_scheduled_task_due", "is_enabled", "next_run_at"),
        Index("ix_scheduled_task_feature", "customer_feature_id", "is_enabled"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("customer.id", ondelete="CASCADE"), nullable=False
    )
    customer_feature_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("customer_feature.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(120), nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    next_run_at: Mapped[int | None] = mapped_column(Integer)
    last_scheduled_for: Mapped[int | None] = mapped_column(Integer)
    last_handled_at: Mapped[int | None] = mapped_column(Integer)
    last_run_request_id: Mapped[str | None] = mapped_column(String(32))
    last_outcome: Mapped[str | None] = mapped_column(String(32))
    last_message: Mapped[str | None] = mapped_column(String(500))
    missed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("user.id", ondelete="SET NULL"))


class RunModel(Base):
    __tablename__ = "run"
    __table_args__ = (
        CheckConstraint(
            "status IN ('QUEUED', 'STARTING', 'RUNNING', 'STOPPING', 'SUCCEEDED', "
            "'FAILED', 'STOPPED', 'TIMED_OUT', 'INTERRUPTED')",
            name="ck_run_status",
        ),
        CheckConstraint("trigger_source IN ('MANUAL', 'SCHEDULED')", name="ck_run_trigger_source"),
        Index("ix_run_customer_queued", "customer_id", "queued_at"),
        Index("ix_run_status_queued", "status", "queued_at"),
        Index("ix_run_customer_feature_status", "customer_feature_id", "status"),
        Index("ix_run_log_retention", "logs_purged_at", "finished_at"),
        Index(
            "uq_run_active_customer_feature",
            "customer_feature_id",
            unique=True,
            sqlite_where=sql_text("status IN ('QUEUED', 'STARTING', 'RUNNING', 'STOPPING')"),
        ),
        UniqueConstraint("trigger_key", name="uq_run_trigger_key"),
    )

    request_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("customer.id", ondelete="RESTRICT"), nullable=False
    )
    customer_feature_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("customer_feature.id", ondelete="RESTRICT"), nullable=False
    )
    feature_version_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("feature_version.id", ondelete="RESTRICT"), nullable=False
    )
    data_source_revision_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("customer_feature_data_source_revision.id", ondelete="RESTRICT")
    )
    feature_name: Mapped[str] = mapped_column(String(120), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    data_source_filename: Mapped[str | None] = mapped_column(String(255))
    config_snapshot_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, deferred=True)
    secret_keys_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    trigger_source: Mapped[str] = mapped_column(String(16), nullable=False)
    trigger_key: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    queued_at: Mapped[int] = mapped_column(Integer, nullable=False)
    claimed_at: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[int | None] = mapped_column(Integer)
    stop_requested_at: Mapped[int | None] = mapped_column(Integer)
    term_sent_at: Mapped[int | None] = mapped_column(Integer)
    kill_sent_at: Mapped[int | None] = mapped_column(Integer)
    finished_at: Mapped[int | None] = mapped_column(Integer)
    exit_code: Mapped[int | None] = mapped_column(Integer)
    process_id: Mapped[int | None] = mapped_column(Integer)
    failure_summary: Mapped[str | None] = mapped_column(Text)
    stop_reason: Mapped[str | None] = mapped_column(String(64))
    runner_id: Mapped[str | None] = mapped_column(String(64))
    runner_heartbeat_at: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("user.id", ondelete="SET NULL"))
    max_runtime_seconds: Mapped[int | None] = mapped_column(Integer)
    last_event_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    final_event_sequence: Mapped[int | None] = mapped_column(Integer)
    logs_purged_at: Mapped[int | None] = mapped_column(Integer)


class RunReportModel(Base):
    __tablename__ = "run_report"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN', 'COMPLETE', 'INCOMPLETE')", name="ck_run_report_status"),
        CheckConstraint(
            "expected_total IS NULL OR (expected_total >= 0 AND expected_total <= 1000000)",
            name="ck_run_report_expected_total",
        ),
        CheckConstraint(
            "reported_total >= 0 AND reported_total <= 1000000",
            name="ck_run_report_reported_total",
        ),
        CheckConstraint(
            "success_count >= 0 AND failed_count >= 0 AND no_data_count >= 0 "
            "AND skipped_count >= 0 AND unfinished_count >= 0",
            name="ck_run_report_counts",
        ),
        CheckConstraint("validation_error_count >= 0", name="ck_run_report_validation_errors"),
    )

    run_request_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("run.request_id", ondelete="CASCADE"), primary_key=True
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    item_label: Mapped[str] = mapped_column(String(40), nullable=False)
    schema_json: Mapped[str] = mapped_column(Text, nullable=False)
    expected_total: Mapped[int | None] = mapped_column(Integer)
    reported_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    no_data_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unfinished_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validation_error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN")
    started_at: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_requested_at: Mapped[int | None] = mapped_column(Integer)
    completed_at: Mapped[int | None] = mapped_column(Integer)
    details_purged_at: Mapped[int | None] = mapped_column(Integer)


class RunReportItemModel(Base):
    __tablename__ = "run_report_item"
    __table_args__ = (
        CheckConstraint(
            "status IN ('SUCCESS', 'FAILED', 'NO_DATA', 'SKIPPED', 'UNFINISHED')",
            name="ck_run_report_item_status",
        ),
        UniqueConstraint("run_request_id", "sequence", name="uq_run_report_item_sequence"),
        Index("ix_run_report_item_run_sequence", "run_request_id", "sequence"),
        Index("ix_run_report_item_run_status", "run_request_id", "status", "sequence"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_request_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("run_report.run_request_id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    reason_code: Mapped[str | None] = mapped_column(String(80))
    values_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    reported_at_ms: Mapped[int] = mapped_column(Integer, nullable=False)


class RunEventModel(Base):
    __tablename__ = "run_event"
    __table_args__ = (
        CheckConstraint("level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR')", name="ck_run_event_level"),
        CheckConstraint("source IN ('PLATFORM', 'SDK', 'STDOUT', 'STDERR')", name="ck_run_event_source"),
        UniqueConstraint("run_request_id", "sequence", name="uq_run_event_sequence"),
        Index("ix_run_event_run_sequence", "run_request_id", "sequence"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_request_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("run.request_id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class RunnerHeartbeatModel(Base):
    __tablename__ = "runner_heartbeat"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'STOPPING')", name="ck_runner_heartbeat_status"),
    )

    runner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    instance_token: Mapped[str] = mapped_column(String(64), nullable=False)
    process_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[int] = mapped_column(Integer, nullable=False)
    heartbeat_at: Mapped[int] = mapped_column(Integer, nullable=False)


class SchedulerHeartbeatModel(Base):
    __tablename__ = "scheduler_heartbeat"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'STOPPING')", name="ck_scheduler_heartbeat_status"),
    )

    scheduler_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    instance_token: Mapped[str] = mapped_column(String(64), nullable=False)
    process_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[int] = mapped_column(Integer, nullable=False)
    heartbeat_at: Mapped[int] = mapped_column(Integer, nullable=False)


class SystemUpdateModel(Base):
    __tablename__ = "system_update"
    __table_args__ = (
        CheckConstraint("operation IN ('APPLY', 'ROLLBACK')", name="ck_system_update_operation"),
        CheckConstraint(
            "status IN ('READY', 'PENDING', 'APPLYING', 'SUCCEEDED', 'FAILED', 'ROLLED_BACK')",
            name="ck_system_update_status",
        ),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_system_update_progress"),
        Index("ix_system_update_created", "created_at"),
        Index(
            "uq_system_update_active",
            "active_guard",
            unique=True,
            sqlite_where=sql_text("active_guard IS NOT NULL"),
        ),
        Index("ix_system_update_package_sha", "package_sha256"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    source_version: Mapped[str] = mapped_column(String(32), nullable=False)
    target_version: Mapped[str] = mapped_column(String(32), nullable=False)
    package_filename: Mapped[str | None] = mapped_column(String(255))
    package_sha256: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    package_size: Mapped[int | None] = mapped_column(Integer)
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    release_notes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_guard: Mapped[int | None] = mapped_column(Integer)
    rollback_compatible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    backup_filename: Mapped[str | None] = mapped_column(String(255))
    release_descriptor_json: Mapped[str | None] = mapped_column(Text)
    previous_release_json: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("user.id", ondelete="SET NULL"))
    actor_display_name: Mapped[str | None] = mapped_column(String(64))
    client_ip: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_at: Mapped[int | None] = mapped_column(Integer)


JsonValue = str | int | float | bool | None | list[Any] | dict[str, Any]
