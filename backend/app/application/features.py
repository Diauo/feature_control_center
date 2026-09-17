from __future__ import annotations

import hashlib
import json
import sys
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import undefer

from app.application.audit import RequestMetadata, add_audit
from app.application.auth import AuthContext, AuthService
from app.application.errors import ApplicationError, AuthorizationError, ConflictError
from app.application.settings import SettingsService
from app.domain.feature_metadata import validate_config_value
from app.domain.identity import MenuKey, UserRole, ValidationError
from app.domain.time import Clock
from app.infrastructure.database import Database
from app.infrastructure.models import (
    CustomerFeatureDataSourceRevisionModel,
    CustomerFeatureModel,
    CustomerModel,
    FeatureConfigValueModel,
    FeatureDefinitionModel,
    FeatureVersionDefaultDataSourceModel,
    FeatureVersionModel,
    RunModel,
    RuntimeEnvironmentModel,
    ScheduledTaskModel,
    UserCustomerModel,
)
from app.infrastructure.package_inspector import FeaturePackageInspector
from app.infrastructure.runtime_environment import dependency_request_fingerprint
from app.security.config_cipher import ConfigCipher


_UNSET = Ellipsis


@dataclass(frozen=True, slots=True)
class DownloadedFile:
    filename: str
    content: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class ExecutionInputs:
    customer_feature_id: str
    feature_version_id: str
    data_source_revision_id: str | None
    config: dict[str, Any]


