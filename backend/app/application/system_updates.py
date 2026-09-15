from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import PurePosixPath
from typing import Any, BinaryIO, Callable

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.application.audit import RequestMetadata, add_audit
from app.application.auth import AuthContext, AuthService
from app.application.errors import ConflictError
from app.application.settings import SettingsService
from app.domain.time import Clock
from app.infrastructure.database import Database
from app.infrastructure.models import RunModel, SystemUpdateModel, UserModel
from app.infrastructure.paths import AppPaths
from app.update_package import UpdatePackageError, inspect_update_package, runtime_platform


ACTIVE_RUN_STATUSES = ("QUEUED", "STARTING", "RUNNING", "STOPPING")
ACTIVE_UPDATE_STATUSES = ("PENDING", "APPLYING")


class SystemUpdateService:
    def __init__(
        self,
        database: Database,
        settings: SettingsService,
        auth: AuthService,
        paths: AppPaths,
        clock: Clock,
        version_provider: Callable[[], str],
    ) -> None:
        self.database = database
        self.settings = settings
        self.auth = auth
        self.paths = paths
        self.clock = clock
        self.version_provider = version_provider

    def overview(self, *, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        current_version = self.version_provider()
        supervisor = self._supervisor_state()
        with self.database.session() as db:
            total = int(db.scalar(select(func.count(SystemUpdateModel.id))) or 0)
            rows = list(db.scalars(
                select(SystemUpdateModel).order_by(SystemUpdateModel.created_at.desc())
                .offset((page - 1) * page_size).limit(page_size)
            ))
            active_runs = db.scalar(
                select(func.count(RunModel.request_id)).where(RunModel.status.in_(ACTIVE_RUN_STATUSES))
            ) or 0
            rollback_source = db.scalar(
                select(SystemUpdateModel).where(
                    SystemUpdateModel.operation == "APPLY",
                    SystemUpdateModel.status == "SUCCEEDED",
                    SystemUpdateModel.target_version == current_version,
                    SystemUpdateModel.rollback_compatible.is_(True),
                    SystemUpdateModel.previous_release_json.is_not(None),
                ).order_by(SystemUpdateModel.completed_at.desc()).limit(1)
            )
            update_in_progress = bool(db.scalar(
                select(SystemUpdateModel.id).where(SystemUpdateModel.status.in_(ACTIVE_UPDATE_STATUSES)).limit(1)
            ))
        return {
            "currentVersion": current_version,
            "runtimePlatform": runtime_platform(),
            "supervisor": supervisor,
            "activeRuns": active_runs,
            "updateInProgress": update_in_progress,
            "canRollback": (
                rollback_source is not None
                and active_runs == 0
                and not update_in_progress
                and supervisor["available"]
            ),
            "rollbackTargetVersion": rollback_source.source_version if rollback_source else None,
            "items": [self._serialize(row, current_version=current_version) for row in rows],
            "pagination": {
                "page": page, "pageSize": page_size, "total": total,
                "totalPages": max(1, (total + page_size - 1) // page_size),
            },
        }

    def upload(
        self,
        *,
        actor: AuthContext,
        filename: str,
        stream: BinaryIO,
        request: RequestMetadata,
    ) -> dict[str, Any]:
        safe_filename = PurePosixPath(filename.replace("\\", "/")).name
        if not safe_filename.casefold().endswith(".fcup") or len(safe_filename) > 255:
            self._audit_upload_denied(
                actor=actor,
                request=request,
                filename=safe_filename[:255],
                package_size=None,
                error_code="UPDATE_FILE_TYPE_INVALID",
            )
            raise ConflictError("UPDATE_FILE_TYPE_INVALID", "请选择 .fcup 更新包", status=400)
        update_id = uuid.uuid4().hex
        maximum = self.settings.update_package_max_bytes()
        temp = self.paths.update_inbox / f".{update_id}.upload"
        destination = self.paths.update_inbox / f"{update_id}.fcup"
        digest = hashlib.sha256()
        total = 0
        try:
            with temp.open("xb") as output:
                while chunk := stream.read(1024 * 1024):
                    total += len(chunk)
                    if total > maximum:
                        raise ConflictError("UPDATE_PACKAGE_SIZE_INVALID", "更新包超过系统大小限制", status=413)
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            if total == 0:
                raise ConflictError("UPDATE_PACKAGE_SIZE_INVALID", "更新包不能为空", status=400)
            inspected = inspect_update_package(
                temp,
                current_version=self.version_provider(),
                maximum_bytes=maximum,
            )
            if inspected.package_sha256 != digest.digest():
                raise ConflictError("UPDATE_PACKAGE_CHANGED", "更新包写入过程中发生变化", status=400)
            os.replace(temp, destination)
            self._fsync_directory(destination.parent)
            try:
                destination.chmod(0o640)
            except OSError:
                pass
        except UpdatePackageError as exc:
            temp.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            self._audit_upload_denied(
                actor=actor,
                request=request,
                filename=safe_filename,
                package_size=total,
                error_code=exc.code,
            )
            raise ConflictError(exc.code, str(exc), status=400) from exc
        except ConflictError as exc:
            temp.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            self._audit_upload_denied(
                actor=actor,
                request=request,
                filename=safe_filename,
                package_size=total,
                error_code=exc.code,
            )
            raise
        except BaseException:
            temp.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            raise

        now = self.clock.now()
        try:
            with self.database.session() as db:
                # Serialize the short registration transaction so two concurrent
                # uploads cannot both register the same immutable signed package.
                db.execute(text("BEGIN IMMEDIATE"))
                duplicate_id = db.scalar(
                    select(SystemUpdateModel.id)
                    .where(SystemUpdateModel.package_sha256 == inspected.package_sha256)
                    .limit(1)
                )
                if duplicate_id is not None:
                    raise ConflictError(
                        "UPDATE_PACKAGE_DUPLICATE",
                        "该更新包已上传；如需重试，请在原失败记录上创建新的尝试",
                        status=409,
                    )
                user = db.get(UserModel, actor.user_id)
                row = SystemUpdateModel(
                    id=update_id,
                    operation="APPLY",
                    source_version=self.version_provider(),
                    target_version=inspected.manifest.version,
                    package_filename=safe_filename,
                    package_sha256=inspected.package_sha256,
                    package_size=inspected.package_size,
                    manifest_json=json.dumps(inspected.manifest.raw, ensure_ascii=False, separators=(",", ":")),
                    release_notes_json=json.dumps(inspected.manifest.release_notes, ensure_ascii=False),
                    status="READY",
                    stage="VERIFIED",
                    progress=10,
                    active_guard=None,
                    rollback_compatible=inspected.manifest.rollback_compatible,
                    backup_filename=None,
                    release_descriptor_json=None,
                    previous_release_json=None,
                    error_message=None,
                    created_by=actor.user_id,
                    actor_display_name=user.display_name if user else None,
                    client_ip=request.client_ip[:64],
                    request_id=request.request_id[:32] or None,
                    created_at=now,
                    updated_at=now,
                    completed_at=None,
                )
                db.add(row)
                add_audit(
                    db,
                    now=now,
                    request=request,
                    action="admin.system_update.upload",
                    outcome="success",
                    actor_user_id=actor.user_id,
                    session_id=actor.session_id,
                    target_type="system_update",
                    target_id=update_id,
                    target_name=f"{row.source_version} → {row.target_version}",
                    details={
                        "filename": safe_filename,
                        "size": total,
                        "sha256": digest.hexdigest(),
                        "targetVersion": row.target_version,
                        "signatureVerified": True,
                    },
                )
                result = self._serialize(row)
        except ConflictError as exc:
            destination.unlink(missing_ok=True)
            self._fsync_directory(destination.parent)
            self._audit_upload_denied(
                actor=actor,
                request=request,
                filename=safe_filename,
                package_size=total,
                error_code=exc.code,
            )
            raise
        except IntegrityError:
            destination.unlink(missing_ok=True)
            self._fsync_directory(destination.parent)
            raise
        return result

    def request_apply(
        self,
        *,
        actor: AuthContext,
        update_id: str,
        request: RequestMetadata,
    ) -> dict[str, Any]:
        self.auth.require_recent_auth(actor)
        self._require_supervisor()
        now = self.clock.now()
        with self.database.session() as db:
            row = db.get(SystemUpdateModel, update_id)
            if row is None or row.operation != "APPLY":
                raise ConflictError("UPDATE_NOT_FOUND", "更新记录不存在", status=404)
            if row.status != "READY":
                raise ConflictError("UPDATE_NOT_READY", "更新包当前不能执行", status=409)
            if row.source_version != self.version_provider():
                raise ConflictError("UPDATE_SOURCE_CHANGED", "系统版本已经变化，请重新上传匹配的更新包", status=409)
            self._require_idle(db)
            self._require_no_active_update(db)
            package_path = self.paths.update_inbox / f"{row.id}.fcup"
            try:
                inspected = inspect_update_package(
                    package_path,
                    current_version=row.source_version,
                    maximum_bytes=self.settings.update_package_max_bytes(),
                )
            except UpdatePackageError as exc:
                raise ConflictError(exc.code, str(exc), status=400) from exc
            if inspected.package_sha256 != row.package_sha256:
                raise ConflictError("UPDATE_PACKAGE_CHANGED", "更新包与上传记录不一致", status=409)
            row.status = "PENDING"
            row.stage = "QUEUED"
            row.progress = 15
            row.active_guard = 1
            row.updated_at = now
            add_audit(
                db,
                now=now,
                request=request,
                action="admin.system_update.apply_requested",
                outcome="success",
                actor_user_id=actor.user_id,
                session_id=actor.session_id,
                target_type="system_update",
                target_id=row.id,
                target_name=f"{row.source_version} → {row.target_version}",
                details={"packageSha256": row.package_sha256.hex(), "targetVersion": row.target_version},
            )
            try:
                db.flush()
            except IntegrityError as exc:
                raise ConflictError("UPDATE_ALREADY_ACTIVE", "已有系统更新或回退正在进行", status=409) from exc
            result = self._serialize(row)
        try:
            self._write_pending(
                {
                    "protocol": 1,
                    "operation": "APPLY",
                    "updateId": update_id,
                    "packageFile": f"{update_id}.fcup",
                    "packageSha256": inspected.package_sha256.hex(),
                    "sourceVersion": row.source_version,
                    "targetVersion": row.target_version,
                    "requestedAt": now,
                    "notBefore": now + 2,
                }
            )
        except OSError as exc:
            self._reset_pending_status(update_id, "无法向启动器提交更新请求")
            raise ConflictError("UPDATE_CONTROL_WRITE_FAILED", "无法向启动器提交更新请求", status=500) from exc
        return result

    def retry_failed(
        self, *, actor: AuthContext, update_id: str, request: RequestMetadata
    ) -> dict[str, Any]:
        """Create a fresh immutable attempt while preserving the failed record."""
        self.auth.require_recent_auth(actor)
        now = self.clock.now()
        new_id = uuid.uuid4().hex
        with self.database.session() as db:
            source = db.get(SystemUpdateModel, update_id)
            if source is None or source.operation != "APPLY" or source.status not in {"FAILED", "ROLLED_BACK"}:
                raise ConflictError("UPDATE_RETRY_UNAVAILABLE", "这条更新记录不能重新尝试", status=409)
            if source.source_version != self.version_provider() or source.package_sha256 is None:
                raise ConflictError("UPDATE_SOURCE_CHANGED", "当前版本与更新包来源版本不一致", status=409)
            source_path = self.paths.update_inbox / f"{source.id}.fcup"
            destination = self.paths.update_inbox / f"{new_id}.fcup"
            if not source_path.is_file():
                raise ConflictError("UPDATE_PACKAGE_MISSING", "原更新包文件已经不存在", status=409)
            try:
                inspected = inspect_update_package(
                    source_path,
                    current_version=source.source_version,
                    maximum_bytes=self.settings.update_package_max_bytes(),
                )
            except UpdatePackageError as exc:
                raise ConflictError(exc.code, str(exc), status=400) from exc
            if inspected.package_sha256 != source.package_sha256:
                raise ConflictError("UPDATE_PACKAGE_CHANGED", "原更新包与记录摘要不一致", status=409)
            shutil.copy2(source_path, destination)
            with destination.open("rb+") as copied_file:
                copied_file.flush()
                os.fsync(copied_file.fileno())
            self._fsync_directory(destination.parent)
            user = db.get(UserModel, actor.user_id)
            row = SystemUpdateModel(
                id=new_id,
                operation="APPLY",
                source_version=source.source_version,
                target_version=source.target_version,
                package_filename=source.package_filename,
                package_sha256=source.package_sha256,
                package_size=source.package_size,
                manifest_json=source.manifest_json,
                release_notes_json=source.release_notes_json,
                status="READY",
                stage="VERIFIED",
                progress=10,
                active_guard=None,
                rollback_compatible=source.rollback_compatible,
                backup_filename=None,
                release_descriptor_json=None,
                previous_release_json=None,
                error_message=None,
                created_by=actor.user_id,
                actor_display_name=user.display_name if user else None,
                client_ip=request.client_ip[:64],
                request_id=request.request_id[:32] or None,
                created_at=now,
                updated_at=now,
                completed_at=None,
            )
            db.add(row)
            add_audit(
                db,
                now=now,
                request=request,
                action="admin.system_update.retry_created",
                outcome="success",
                actor_user_id=actor.user_id,
                session_id=actor.session_id,
                target_type="system_update",
                target_id=row.id,
                target_name=f"{row.source_version} → {row.target_version}",
                details={"previousAttemptId": source.id, "packageSha256": source.package_sha256.hex()},
            )
            try:
                db.flush()
            except BaseException:
                destination.unlink(missing_ok=True)
                self._fsync_directory(destination.parent)
                raise
            return self._serialize(row, current_version=self.version_provider())

    def request_rollback(self, *, actor: AuthContext, request: RequestMetadata) -> dict[str, Any]:
        self.auth.require_recent_auth(actor)
        self._require_supervisor()
        current_version = self.version_provider()
        now = self.clock.now()
        rollback_id = uuid.uuid4().hex
        with self.database.session() as db:
            self._require_idle(db)
            self._require_no_active_update(db)
            source = db.scalar(
                select(SystemUpdateModel)
                .where(
                    SystemUpdateModel.operation == "APPLY",
                    SystemUpdateModel.status == "SUCCEEDED",
                    SystemUpdateModel.target_version == current_version,
                    SystemUpdateModel.rollback_compatible.is_(True),
                    SystemUpdateModel.previous_release_json.is_not(None),
                )
                .order_by(SystemUpdateModel.completed_at.desc())
            )
            if source is None:
                raise ConflictError("ROLLBACK_UNAVAILABLE", "当前版本没有可保留数据回退的上一版本", status=409)
            user = db.get(UserModel, actor.user_id)
            row = SystemUpdateModel(
                id=rollback_id,
                operation="ROLLBACK",
                source_version=current_version,
                target_version=source.source_version,
                package_filename=None,
                package_sha256=None,
                package_size=None,
                manifest_json=json.dumps(
                    {"sourceUpdateId": source.id, "targetRelease": json.loads(source.previous_release_json)},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                release_notes_json="[]",
                status="PENDING",
                stage="QUEUED",
                progress=15,
                active_guard=1,
                rollback_compatible=False,
                backup_filename=None,
                release_descriptor_json=None,
                previous_release_json=None,
                error_message=None,
                created_by=actor.user_id,
                actor_display_name=user.display_name if user else None,
                client_ip=request.client_ip[:64],
                request_id=request.request_id[:32] or None,
                created_at=now,
                updated_at=now,
                completed_at=None,
            )
            db.add(row)
            add_audit(
                db,
                now=now,
                request=request,
                action="admin.system_update.rollback_requested",
                outcome="success",
                actor_user_id=actor.user_id,
                session_id=actor.session_id,
                target_type="system_update",
                target_id=rollback_id,
                target_name=f"{current_version} → {source.source_version}",
                details={"sourceUpdateId": source.id, "preserveCurrentDatabase": True},
            )
            try:
                db.flush()
            except IntegrityError as exc:
                raise ConflictError("UPDATE_ALREADY_ACTIVE", "已有系统更新或回退正在进行", status=409) from exc
            result = self._serialize(row)
        try:
            self._write_pending(
                {
                    "protocol": 1,
                    "operation": "ROLLBACK",
                    "updateId": rollback_id,
                    "sourceVersion": current_version,
                    "targetVersion": source.source_version,
                    "requestedAt": now,
                    "notBefore": now + 2,
                }
            )
        except OSError as exc:
            self._reset_pending_status(rollback_id, "无法向启动器提交回退请求")
            raise ConflictError("UPDATE_CONTROL_WRITE_FAILED", "无法向启动器提交回退请求", status=500) from exc
        return result

    def _require_idle(self, db: Any) -> None:
        active = db.scalar(select(func.count(RunModel.request_id)).where(RunModel.status.in_(ACTIVE_RUN_STATUSES))) or 0
        if active:
            raise ConflictError("UPDATE_ACTIVE_RUNS", "仍有运行、停止或排队中的任务，暂时不能更新", status=409)

    @staticmethod
    def _require_no_active_update(db: Any) -> None:
        active = db.scalar(
            select(SystemUpdateModel.id).where(SystemUpdateModel.status.in_(ACTIVE_UPDATE_STATUSES)).limit(1)
        )
        if active:
            raise ConflictError("UPDATE_ALREADY_ACTIVE", "已有系统更新或回退正在进行", status=409)

    def _require_supervisor(self) -> None:
        state = self._supervisor_state()
        if not state["available"]:
            raise ConflictError(
                "UPDATE_SUPERVISOR_UNAVAILABLE",
                "系统更新只能在 Linux 单容器启动器托管模式下执行",
                status=409,
            )

    def _supervisor_state(self) -> dict[str, Any]:
        try:
            value = json.loads(self.paths.launcher_state.read_text(encoding="utf-8"))
            heartbeat = int(value.get("heartbeatAt", 0))
            protocol = int(value.get("protocol", 0))
            available = protocol == 1 and heartbeat >= self.clock.now() - 10
            return {
                "available": available,
                "heartbeatAt": heartbeat or None,
                "protocol": protocol or None,
                "processId": value.get("processId"),
                "managedVersion": value.get("version"),
            }
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {"available": False, "heartbeatAt": None, "protocol": None, "processId": None, "managedVersion": None}

    def _write_pending(self, value: dict[str, Any]) -> None:
        if self.paths.update_pending.exists():
            raise OSError("pending update already exists")
        temp = self.paths.update_pending.with_suffix(f".{uuid.uuid4().hex}.tmp")
        with temp.open("x", encoding="utf-8", newline="\n") as output:
            json.dump(value, output, ensure_ascii=False, separators=(",", ":"))
            output.flush()
            os.fsync(output.fileno())
        try:
            temp.chmod(0o640)
        except OSError:
            pass
        os.replace(temp, self.paths.update_pending)
        self._fsync_directory(self.paths.update_pending.parent)

    @staticmethod
    def _fsync_directory(directory: Any) -> None:
        if os.name == "nt":
            return
        descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _reset_pending_status(self, update_id: str, message: str) -> None:
        with self.database.session() as db:
            row = db.get(SystemUpdateModel, update_id)
            if row is None:
                return
            row.active_guard = None
            row.error_message = message
            row.updated_at = self.clock.now()
            if row.operation == "APPLY":
                row.status = "READY"
                row.stage = "VERIFIED"
                row.progress = 10
                row.completed_at = None
            else:
                row.status = "FAILED"
                row.stage = "CONTROL_ERROR"
                row.progress = 100
                row.completed_at = self.clock.now()

    def _audit_upload_denied(
        self,
        *,
        actor: AuthContext,
        request: RequestMetadata,
        filename: str,
        package_size: int | None,
        error_code: str,
    ) -> None:
        with self.database.session() as db:
            add_audit(
                db,
                now=self.clock.now(),
                request=request,
                action="admin.system_update.upload",
                outcome="denied",
                actor_user_id=actor.user_id,
                session_id=actor.session_id,
                target_type="system_update_package",
                target_name=filename or None,
                details={"errorCode": error_code, "packageSize": package_size},
            )

    @staticmethod
    def _serialize(row: SystemUpdateModel, *, current_version: str | None = None) -> dict[str, Any]:
        return {
            "id": row.id,
            "operation": row.operation,
            "sourceVersion": row.source_version,
            "targetVersion": row.target_version,
            "packageFilename": row.package_filename,
            "packageSha256": row.package_sha256.hex() if row.package_sha256 else None,
            "packageSize": row.package_size,
            "releaseNotes": json.loads(row.release_notes_json),
            "status": row.status,
            "stage": row.stage,
            "progress": row.progress,
            "rollbackCompatible": row.rollback_compatible,
            "backupFilename": row.backup_filename,
            "errorMessage": row.error_message,
            "actorDisplayName": row.actor_display_name,
            "clientIp": row.client_ip,
            "createdAt": row.created_at,
            "updatedAt": row.updated_at,
            "completedAt": row.completed_at,
            "canApply": (
                row.operation == "APPLY"
                and row.status == "READY"
                and (current_version is None or row.source_version == current_version)
            ),
            "canRetry": (
                row.operation == "APPLY"
                and row.status in {"FAILED", "ROLLED_BACK"}
                and (current_version is None or row.source_version == current_version)
                and row.package_sha256 is not None
            ),
        }