class FeatureService:
    def __init__(
        self,
        database: Database,
        settings: SettingsService,
        auth: AuthService,
        clock: Clock,
        inspector: FeaturePackageInspector,
        cipher: ConfigCipher,
    ) -> None:
        self.database = database
        self.settings = settings
        self.auth = auth
        self.clock = clock
        self.inspector = inspector
        self.cipher = cipher

    def register_package(
        self,
        *,
        actor: AuthContext,
        customer_id: str,
        filename: str,
        content: bytes,
        request: RequestMetadata,
    ) -> dict[str, Any]:
        self._require_menu(actor, MenuKey.FEATURE_ADMIN)
        self.auth.require_recent_auth(actor)
        try:
            package = self.inspector.inspect(
                filename,
                content,
                self.settings.package_limits(),
                self.settings.allowed_package_formats(),
            )
            if package.default_data_source and (
                not package.default_data_source.content
                or len(package.default_data_source.content) > self.settings.data_source_max_bytes()
            ):
                raise ValidationError("DEFAULT_DATA_SOURCE_SIZE_INVALID", "包内默认数据源为空或超过系统大小限制")
        except ValidationError as exc:
            with self.database.session() as db:
                add_audit(
                    db,
                    now=self.clock.now(),
                    request=request,
                    action="admin.feature_version.upload",
                    outcome="denied",
                    actor_user_id=actor.user_id,
                    session_id=actor.session_id,
                    target_type="feature_package",
                    details={"errorCode": exc.code, "packageSize": len(content)},
                )
            raise
        now = self.clock.now()
        with self.database.session() as db:
            self._require_customer_access(db, actor, customer_id)
            normalized_name = unicodedata.normalize("NFKC", package.metadata.name).strip().casefold()
            definition = db.scalar(
                select(FeatureDefinitionModel).where(FeatureDefinitionModel.name_normalized == normalized_name)
            )
            if definition is None:
                definition = FeatureDefinitionModel(
                    id=uuid.uuid4().hex,
                    name=package.metadata.name,
                    name_normalized=normalized_name,
                    created_at=now,
                    created_by=actor.user_id,
                )
                db.add(definition)
                db.flush()
            duplicate = db.scalar(
                select(FeatureVersionModel.id).where(
                    FeatureVersionModel.feature_definition_id == definition.id,
                    FeatureVersionModel.package_sha256 == package.package_sha256,
                )
            )
            if duplicate:
                deleted_registration = db.scalar(select(CustomerFeatureModel).where(
                    CustomerFeatureModel.customer_id == customer_id,
                    CustomerFeatureModel.feature_definition_id == definition.id,
                    CustomerFeatureModel.is_deleted.is_(True),
                ))
                duplicate_version = db.get(FeatureVersionModel, duplicate) if deleted_registration else None
                if duplicate_version is None or duplicate_version.status not in ("READY", "PREPARING"):
                    raise ConflictError("FEATURE_PACKAGE_EXISTS", "这个功能包内容已经登记过", status=409)
                default = db.scalar(
                    select(FeatureVersionDefaultDataSourceModel)
                    .options(undefer(FeatureVersionDefaultDataSourceModel.content))
                    .where(FeatureVersionDefaultDataSourceModel.feature_version_id == duplicate_version.id)
                )
                self._revive_customer_feature(
                    db,
                    deleted_registration,
                    version=duplicate_version,
                    config_schema=self._config_schema(duplicate_version),
                    data_schema=self._data_schema(duplicate_version),
                    default_source=default,
                    actor_user_id=actor.user_id,
                    now=now,
                )
                add_audit(
                    db,
                    now=now,
                    request=request,
                    action="admin.feature_version.upload",
                    outcome="success",
                    actor_user_id=actor.user_id,
                    session_id=actor.session_id,
                    target_type="feature_version",
                    target_id=duplicate_version.id,
                    details={"definitionId": definition.id, "version": duplicate_version.version_number, "customerId": customer_id, "restored": True},
                )
                return {"version": self.get_version(duplicate_version.id), "activatedForCustomer": True, "restored": True}
            version_number = (db.scalar(select(func.max(FeatureVersionModel.version_number)).where(
                FeatureVersionModel.feature_definition_id == definition.id
            )) or 0) + 1
            environment: RuntimeEnvironmentModel | None = None
            version_status = "READY"
            prepare_error = None
            if package.requirements_text:
                fingerprint = dependency_request_fingerprint(package.requirements_text, package.offline_wheels)
                environment = db.scalar(
                    select(RuntimeEnvironmentModel).where(RuntimeEnvironmentModel.request_fingerprint == fingerprint)
                )
                if environment is None:
                    environment = RuntimeEnvironmentModel(
                        id=uuid.uuid4().hex,
                        request_fingerprint=fingerprint,
                        resolved_fingerprint=None,
                        python_version=f"{sys.version_info.major}.{sys.version_info.minor}",
                        requirements_text=package.requirements_text,
                        resolved_lock_text=None,
                        wheel_manifest_json=None,
                        environment_path=None,
                        status="PREPARING",
                        failure_summary=None,
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(environment)
                    db.flush()
                    version_status = "PREPARING"
                elif environment.status == "READY":
                    version_status = "READY"
                elif environment.status == "FAILED":
                    environment.status = "PREPARING"
                    environment.failure_summary = None
                    environment.updated_at = now
                    version_status = "PREPARING"
                else:
                    version_status = "PREPARING"
            version = FeatureVersionModel(
                id=uuid.uuid4().hex,
                feature_definition_id=definition.id,
                version_number=version_number,
                name=package.metadata.name,
                description=package.metadata.description,
                entrypoint=package.metadata.entrypoint,
                metadata_json=json.dumps(package.metadata.as_dict(), ensure_ascii=False, separators=(",", ":")),
                metadata_warnings_json=json.dumps(package.metadata.warnings, ensure_ascii=False),
                config_schema_json=json.dumps(package.metadata.config_schema, ensure_ascii=False, separators=(",", ":")),
                data_source_schema_json=json.dumps(package.metadata.data_source_schema, ensure_ascii=False, separators=(",", ":")) if package.metadata.data_source_schema else None,
                package_filename=package.package_filename,
                package_sha256=package.package_sha256,
                package_size=len(package.package_content),
                package_blob=package.package_content,
                source_encoding=package.source_encoding,
                requirements_text=package.requirements_text,
                runtime_environment_id=environment.id if environment else None,
                status=version_status,
                prepare_error=prepare_error,
                uploaded_by=actor.user_id,
                created_at=now,
            )
            db.add(version)
            db.flush()
            if package.default_data_source:
                default = package.default_data_source
                db.add(FeatureVersionDefaultDataSourceModel(
                    feature_version_id=version.id,
                    filename=default.filename,
                    size=len(default.content),
                    sha256=default.sha256,
                    content=default.content,
                ))
            customer_feature = db.scalar(select(CustomerFeatureModel).where(
                CustomerFeatureModel.customer_id == customer_id,
                CustomerFeatureModel.feature_definition_id == definition.id,
            ))
            restored = customer_feature is not None and customer_feature.is_deleted
            if restored:
                self._revive_customer_feature(
                    db,
                    customer_feature,
                    version=version,
                    config_schema=package.metadata.config_schema,
                    data_schema=package.metadata.data_source_schema,
                    default_source=package.default_data_source,
                    actor_user_id=actor.user_id,
                    now=now,
                )
            activated = customer_feature is None or restored
            if customer_feature is None:
                customer_feature = CustomerFeatureModel(
                    id=uuid.uuid4().hex,
                    customer_id=customer_id,
                    feature_definition_id=definition.id,
                    feature_version_id=version.id,
                    display_name=version.name,
                    description=version.description,
                    is_enabled=True,
                    status="PREPARING" if version.status == "PREPARING" else "ACTIVE",
                    current_data_source_revision_id=None,
                    created_at=now,
                    updated_at=now,
                    created_by=actor.user_id,
                )
                db.add(customer_feature)
                db.flush()
                self._initialize_config_defaults(db, customer_feature.id, package.metadata.config_schema, actor.user_id, now)
                if package.default_data_source:
                    revision = self._create_data_source_revision(
                        db, customer_feature.id, 1, "DEFAULT", version.id,
                        package.default_data_source.filename, package.default_data_source.content, actor.user_id, now,
                    )
                    customer_feature.current_data_source_revision_id = revision.id
                customer_feature.status = self._derive_status(customer_feature, version, package.metadata.data_source_schema)
            add_audit(
                db,
                now=now,
                request=request,
                action="admin.feature_version.upload",
                outcome="success",
                actor_user_id=actor.user_id,
                session_id=actor.session_id,
                target_type="feature_version",
                target_id=version.id,
                details={"definitionId": definition.id, "version": version_number, "customerId": customer_id, "activated": activated, "restored": restored},
            )
            version_id = version.id
        return {"version": self.get_version(version_id), "activatedForCustomer": activated, "restored": restored}

    def retry_prepare(self, *, actor: AuthContext, version_id: str, request: RequestMetadata) -> dict[str, Any]:
        self._require_menu(actor, MenuKey.FEATURE_ADMIN)
        self.auth.require_recent_auth(actor)
        with self.database.session() as db:
            version = db.scalar(select(FeatureVersionModel).where(
                FeatureVersionModel.id == version_id
            ))
            if version is None:
                raise ConflictError("FEATURE_VERSION_NOT_FOUND", "功能版本不存在", status=404)
            if not version.runtime_environment_id:
                return self._version_dict(db, version)
            environment = db.get(RuntimeEnvironmentModel, version.runtime_environment_id)
            if environment is None:
                raise ConflictError("ENVIRONMENT_NOT_FOUND", "依赖环境记录不存在", status=409)
            environment.status = "PREPARING"
            environment.failure_summary = None
            environment.updated_at = self.clock.now()
            linked = db.scalars(select(FeatureVersionModel).where(
                FeatureVersionModel.runtime_environment_id == environment.id
            )).all()
            for item in linked:
                item.status = "PREPARING"
                item.prepare_error = None
            add_audit(db, now=self.clock.now(), request=request, action="admin.feature_version.prepare.retry", outcome="success", actor_user_id=actor.user_id, session_id=actor.session_id, target_type="feature_version", target_id=version.id)
        return self.get_version(version_id)

    def list_definitions(self, *, page: int = 1, page_size: int = 20) -> tuple[list[dict[str, Any]], int]:
        with self.database.session() as db:
            total = int(db.scalar(select(func.count(FeatureDefinitionModel.id))) or 0)
            definitions = db.scalars(
                select(FeatureDefinitionModel)
                .order_by(FeatureDefinitionModel.name)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            result = []
            for definition in definitions:
                versions = db.scalars(select(FeatureVersionModel).where(
                    FeatureVersionModel.feature_definition_id == definition.id
                ).order_by(FeatureVersionModel.version_number.desc())).all()
                result.append({
                    "id": definition.id,
                    "name": definition.name,
                    "createdAt": definition.created_at,
                    "versions": [self._version_dict(db, version) for version in versions],
                })
            return result, total

    def get_version(self, version_id: str) -> dict[str, Any]:
        with self.database.session() as db:
            version = db.get(FeatureVersionModel, version_id)
            if version is None:
                raise ConflictError("FEATURE_VERSION_NOT_FOUND", "功能版本不存在", status=404)
            return self._version_dict(db, version)

    def list_customer_features(self, actor: AuthContext, customer_id: str) -> list[dict[str, Any]]:
        with self.database.session() as db:
            customer = self._require_customer_access(db, actor, customer_id)
            rows = db.scalars(select(CustomerFeatureModel).where(
                CustomerFeatureModel.customer_id == customer_id,
                CustomerFeatureModel.is_deleted.is_(False),
            ).order_by(CustomerFeatureModel.display_name)).all()
            return [self._customer_feature_dict(db, row, customer_name=customer.name) for row in rows]

    def list_scoped_customer_features(
        self,
        actor: AuthContext,
        *,
        customer_id: str | None,
        page: int,
        page_size: int,
        search: str = "",
        status: str = "",
    ) -> tuple[list[dict[str, Any]], int]:
        if status and status not in {"PREPARING", "ACTIVE", "WAITING_DATA_SOURCE", "DEPENDENCY_FAILED", "DISABLED"}:
            raise ConflictError("INVALID_FEATURE_STATUS", "功能状态筛选值无效")
        with self.database.session() as db:
            statement = select(CustomerFeatureModel, CustomerModel.name).join(
                CustomerModel, CustomerModel.id == CustomerFeatureModel.customer_id
            ).where(
                CustomerModel.is_active.is_(True),
                CustomerFeatureModel.is_deleted.is_(False),
            )
            if customer_id:
                self._require_customer_access(db, actor, customer_id)
                statement = statement.where(CustomerFeatureModel.customer_id == customer_id)
            elif actor.role is not UserRole.ADMIN:
                statement = statement.join(
                    UserCustomerModel,
                    UserCustomerModel.customer_id == CustomerFeatureModel.customer_id,
                ).where(UserCustomerModel.user_id == actor.user_id)
            if search.strip():
                token = f"%{search.strip()[:120]}%"
                statement = statement.where(
                    CustomerFeatureModel.display_name.ilike(token) | CustomerModel.name.ilike(token)
                )
            if status:
                statement = statement.where(CustomerFeatureModel.status == status)
            total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
            rows = db.execute(
                statement.order_by(CustomerModel.name, CustomerFeatureModel.display_name)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            return [self._customer_feature_dict(db, feature, customer_name=name) for feature, name in rows], total

    def copy_to_customers(
        self,
        *,
        actor: AuthContext,
        source_customer_feature_id: str,
        target_customer_ids: list[str],
        request: RequestMetadata,
    ) -> list[dict[str, Any]]:
        """Share immutable code while creating customer-owned defaults and data-source rows."""
        self._require_menu(actor, MenuKey.FEATURE_ADMIN)
        self.auth.require_recent_auth(actor)
        unique_targets = list(dict.fromkeys(item.strip() for item in target_customer_ids if item.strip()))
        if not unique_targets:
            raise ConflictError("COPY_TARGET_REQUIRED", "请至少选择一个目标客户")
        if len(unique_targets) > 200:
            raise ConflictError("COPY_TARGET_LIMIT", "一次最多复制到 200 个客户")

        with self.database.session() as db:
            source = self._require_customer_feature(db, actor, source_customer_feature_id)
            source_customer_id = source.customer_id
            definition_id = source.feature_definition_id
            version_id = source.feature_version_id
            version = db.get(FeatureVersionModel, version_id)
            if version is None or version.status != "READY":
                raise ConflictError("VERSION_NOT_READY", "来源功能的当前版本尚未准备完成", status=409)

        results: list[dict[str, Any]] = []
        for customer_id in unique_targets:
            try:
                result = self._copy_to_customer(
                    actor=actor,
                    source_customer_id=source_customer_id,
                    definition_id=definition_id,
                    version_id=version_id,
                    target_customer_id=customer_id,
                    request=request,
                )
            except ApplicationError as exc:
                result = {
                    "customerId": customer_id,
                    "status": "FAILED",
                    "customerFeatureId": None,
                    "message": exc.message,
                    "errorCode": exc.code,
                }
                with self.database.session() as db:
                    add_audit(
                        db,
                        now=self.clock.now(),
                        request=request,
                        action="admin.customer_feature.copy",
                        outcome="denied",
                        actor_user_id=actor.user_id,
                        session_id=actor.session_id,
                        target_type="customer",
                        target_id=customer_id,
                        details={
                            "sourceCustomerFeatureId": source_customer_feature_id,
                            "errorCode": exc.code,
                        },
                    )
            except IntegrityError:
                result = {
                    "customerId": customer_id,
                    "status": "FAILED",
                    "customerFeatureId": None,
                    "message": "目标客户状态刚刚发生变化，请刷新后重试",
                    "errorCode": "COPY_CONCURRENT_CHANGE",
                }
                with self.database.session() as db:
                    add_audit(
                        db,
                        now=self.clock.now(),
                        request=request,
                        action="admin.customer_feature.copy",
                        outcome="denied",
                        actor_user_id=actor.user_id,
                        session_id=actor.session_id,
                        target_type="customer",
                        target_id=customer_id,
                        details={
                            "sourceCustomerFeatureId": source_customer_feature_id,
                            "errorCode": "COPY_CONCURRENT_CHANGE",
                        },
                    )
            results.append(result)
        return results

    def _copy_to_customer(
        self,
        *,
        actor: AuthContext,
        source_customer_id: str,
        definition_id: str,
        version_id: str,
        target_customer_id: str,
        request: RequestMetadata,
    ) -> dict[str, Any]:
        if target_customer_id == source_customer_id:
            raise ConflictError("COPY_SOURCE_CUSTOMER", "不能把功能复制回来源客户")
        now = self.clock.now()
        with self.database.session() as db:
            target = db.get(CustomerModel, target_customer_id)
            if target is None or not target.is_active:
                raise ConflictError("CUSTOMER_NOT_AVAILABLE", "目标客户不存在或已停用", status=404)
            version = db.get(FeatureVersionModel, version_id)
            if version is None or version.status != "READY" or version.feature_definition_id != definition_id:
                raise ConflictError("VERSION_NOT_READY", "来源功能版本已不可用", status=409)
            existing = db.scalar(
                select(CustomerFeatureModel).where(
                    CustomerFeatureModel.customer_id == target_customer_id,
                    CustomerFeatureModel.feature_definition_id == definition_id,
                )
            )
            if existing is not None and existing.is_deleted:
                default = db.scalar(
                    select(FeatureVersionDefaultDataSourceModel)
                    .options(undefer(FeatureVersionDefaultDataSourceModel.content))
                    .where(FeatureVersionDefaultDataSourceModel.feature_version_id == version.id)
                )
                self._revive_customer_feature(
                    db,
                    existing,
                    version=version,
                    config_schema=self._config_schema(version),
                    data_schema=self._data_schema(version),
                    default_source=default,
                    actor_user_id=actor.user_id,
                    now=now,
                )
                add_audit(
                    db,
                    now=now,
                    request=request,
                    action="admin.customer_feature.copy",
                    outcome="success",
                    actor_user_id=actor.user_id,
                    session_id=actor.session_id,
                    target_type="customer_feature",
                    target_id=existing.id,
                    details={"sourceCustomerId": source_customer_id, "targetCustomerId": target_customer_id, "restored": True},
                )
                return {
                    "customerId": target_customer_id,
                    "status": "COPIED",
                    "customerFeatureId": existing.id,
                    "message": "已恢复该客户此前删除的功能（历史记录保留）",
                }
            if existing is not None:
                add_audit(
                    db,
                    now=now,
                    request=request,
                    action="admin.customer_feature.copy",
                    outcome="ignored",
                    actor_user_id=actor.user_id,
                    session_id=actor.session_id,
                    target_type="customer_feature",
                    target_id=existing.id,
                    details={"sourceCustomerId": source_customer_id, "targetCustomerId": target_customer_id},
                )
                return {
                    "customerId": target_customer_id,
                    "status": "SKIPPED_EXISTS",
                    "customerFeatureId": existing.id,
                    "message": "目标客户已经注册这个功能",
                }

            copied = CustomerFeatureModel(
                id=uuid.uuid4().hex,
                customer_id=target_customer_id,
                feature_definition_id=definition_id,
                feature_version_id=version.id,
                display_name=version.name,
                description=version.description,
                is_enabled=True,
                status="ACTIVE",
                max_runtime_seconds=None,
                current_data_source_revision_id=None,
                created_at=now,
                updated_at=now,
                created_by=actor.user_id,
            )
            db.add(copied)
            db.flush()
            schema = self._config_schema(version)
            self._initialize_config_defaults(db, copied.id, schema, actor.user_id, now)
            default = db.scalar(
                select(FeatureVersionDefaultDataSourceModel)
                .options(undefer(FeatureVersionDefaultDataSourceModel.content))
                .where(FeatureVersionDefaultDataSourceModel.feature_version_id == version.id)
            )
            if default is not None:
                revision = self._create_data_source_revision(
                    db,
                    copied.id,
                    1,
                    "DEFAULT",
                    version.id,
                    default.filename,
                    default.content,
                    actor.user_id,
                    now,
                )
                db.flush()
                copied.current_data_source_revision_id = revision.id
            copied.status = self._derive_status(copied, version, self._data_schema(version))
            add_audit(
                db,
                now=now,
                request=request,
                action="admin.customer_feature.copy",
                outcome="success",
                actor_user_id=actor.user_id,
                session_id=actor.session_id,
                target_type="customer_feature",
                target_id=copied.id,
                details={
                    "sourceCustomerId": source_customer_id,
                    "targetCustomerId": target_customer_id,
                    "versionId": version.id,
                    "initializedDefaultDataSource": default is not None,
                },
            )
            db.flush()
            return {
                "customerId": target_customer_id,
                "status": "COPIED",
                "customerFeatureId": copied.id,
                "message": "复制完成",
            }

    def delete_customer_feature(
        self,
        *,
        actor: AuthContext,
        customer_feature_id: str,
        request: RequestMetadata,
    ) -> dict[str, Any]:
        """软删除功能登记：保留登记行与版本记录（历史运行可查），清空客户侧配置与数据源。"""
        self._require_menu(actor, MenuKey.FEATURE_ADMIN)
        self.auth.require_recent_auth(actor, max_age_seconds=120)  # 高危操作：要求刚刚验证过密码
        now = self.clock.now()
        with self.database.session() as db:
            feature = self._require_customer_feature(db, actor, customer_feature_id)
            active = db.scalar(
                select(func.count(RunModel.request_id)).where(
                    RunModel.customer_feature_id == feature.id,
                    RunModel.status.in_(("QUEUED", "STARTING", "RUNNING", "STOPPING")),
                )
            )
            if active:
                raise ConflictError("FEATURE_RUN_ACTIVE", "该功能有正在处理的任务，请先停止或等待完成", status=409)
            config_count = db.execute(
                delete(FeatureConfigValueModel).where(FeatureConfigValueModel.customer_feature_id == feature.id)
            ).rowcount
            schedule_count = db.execute(
                delete(ScheduledTaskModel).where(ScheduledTaskModel.customer_feature_id == feature.id)
            ).rowcount
            revisions = db.scalars(
                select(CustomerFeatureDataSourceRevisionModel).where(
                    CustomerFeatureDataSourceRevisionModel.customer_feature_id == feature.id
                )
            ).all()
            revision_purged = 0
            revision_blanked = 0
            for revision in revisions:
                referenced = db.scalar(
                    select(RunModel.request_id).where(RunModel.data_source_revision_id == revision.id).limit(1)
                )
                if referenced:
                    revision.content = b""
                    revision_blanked += 1
                else:
                    db.delete(revision)
                    revision_purged += 1
            feature.current_data_source_revision_id = None
            feature.is_deleted = True
            feature.deleted_at = now
            feature.deleted_by = actor.user_id
            feature.is_enabled = False
            feature.updated_at = now
            add_audit(
                db,
                now=now,
                request=request,
                action="admin.customer_feature.delete",
                outcome="success",
                actor_user_id=actor.user_id,
                session_id=actor.session_id,
                target_type="customer_feature",
                target_id=feature.id,
                details={
                    "customerId": feature.customer_id,
                    "definitionId": feature.feature_definition_id,
                    "configCount": config_count,
                    "scheduleCount": schedule_count,
                    "revisionPurged": revision_purged,
                    "revisionBlanked": revision_blanked,
                },
            )
            return {
                "deleted": True,
                "customerFeatureId": feature.id,
                "configCount": config_count,
                "scheduleCount": schedule_count,
                "revisionPurged": revision_purged,
                "revisionBlanked": revision_blanked,
            }

    def _revive_customer_feature(
        self,
        db: Any,
        feature: CustomerFeatureModel,
        *,
        version: FeatureVersionModel,
        config_schema: dict[str, Any],
        data_schema: dict[str, Any] | None,
        default_source: Any,
        actor_user_id: str,
        now: int,
    ) -> None:
        """恢复已删除的功能登记：复用同一行，历史运行记录自然延续。"""
        feature.is_deleted = False
        feature.deleted_at = None
        feature.deleted_by = None
        feature.feature_version_id = version.id
        feature.display_name = version.name
        feature.description = version.description
        feature.is_enabled = True
        feature.max_runtime_seconds = None
        feature.current_data_source_revision_id = None
        feature.updated_at = now
        self._initialize_config_defaults(db, feature.id, config_schema, actor_user_id, now)
        if default_source is not None:
            last_number = db.scalar(
                select(func.max(CustomerFeatureDataSourceRevisionModel.revision_number)).where(
                    CustomerFeatureDataSourceRevisionModel.customer_feature_id == feature.id
                )
            ) or 0
            revision = self._create_data_source_revision(
                db,
                feature.id,
                last_number + 1,
                "DEFAULT",
                version.id,
                default_source.filename,
                default_source.content,
                actor_user_id,
                now,
            )
            feature.current_data_source_revision_id = revision.id
        feature.status = self._derive_status(feature, version, data_schema)

    def set_enabled(
        self,
        *,
        actor: AuthContext,
        customer_feature_id: str,
        enabled: bool | None,
        max_runtime_seconds: int | None | object = _UNSET,
        request: RequestMetadata,
    ) -> dict[str, Any]:
        self._require_menu(actor, MenuKey.FEATURE_ADMIN)
        self.auth.require_recent_auth(actor)
        if enabled is not None and not isinstance(enabled, bool):
            raise ConflictError("INVALID_ENABLED", "启用状态必须是布尔值")
        if max_runtime_seconds is not _UNSET and (
            max_runtime_seconds is not None
            and (
                isinstance(max_runtime_seconds, bool)
                or not isinstance(max_runtime_seconds, int)
                or not 1 <= max_runtime_seconds <= 2_592_000
            )
        ):
            raise ConflictError("INVALID_MAX_RUNTIME", "最长运行时间必须留空或设为 1 到 2592000 秒")
        with self.database.session() as db:
            feature = self._require_customer_feature(db, actor, customer_feature_id)
            version = db.get(FeatureVersionModel, feature.feature_version_id)
            if enabled is not None:
                feature.is_enabled = enabled
            if max_runtime_seconds is not _UNSET:
                feature.max_runtime_seconds = max_runtime_seconds
            feature.updated_at = self.clock.now()
            feature.status = self._derive_status(feature, version, self._data_schema(version))
            add_audit(db, now=self.clock.now(), request=request, action="admin.customer_feature.policy.update", outcome="success", actor_user_id=actor.user_id, session_id=actor.session_id, target_type="customer_feature", target_id=feature.id, details={"enabled": feature.is_enabled, "maxRuntimeSeconds": feature.max_runtime_seconds})
            return self._customer_feature_dict(db, feature)

    def activate_version(self, *, actor: AuthContext, customer_feature_id: str, version_id: str, use_default_data_source: bool, request: RequestMetadata) -> dict[str, Any]:
        self._require_menu(actor, MenuKey.FEATURE_ADMIN)
        self.auth.require_recent_auth(actor)
        now = self.clock.now()
        with self.database.session() as db:
            feature = self._require_customer_feature(db, actor, customer_feature_id)
            version = db.get(FeatureVersionModel, version_id)
            if version is None or version.feature_definition_id != feature.feature_definition_id:
                raise ConflictError("VERSION_DEFINITION_MISMATCH", "所选版本不属于这个功能", status=409)
            if version.status != "READY":
                raise ConflictError("VERSION_NOT_READY", "依赖尚未准备完成，不能启用这个版本", status=409)
            schema = self._data_schema(version)
            current = db.get(CustomerFeatureDataSourceRevisionModel, feature.current_data_source_revision_id) if feature.current_data_source_revision_id else None
            incompatible = bool(current and schema and schema.get("extensions") and PurePath(current.filename).suffix.lower() not in schema["extensions"])
            if incompatible and not use_default_data_source:
                raise ConflictError(
                    "DATA_SOURCE_INCOMPATIBLE",
                    "当前数据源格式与新版本不兼容；请明确选择使用新版本默认文件后再切换",
                    status=409,
                )
            if use_default_data_source:
                default = db.scalar(select(FeatureVersionDefaultDataSourceModel).options(undefer(FeatureVersionDefaultDataSourceModel.content)).where(
                    FeatureVersionDefaultDataSourceModel.feature_version_id == version.id
                ))
                if default is None:
                    raise ConflictError("DEFAULT_DATA_SOURCE_MISSING", "新版本没有可用于重置的默认数据源", status=409)
                next_number = (db.scalar(select(func.max(CustomerFeatureDataSourceRevisionModel.revision_number)).where(
                    CustomerFeatureDataSourceRevisionModel.customer_feature_id == feature.id
                )) or 0) + 1
                revision = self._create_data_source_revision(db, feature.id, next_number, "DEFAULT", version.id, default.filename, default.content, actor.user_id, now)
                feature.current_data_source_revision_id = revision.id
            old_schema = self._config_schema(db.get(FeatureVersionModel, feature.feature_version_id))
            new_schema = self._config_schema(version)
            existing_rows = list(db.scalars(select(FeatureConfigValueModel).where(
                FeatureConfigValueModel.customer_feature_id == feature.id
            )))
            existing_keys: set[str] = set()
            for row in existing_rows:
                spec = new_schema.get(row.config_key)
                compatible = spec is not None and old_schema.get(row.config_key, {}).get("type") == spec.get("type")
                if compatible and spec["type"] != "secret":
                    try:
                        validate_config_value(row.config_key, spec, json.loads(row.value_json) if row.value_json is not None else None)
                    except (ValidationError, ValueError, TypeError):
                        compatible = False
                if compatible:
                    existing_keys.add(row.config_key)
                else:
                    db.delete(row)
            self._initialize_config_defaults(db, feature.id, {key: value for key, value in new_schema.items() if key not in existing_keys}, actor.user_id, now)
            feature.feature_version_id = version.id
            feature.display_name = version.name
            feature.description = version.description
            feature.updated_at = now
            feature.status = self._derive_status(feature, version, schema)
            db.flush()
            add_audit(db, now=now, request=request, action="admin.customer_feature.version.activate", outcome="success", actor_user_id=actor.user_id, session_id=actor.session_id, target_type="customer_feature", target_id=feature.id, details={"versionId": version.id, "resetDataSource": use_default_data_source or incompatible, "removedConfigKeys": sorted(set(old_schema) - set(new_schema))})
            return self._customer_feature_dict(db, feature)

    def get_config(
        self,
        actor: AuthContext,
        customer_feature_id: str,
        request: RequestMetadata | None = None,
    ) -> dict[str, Any]:
        self._require_menu(actor, MenuKey.FEATURE_ADMIN)
        with self.database.session() as db:
            feature = self._require_customer_feature(db, actor, customer_feature_id)
            version = db.get(FeatureVersionModel, feature.feature_version_id)
            schema = self._config_schema(version)
            values = {row.config_key: row for row in db.scalars(select(FeatureConfigValueModel).where(
                FeatureConfigValueModel.customer_feature_id == feature.id
            ))}
            fields = []
            for key, spec in schema.items():
                field = {"key": key, **spec}
                row = values.get(key)
                if spec["type"] == "secret":
                    field["isSet"] = bool(row and row.encrypted_value)
                else:
                    field["value"] = json.loads(row.value_json) if row and row.value_json is not None else spec.get("default")
                fields.append(field)
            if request is not None:
                add_audit(
                    db,
                    now=self.clock.now(),
                    request=request,
                    action="admin.customer_feature.config.view",
                    outcome="success",
                    actor_user_id=actor.user_id,
                    session_id=actor.session_id,
                    target_type="customer_feature",
                    target_id=feature.id,
                    details={"fieldCount": len(fields), "secretFieldCount": sum(1 for item in fields if item["type"] == "secret")},
                )
            return {
                "customerFeatureId": feature.id,
                "fields": fields,
                "complete": self._config_complete(schema, values),
                "maxRuntimeSeconds": feature.max_runtime_seconds,
            }

    def update_config(self, *, actor: AuthContext, customer_feature_id: str, values: dict[str, Any], clear_secrets: list[str], request: RequestMetadata) -> dict[str, Any]:
        self._require_menu(actor, MenuKey.FEATURE_ADMIN)
        self.auth.require_recent_auth(actor)
        now = self.clock.now()
        with self.database.session() as db:
            feature = self._require_customer_feature(db, actor, customer_feature_id)
            version = db.get(FeatureVersionModel, feature.feature_version_id)
            schema = self._config_schema(version)
            unknown = (set(values) | set(clear_secrets)) - set(schema)
            if unknown:
                raise ConflictError("UNKNOWN_CONFIG_KEY", f"包含未知配置项：{', '.join(sorted(unknown))}")
            for key in clear_secrets:
                if schema[key]["type"] != "secret":
                    raise ConflictError("INVALID_SECRET_KEY", f"配置 {key} 不是密钥")
                row = db.get(FeatureConfigValueModel, (feature.id, key))
                if row:
                    db.delete(row)
            for key, value in values.items():
                spec = schema[key]
                if spec["type"] == "secret":
                    if not isinstance(value, str) or not value or len(value) > 10_000:
                        raise ValidationError("INVALID_SECRET_VALUE", f"密钥配置 {key} 必须是 1 到 10000 字符的字符串")
                    row = db.get(FeatureConfigValueModel, (feature.id, key))
                    if row is None:
                        row = FeatureConfigValueModel(customer_feature_id=feature.id, config_key=key)
                        db.add(row)
                    row.value_type = "secret"
                    row.value_json = None
                    row.encrypted_value = self.cipher.encrypt(feature.id, key, value.encode("utf-8"))
                else:
                    validated = validate_config_value(key, spec, value)
                    if spec.get("required") and (validated is None or (spec["type"] in {"string", "text"} and validated == "")):
                        raise ValidationError("CONFIG_REQUIRED", f"配置 {key} 不能为空")
                    row = db.get(FeatureConfigValueModel, (feature.id, key))
                    if row is None:
                        row = FeatureConfigValueModel(customer_feature_id=feature.id, config_key=key)
                        db.add(row)
                    row.value_type = spec["type"]
                    row.value_json = json.dumps(validated, ensure_ascii=False, separators=(",", ":"))
                    row.encrypted_value = None
                row.updated_at = now
                row.updated_by = actor.user_id
            db.flush()
            stored = {row.config_key: row for row in db.scalars(select(FeatureConfigValueModel).where(
                FeatureConfigValueModel.customer_feature_id == feature.id
            ))}
            if not self._config_complete(schema, stored):
                raise ConflictError("CONFIG_REQUIRED", "仍有必填配置未设置")
            add_audit(db, now=now, request=request, action="admin.customer_feature.config.update", outcome="success", actor_user_id=actor.user_id, session_id=actor.session_id, target_type="customer_feature", target_id=feature.id, details={"changedKeys": sorted(values), "clearedKeys": sorted(clear_secrets)})
        return self.get_config(actor, customer_feature_id)

    def data_source_metadata(self, actor: AuthContext, customer_feature_id: str) -> dict[str, Any]:
        with self.database.session() as db:
            feature = self._require_customer_feature(db, actor, customer_feature_id)
            version = db.get(FeatureVersionModel, feature.feature_version_id)
            revision = db.get(CustomerFeatureDataSourceRevisionModel, feature.current_data_source_revision_id) if feature.current_data_source_revision_id else None
            return {"schema": self._data_schema(version), "current": self._revision_dict(revision) if revision else None}

    def replace_data_source(self, *, actor: AuthContext, customer_feature_id: str, filename: str, content: bytes, request: RequestMetadata) -> dict[str, Any]:
        if not content or len(content) > self.settings.data_source_max_bytes():
            raise ConflictError("DATA_SOURCE_SIZE_INVALID", "数据源为空或超过系统大小限制")
        safe_name = self._safe_upload_filename(filename)
        now = self.clock.now()
        with self.database.session() as db:
            feature = self._require_customer_feature(db, actor, customer_feature_id)
            version = db.get(FeatureVersionModel, feature.feature_version_id)
            schema = self._data_schema(version)
            if schema is None:
                raise ConflictError("DATA_SOURCE_NOT_DECLARED", "这个功能没有声明数据源")
            suffix = PurePath(safe_name).suffix.lower()
            if schema.get("extensions") and suffix not in schema["extensions"]:
                raise ConflictError("DATA_SOURCE_EXTENSION_INVALID", f"只允许上传：{', '.join(schema['extensions'])}")
            next_number = (db.scalar(select(func.max(CustomerFeatureDataSourceRevisionModel.revision_number)).where(
                CustomerFeatureDataSourceRevisionModel.customer_feature_id == feature.id
            )) or 0) + 1
            revision = self._create_data_source_revision(db, feature.id, next_number, "UPLOAD", version.id, safe_name, content, actor.user_id, now)
            feature.current_data_source_revision_id = revision.id
            feature.updated_at = now
            feature.status = self._derive_status(feature, version, schema)
            add_audit(db, now=now, request=request, action="customer_feature.data_source.replace", outcome="success", actor_user_id=actor.user_id, session_id=actor.session_id, target_type="customer_feature", target_id=feature.id, details={"revision": next_number, "filename": safe_name, "sha256": revision.sha256.hex()})
            return {"schema": schema, "current": self._revision_dict(revision)}

    def download_data_source(
        self, actor: AuthContext, customer_feature_id: str, request: RequestMetadata | None = None
    ) -> DownloadedFile:
        with self.database.session() as db:
            feature = self._require_customer_feature(db, actor, customer_feature_id)
            if not feature.current_data_source_revision_id:
                raise ConflictError("DATA_SOURCE_MISSING", "当前没有可下载的数据源", status=404)
            revision = db.scalar(select(CustomerFeatureDataSourceRevisionModel).options(undefer(CustomerFeatureDataSourceRevisionModel.content)).where(
                CustomerFeatureDataSourceRevisionModel.id == feature.current_data_source_revision_id
            ))
            if revision is None:
                raise ConflictError("DATA_SOURCE_MISSING", "当前数据源记录不存在", status=404)
            if request is not None:
                add_audit(
                    db,
                    now=self.clock.now(),
                    request=request,
                    action="customer_feature.data_source.download",
                    outcome="success",
                    actor_user_id=actor.user_id,
                    session_id=actor.session_id,
                    target_type="customer_feature",
                    target_id=feature.id,
                    details={"revision": revision.revision_number, "filename": revision.filename, "sha256": revision.sha256.hex()},
                )
            return DownloadedFile(revision.filename, revision.content, revision.sha256.hex())

    def download_default_data_source(
        self, actor: AuthContext, version_id: str, request: RequestMetadata | None = None
    ) -> DownloadedFile:
        self._require_menu(actor, MenuKey.FEATURE_ADMIN)
        with self.database.session() as db:
            row = db.scalar(select(FeatureVersionDefaultDataSourceModel).options(undefer(FeatureVersionDefaultDataSourceModel.content)).where(
                FeatureVersionDefaultDataSourceModel.feature_version_id == version_id
            ))
            if row is None:
                raise ConflictError("DEFAULT_DATA_SOURCE_MISSING", "这个版本没有默认数据源", status=404)
            if request is not None:
                add_audit(
                    db,
                    now=self.clock.now(),
                    request=request,
                    action="admin.feature_version.default_data_source.download",
                    outcome="success",
                    actor_user_id=actor.user_id,
                    session_id=actor.session_id,
                    target_type="feature_version",
                    target_id=version_id,
                    details={"filename": row.filename, "sha256": row.sha256.hex()},
                )
            return DownloadedFile(row.filename, row.content, row.sha256.hex())

    def capture_execution_inputs(self, customer_feature_id: str) -> ExecutionInputs:
        """Capture immutable identifiers before Phase C creates a run record."""
        with self.database.session() as db:
            feature = db.get(CustomerFeatureModel, customer_feature_id)
            if feature is None:
                raise ConflictError("CUSTOMER_FEATURE_NOT_FOUND", "客户功能不存在", status=404)
            version = db.get(FeatureVersionModel, feature.feature_version_id)
            schema = self._config_schema(version)
            rows = {row.config_key: row for row in db.scalars(select(FeatureConfigValueModel).where(
                FeatureConfigValueModel.customer_feature_id == feature.id
            ))}
            if feature.status != "ACTIVE" or not self._config_complete(schema, rows):
                raise ConflictError("FEATURE_NOT_RUNNABLE", "功能尚未满足运行条件", status=409)
            values: dict[str, Any] = {}
            for key, spec in schema.items():
                row = rows.get(key)
                if spec["type"] == "secret":
                    values[key] = self.cipher.decrypt(feature.id, key, row.encrypted_value).decode("utf-8")
                elif row and row.value_json is not None:
                    values[key] = json.loads(row.value_json)
                else:
                    values[key] = spec.get("default")
            return ExecutionInputs(feature.id, version.id, feature.current_data_source_revision_id, values)

    @staticmethod
    def _initialize_config_defaults(db: Any, customer_feature_id: str, schema: dict[str, dict[str, Any]], actor_id: str, now: int) -> None:
        for key, spec in schema.items():
            if spec["type"] != "secret" and "default" in spec:
                db.add(FeatureConfigValueModel(
                    customer_feature_id=customer_feature_id,
                    config_key=key,
                    value_type=spec["type"],
                    value_json=json.dumps(spec["default"], ensure_ascii=False, separators=(",", ":")),
                    encrypted_value=None,
                    updated_at=now,
                    updated_by=actor_id,
                ))

    @staticmethod
    def _create_data_source_revision(db: Any, feature_id: str, number: int, kind: str, version_id: str, filename: str, content: bytes, actor_id: str, now: int) -> CustomerFeatureDataSourceRevisionModel:
        revision = CustomerFeatureDataSourceRevisionModel(
            id=uuid.uuid4().hex,
            customer_feature_id=feature_id,
            revision_number=number,
            source_kind=kind,
            source_feature_version_id=version_id,
            filename=filename,
            size=len(content),
            sha256=hashlib.sha256(content).digest(),
            content=content,
            uploaded_by=actor_id,
            created_at=now,
        )
        db.add(revision)
        return revision

    @staticmethod
    def _config_schema(version: FeatureVersionModel | None) -> dict[str, dict[str, Any]]:
        return json.loads(version.config_schema_json) if version else {}

    @staticmethod
    def _data_schema(version: FeatureVersionModel | None) -> dict[str, Any] | None:
        return json.loads(version.data_source_schema_json) if version and version.data_source_schema_json else None

    @staticmethod
    def _config_complete(schema: dict[str, dict[str, Any]], values: dict[str, FeatureConfigValueModel]) -> bool:
        for key, spec in schema.items():
            if not spec.get("required"):
                continue
            row = values.get(key)
            if spec["type"] == "secret":
                if not row or not row.encrypted_value:
                    return False
            elif not row and "default" not in spec:
                return False
            elif row:
                if row.value_json == "null":
                    return False
                if spec["type"] in {"string", "text"} and json.loads(row.value_json) == "":
                    return False
        return True

    @staticmethod
    def _derive_status(feature: CustomerFeatureModel, version: FeatureVersionModel | None, data_schema: dict[str, Any] | None) -> str:
        if not feature.is_enabled:
            return "DISABLED"
        if version is None or version.status == "PREPARING":
            return "PREPARING"
        if version.status == "DEPENDENCY_FAILED":
            return "DEPENDENCY_FAILED"
        if data_schema and data_schema.get("required") and not feature.current_data_source_revision_id:
            return "WAITING_DATA_SOURCE"
        return "ACTIVE"

    def _require_customer_access(self, db: Any, actor: AuthContext, customer_id: str) -> CustomerModel:
        customer = db.get(CustomerModel, customer_id)
        if customer is None or not customer.is_active:
            raise ConflictError("CUSTOMER_NOT_AVAILABLE", "客户不存在或已停用", status=404)
        if actor.role is not UserRole.ADMIN:
            link = db.get(UserCustomerModel, (actor.user_id, customer_id))
            if link is None:
                raise AuthorizationError("CUSTOMER_ACCESS_DENIED", "无权访问这个客户", status=403)
        return customer

    def _require_customer_feature(self, db: Any, actor: AuthContext, feature_id: str) -> CustomerFeatureModel:
        feature = db.get(CustomerFeatureModel, feature_id)
        if feature is None:
            raise ConflictError("CUSTOMER_FEATURE_NOT_FOUND", "客户功能不存在", status=404)
        if feature.is_deleted:
            raise ConflictError("FEATURE_DELETED", "功能已删除，重新上传后可恢复", status=409)
        self._require_customer_access(db, actor, feature.customer_id)
        return feature

    @staticmethod
    def _require_menu(actor: AuthContext, *menu_keys: str) -> None:
        if not actor.has_menu(*menu_keys):
            raise AuthorizationError("MENU_PERMISSION_REQUIRED", "当前账号没有访问该菜单的权限", status=403)

    def _customer_feature_dict(
        self, db: Any, feature: CustomerFeatureModel, *, customer_name: str | None = None
    ) -> dict[str, Any]:
        version = db.get(FeatureVersionModel, feature.feature_version_id)
        if customer_name is None:
            customer = db.get(CustomerModel, feature.customer_id)
            customer_name = customer.name if customer else ""
        revision = db.get(CustomerFeatureDataSourceRevisionModel, feature.current_data_source_revision_id) if feature.current_data_source_revision_id else None
        config_values = {row.config_key: row for row in db.scalars(select(FeatureConfigValueModel).where(
            FeatureConfigValueModel.customer_feature_id == feature.id
        ))}
        return {
            "id": feature.id,
            "customerId": feature.customer_id,
            "customerName": customer_name,
            "definitionId": feature.feature_definition_id,
            "versionId": feature.feature_version_id,
            "versionNumber": version.version_number if version else None,
            "name": feature.display_name,
            "description": feature.description,
            "isEnabled": feature.is_enabled,
            "status": feature.status,
            "maxRuntimeSeconds": feature.max_runtime_seconds,
            "configurationComplete": self._config_complete(self._config_schema(version), config_values),
            "dataSourceSchema": self._data_schema(version),
            "dataSource": self._revision_dict(revision) if revision else None,
            "updatedAt": feature.updated_at,
        }

    def _version_dict(self, db: Any, version: FeatureVersionModel) -> dict[str, Any]:
        default = db.get(FeatureVersionDefaultDataSourceModel, version.id)
        environment = db.get(RuntimeEnvironmentModel, version.runtime_environment_id) if version.runtime_environment_id else None
        return {
            "id": version.id,
            "definitionId": version.feature_definition_id,
            "versionNumber": version.version_number,
            "name": version.name,
            "description": version.description,
            "entrypoint": version.entrypoint,
            "status": version.status,
            "prepareError": version.prepare_error,
            "packageFilename": version.package_filename,
            "packageSize": version.package_size,
            "packageSha256": version.package_sha256.hex(),
            "sourceEncoding": version.source_encoding,
            "requirements": version.requirements_text.splitlines(),
            "warnings": json.loads(version.metadata_warnings_json),
            "configSchema": json.loads(version.config_schema_json),
            "dataSourceSchema": self._data_schema(version),
            "reportSchema": json.loads(version.metadata_json).get("report"),
            "defaultDataSource": {"filename": default.filename, "size": default.size, "sha256": default.sha256.hex()} if default else None,
            "environment": {"id": environment.id, "status": environment.status, "requestFingerprint": environment.request_fingerprint, "resolvedFingerprint": environment.resolved_fingerprint, "failure": environment.failure_summary} if environment else None,
            "createdAt": version.created_at,
        }

    @staticmethod
    def _revision_dict(revision: CustomerFeatureDataSourceRevisionModel | None) -> dict[str, Any] | None:
        if revision is None:
            return None
        return {"id": revision.id, "revisionNumber": revision.revision_number, "sourceKind": revision.source_kind, "sourceVersionId": revision.source_feature_version_id, "filename": revision.filename, "size": revision.size, "sha256": revision.sha256.hex(), "createdAt": revision.created_at}

    @staticmethod
    def _safe_upload_filename(filename: str) -> str:
        name = unicodedata.normalize("NFKC", PurePath(filename.replace("\\", "/")).name).strip()
        if (
            not name
            or name in {".", ".."}
            or ":" in name
            or len(name) > 255
            or any(unicodedata.category(char).startswith("C") for char in name)
        ):
            raise ConflictError("INVALID_DATA_SOURCE_FILENAME", "数据源文件名无效")
        return name
