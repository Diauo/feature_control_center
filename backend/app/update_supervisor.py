from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from app.application.audit import RequestMetadata, add_audit
from app.infrastructure.database import Database
from app.infrastructure.models import RunModel, SystemUpdateModel
from app.infrastructure.paths import AppPaths
from app.update_package import UpdatePackageError, extract_update_wheels, inspect_update_package


ACTIVE_RUN_STATUSES = ("QUEUED", "STARTING", "RUNNING", "STOPPING")


@dataclass(frozen=True, slots=True)
class ReleaseDescriptor:
    kind: str
    version: str
    python_executable: Path
    release_dir_name: str | None = None
    skip_migrations: bool = False
    database_revision: str | None = None

    def as_json(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "kind": self.kind,
            "version": self.version,
            "skipMigrations": self.skip_migrations,
        }
        if self.release_dir_name:
            value["releaseDir"] = self.release_dir_name
        if self.database_revision:
            value["databaseRevision"] = self.database_revision
        return value


def bundled_release(version: str) -> ReleaseDescriptor:
    return ReleaseDescriptor("bundled", version, Path(sys.executable).resolve())


def load_current_release(paths: AppPaths, bundled_version: str) -> ReleaseDescriptor:
    if not paths.current_release.is_file():
        return bundled_release(bundled_version)
    try:
        value = json.loads(paths.current_release.read_text(encoding="utf-8"))
        return descriptor_from_json(paths, value, bundled_version=bundled_version)
    except (OSError, ValueError, TypeError, json.JSONDecodeError, KeyError) as exc:
        raise RuntimeError("当前版本指针损坏，启动器拒绝猜测运行版本") from exc


def descriptor_from_json(
    paths: AppPaths, value: dict[str, Any], *, bundled_version: str
) -> ReleaseDescriptor:
    kind = value.get("kind")
    version = str(value.get("version", ""))
    skip_value = value.get("skipMigrations", False)
    if not isinstance(skip_value, bool):
        raise ValueError("invalid migration mode")
    skip_migrations = skip_value
    database_revision_value = value.get("databaseRevision")
    database_revision = str(database_revision_value) if database_revision_value is not None else None
    if not version or len(version) > 32:
        raise ValueError("invalid release version")
    if database_revision is not None and (
        not database_revision
        or len(database_revision) > 80
        or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for character in database_revision)
    ):
        raise ValueError("invalid database revision")
    if kind == "bundled":
        if version != bundled_version:
            raise ValueError("bundled version mismatch")
        return replace(
            bundled_release(bundled_version),
            skip_migrations=skip_migrations,
            database_revision=database_revision,
        )
    if kind != "installed":
        raise ValueError("invalid release kind")
    directory_name = str(value.get("releaseDir", ""))
    if not directory_name or Path(directory_name).name != directory_name or len(directory_name) > 100:
        raise ValueError("invalid release directory")
    release_dir = (paths.releases_dir / directory_name).resolve()
    if release_dir.parent != paths.releases_dir.resolve():
        raise ValueError("release directory escape")
    python_executable = release_dir / "venv" / "bin" / "python"
    if not python_executable.is_file():
        raise ValueError("release python missing")
    return ReleaseDescriptor("installed", version, python_executable, directory_name, skip_migrations, database_revision)


def write_current_release(paths: AppPaths, descriptor: ReleaseDescriptor) -> None:
    _atomic_json(paths.current_release, descriptor.as_json(), mode=0o640)


def write_launcher_state(paths: AppPaths, descriptor: ReleaseDescriptor) -> None:
    _atomic_json(
        paths.launcher_state,
        {
            "protocol": 1,
            "processId": os.getpid(),
            "version": descriptor.version,
            "heartbeatAt": int(time.time()),
        },
        mode=0o640,
    )


def load_pending(paths: AppPaths) -> dict[str, Any] | None:
    try:
        value = json.loads(paths.update_pending.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("更新控制文件损坏") from exc
    if not isinstance(value, dict) or value.get("protocol") != 1:
        raise RuntimeError("更新控制协议不受支持")
    not_before = int(value.get("notBefore", value.get("requestedAt", 0)))
    if not_before > int(time.time()):
        return None
    return value


def clear_pending(paths: AppPaths) -> None:
    _durable_unlink(paths.update_pending)


def validate_pending_record(paths: AppPaths, pending: dict[str, Any], current_version: str) -> None:
    update_id = _update_id(pending)
    operation = str(pending.get("operation", ""))
    database = Database(paths.database)
    try:
        database.configure_database()
        with database.session() as db:
            row = db.get(SystemUpdateModel, update_id)
            if row is None or row.status != "PENDING" or row.active_guard != 1:
                raise RuntimeError("更新控制文件没有对应的待执行数据库记录")
            if row.operation != operation or row.source_version != current_version:
                raise RuntimeError("更新控制文件与当前版本或操作类型不一致")
            if pending.get("sourceVersion") != row.source_version or pending.get("targetVersion") != row.target_version:
                raise RuntimeError("更新控制文件的版本信息与数据库不一致")
            if operation == "APPLY":
                expected_hash = row.package_sha256.hex() if row.package_sha256 else None
                if pending.get("packageSha256") != expected_hash:
                    raise RuntimeError("更新控制文件的包摘要与数据库不一致")
            elif operation != "ROLLBACK":
                raise RuntimeError("更新控制文件的操作类型无效")
    finally:
        database.dispose()


def recover_rejected_control(paths: AppPaths, pending: dict[str, Any], error: Exception) -> bool:
    """Release a valid pending row when its handoff file fails consistency checks."""
    try:
        update_id = _update_id(pending)
    except (RuntimeError, TypeError, ValueError):
        return False
    database = Database(paths.database)
    try:
        database.configure_database()
        now = int(time.time())
        with database.session() as db:
            row = db.get(SystemUpdateModel, update_id)
            if row is None or row.status != "PENDING" or row.active_guard != 1:
                return False
            row.active_guard = None
            row.updated_at = now
            row.error_message = f"启动器拒绝更新控制文件：{str(error)[:300]}"
            if row.operation == "APPLY":
                row.status = "READY"
                row.stage = "VERIFIED"
                row.progress = 10
                row.completed_at = None
            else:
                row.status = "FAILED"
                row.stage = "CONTROL_INVALID"
                row.progress = 100
                row.completed_at = now
            add_audit(
                db,
                now=now,
                request=RequestMetadata(
                    client_ip=row.client_ip,
                    user_agent="fcc-launcher",
                    method="SYSTEM",
                    path="system-update-supervisor",
                    request_id=row.request_id or "",
                ),
                action="system.system_update.control_rejected",
                outcome="failure",
                actor_user_id=row.created_by,
                target_type="system_update",
                target_id=row.id,
                target_name=f"{row.source_version} → {row.target_version}",
                details={
                    "operation": row.operation,
                    "returnedToReady": row.operation == "APPLY",
                    "reason": str(error)[:300],
                },
            )
            return True
    finally:
        database.dispose()


def reconcile_orphaned_handoff(paths: AppPaths, *, grace_seconds: int = 15) -> bool:
    """Release an update row when Web committed but died before writing control state."""
    database = Database(paths.database)
    try:
        database.configure_database()
        now = int(time.time())
        with database.session() as db:
            row = db.scalar(
                select(SystemUpdateModel)
                .where(
                    SystemUpdateModel.status == "PENDING",
                    SystemUpdateModel.updated_at <= now - grace_seconds,
                )
                .order_by(SystemUpdateModel.updated_at)
                .limit(1)
            )
            if row is None:
                return False
            row.active_guard = None
            row.updated_at = now
            row.error_message = "Web 在提交更新控制文件前中断，启动器已解除挂起状态"
            if row.operation == "APPLY":
                row.status = "READY"
                row.stage = "VERIFIED"
                row.progress = 10
                row.completed_at = None
            else:
                row.status = "FAILED"
                row.stage = "CONTROL_HANDOFF_LOST"
                row.progress = 100
                row.completed_at = now
            add_audit(
                db,
                now=now,
                request=RequestMetadata(
                    client_ip=row.client_ip,
                    user_agent="fcc-launcher",
                    method="SYSTEM",
                    path="system-update-supervisor",
                    request_id=row.request_id or "",
                ),
                action="system.system_update.handoff_recovered",
                outcome="failure",
                actor_user_id=row.created_by,
                target_type="system_update",
                target_id=row.id,
                target_name=f"{row.source_version} → {row.target_version}",
                details={"operation": row.operation, "returnedToReady": row.operation == "APPLY"},
            )
            return True
    finally:
        database.dispose()


def write_recovery(
    paths: AppPaths,
    *,
    update_id: str,
    previous: ReleaseDescriptor,
    backup: Path,
) -> None:
    _atomic_json(
        paths.update_recovery,
        {
            "protocol": 1,
            "updateId": update_id,
            "previousRelease": previous.as_json(),
            "backupFile": backup.name,
            "createdAt": int(time.time()),
        },
        mode=0o640,
    )


def clear_recovery(paths: AppPaths) -> None:
    _durable_unlink(paths.update_recovery)


def recover_interrupted_update(paths: AppPaths, bundled_version: str) -> ReleaseDescriptor | None:
    if not paths.update_recovery.is_file():
        return None
    try:
        value = json.loads(paths.update_recovery.read_text(encoding="utf-8"))
        if value.get("protocol") != 1:
            raise ValueError("invalid recovery protocol")
        update_id = _update_id(value)
        previous = descriptor_from_json(paths, value["previousRelease"], bundled_version=bundled_version)
        backup_name = str(value["backupFile"])
        if Path(backup_name).name != backup_name:
            raise ValueError("invalid backup name")
        backup = paths.backups_dir / backup_name
        restore_database(paths, backup)
        write_current_release(paths, previous)
        update_record(
            paths,
            update_id,
            status="ROLLED_BACK",
            stage="RECOVERED_AFTER_INTERRUPTION",
            progress=100,
            error="更新过程被中断，启动器已恢复数据库和上一版本",
            backup_filename=backup.name,
            complete=True,
            audit_action="system.system_update.interrupted_rollback",
            audit_outcome="failure",
        )
        clear_pending(paths)
        clear_recovery(paths)
        return previous
    except Exception as exc:
        raise RuntimeError("无法从中断的系统更新中自动恢复") from exc


def update_record(
    paths: AppPaths,
    update_id: str,
    *,
    status: str | None = None,
    stage: str | None = None,
    progress: int | None = None,
    error: str | None = None,
    backup_filename: str | None = None,
    release: ReleaseDescriptor | None = None,
    previous: ReleaseDescriptor | None = None,
    complete: bool = False,
    audit_action: str | None = None,
    audit_outcome: str = "success",
) -> None:
    database = Database(paths.database)
    try:
        database.configure_database()
        now = int(time.time())
        with database.session() as db:
            row = db.get(SystemUpdateModel, update_id)
            if row is None:
                raise RuntimeError("系统更新记录不存在")
            if status is not None:
                row.status = status
            if stage is not None:
                row.stage = stage
            if progress is not None:
                row.progress = max(0, min(100, progress))
            if error is not None:
                row.error_message = error[:2_000]
            if backup_filename is not None:
                row.backup_filename = backup_filename[:255]
            if release is not None:
                row.release_descriptor_json = json.dumps(release.as_json(), ensure_ascii=False, separators=(",", ":"))
            if previous is not None:
                row.previous_release_json = json.dumps(previous.as_json(), ensure_ascii=False, separators=(",", ":"))
            row.updated_at = now
            if complete:
                row.completed_at = now
                row.active_guard = None
            if audit_action:
                add_audit(
                    db,
                    now=now,
                    request=RequestMetadata(
                        client_ip=row.client_ip,
                        user_agent="fcc-launcher",
                        method="SYSTEM",
                        path="system-update-supervisor",
                        request_id=row.request_id or "",
                    ),
                    action=audit_action,
                    outcome=audit_outcome,
                    actor_user_id=row.created_by,
                    target_type="system_update",
                    target_id=row.id,
                    target_name=f"{row.source_version} → {row.target_version}",
                    details={
                        "operation": row.operation,
                        "sourceVersion": row.source_version,
                        "targetVersion": row.target_version,
                        "status": row.status,
                        "stage": row.stage,
                        "backupFilename": row.backup_filename,
                        "error": row.error_message,
                    },
                )
    finally:
        database.dispose()


def active_run_count(paths: AppPaths) -> int:
    database = Database(paths.database)
    try:
        database.configure_database()
        with database.session() as db:
            return int(
                db.scalar(select(func.count(RunModel.request_id)).where(RunModel.status.in_(ACTIVE_RUN_STATUSES)))
                or 0
            )
    finally:
        database.dispose()


def stage_apply_release(
    paths: AppPaths,
    pending: dict[str, Any],
    *,
    current_version: str,
    maximum_bytes: int,
) -> ReleaseDescriptor:
    update_id = _update_id(pending)
    package_name = str(pending.get("packageFile", ""))
    if Path(package_name).name != package_name or package_name != f"{update_id}.fcup":
        raise RuntimeError("更新控制文件引用了无效包路径")
    package_path = paths.update_inbox / package_name
    inspected = inspect_update_package(
        package_path,
        current_version=current_version,
        maximum_bytes=maximum_bytes,
    )
    if inspected.package_sha256.hex() != pending.get("packageSha256"):
        raise RuntimeError("更新包与控制文件校验值不一致")
    directory_name = f"{inspected.manifest.version}-{update_id[:8]}"
    final_dir = paths.releases_dir / directory_name
    if final_dir.exists():
        raise RuntimeError("目标版本目录已经存在")
    stage_dir = paths.releases_dir / f".stage-{update_id}"
    shutil.rmtree(stage_dir, ignore_errors=True)
    extract_update_wheels(package_path, inspected, stage_dir)
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", str(stage_dir / "venv")],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=180,
        )
        candidate_python = stage_dir / "venv" / "bin" / "python"
        wheelhouse = stage_dir / "wheels"
        app_wheel = stage_dir / Path(*Path(inspected.manifest.app_wheel).parts)
        install = subprocess.run(
            [
                str(candidate_python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-index",
                "--find-links",
                str(wheelhouse),
                str(app_wheel),
            ],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=600,
        )
        if install.returncode != 0:
            raise RuntimeError(f"离线安装平台依赖失败：{_last_output(install.stdout)}")
        verify = subprocess.run(
            [
                str(candidate_python),
                "-c",
                "import importlib.metadata; print(importlib.metadata.version('feature-control-center'))",
            ],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
        )
        if verify.returncode != 0 or verify.stdout.strip() != inspected.manifest.version:
            raise RuntimeError("安装后的平台版本与更新清单不一致")
        _make_release_readable(stage_dir)
        os.replace(stage_dir, final_dir)
    except BaseException:
        shutil.rmtree(stage_dir, ignore_errors=True)
        raise
    return ReleaseDescriptor(
        "installed",
        inspected.manifest.version,
        final_dir / "venv" / "bin" / "python",
        directory_name,
        False,
        inspected.manifest.database_revision,
    )


def rollback_target(paths: AppPaths, update_id: str, bundled_version: str) -> ReleaseDescriptor:
    database = Database(paths.database)
    try:
        database.configure_database()
        with database.session() as db:
            row = db.get(SystemUpdateModel, update_id)
            if row is None or row.operation != "ROLLBACK":
                raise RuntimeError("回退记录不存在")
            manifest = json.loads(row.manifest_json)
            target = descriptor_from_json(paths, manifest["targetRelease"], bundled_version=bundled_version)
            return replace(target, skip_migrations=True)
    finally:
        database.dispose()


def backup_database(paths: AppPaths, update_id: str, source_version: str) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    safe_version = "".join(character for character in source_version if character.isalnum() or character in ".-")[:32]
    destination = paths.backups_dir / f"{timestamp}-{safe_version}-{update_id[:8]}.db"
    partial = destination.with_suffix(".db.partial")
    partial.unlink(missing_ok=True)
    source_connection = sqlite3.connect(paths.database)
    destination_connection = sqlite3.connect(partial)
    failure: BaseException | None = None
    try:
        source_connection.backup(destination_connection)
        result = destination_connection.execute("PRAGMA integrity_check").fetchone()
        if result is None or result[0] != "ok":
            raise RuntimeError("数据库备份完整性检查失败")
        destination_connection.commit()
    except BaseException as exc:
        failure = exc
    finally:
        destination_connection.close()
        source_connection.close()
    if failure is not None:
        partial.unlink(missing_ok=True)
        raise failure
    with partial.open("rb+") as backup_file:
        backup_file.flush()
        os.fsync(backup_file.fileno())
    try:
        partial.chmod(0o640)
    except OSError:
        pass
    os.replace(partial, destination)
    _fsync_directory(destination.parent)
    return destination


def restore_database(paths: AppPaths, backup: Path) -> None:
    if backup.parent.resolve() != paths.backups_dir.resolve() or not backup.is_file():
        raise RuntimeError("数据库备份路径无效")
    for suffix in ("-wal", "-shm"):
        Path(str(paths.database) + suffix).unlink(missing_ok=True)
    temp = paths.database.with_suffix(f".restore-{uuid.uuid4().hex}.tmp")
    shutil.copy2(backup, temp)
    try:
        connection = sqlite3.connect(temp)
        try:
            result = connection.execute("PRAGMA integrity_check").fetchone()
        finally:
            connection.close()
        if not result or result[0] != "ok":
            raise RuntimeError("数据库备份完整性检查失败")
        with temp.open("rb+") as restored_file:
            restored_file.flush()
            os.fsync(restored_file.fileno())
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    os.replace(temp, paths.database)
    _fsync_directory(paths.database.parent)


def run_preflight(
    descriptor: ReleaseDescriptor,
    *,
    data_dir: Path,
    public_url: str,
    uid: int,
    gid: int,
    timeout: int = 120,
) -> None:
    command = [
        str(descriptor.python_executable),
        "-m",
        "app.preflight",
        "--data-dir",
        str(data_dir),
        "--public-url",
        public_url,
    ]
    if descriptor.skip_migrations:
        command.append("--skip-migrations")
    result = subprocess.run(
        command,
        check=False,
        user=uid,
        group=gid,
        extra_groups=[],
        env=release_environment(descriptor),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"版本预检失败：{_last_output(result.stdout)}")
    if descriptor.database_revision and not descriptor.skip_migrations:
        try:
            with sqlite3.connect(data_dir / "fcc.db") as connection:
                revisions = {
                    str(row[0]) for row in connection.execute("SELECT version_num FROM alembic_version").fetchall()
                }
        except sqlite3.Error as exc:
            raise RuntimeError("无法确认候选版本的数据库迁移结果") from exc
        if revisions != {descriptor.database_revision}:
            raise RuntimeError(
                f"候选版本数据库迁移结果不符：期望 {descriptor.database_revision}，实际 {sorted(revisions)}"
            )


def release_environment(descriptor: ReleaseDescriptor) -> dict[str, str]:
    environment = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        environment.pop(key, None)
    environment["FCC_ACTIVE_VERSION"] = descriptor.version
    environment["FCC_RELEASE_KIND"] = descriptor.kind
    return environment


def _make_release_readable(root: Path) -> None:
    for path in [root, *root.rglob("*")]:
        try:
            if path.is_dir():
                path.chmod(0o755)
            else:
                executable = path.parent.name in {"bin", "Scripts"} and os.access(path, os.X_OK)
                path.chmod(0o755 if executable else 0o644)
        except OSError as exc:
            raise RuntimeError("无法设置版本目录权限") from exc


def _atomic_json(path: Path, value: dict[str, Any], *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    with temp.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, ensure_ascii=False, separators=(",", ":"))
        output.flush()
        os.fsync(output.fileno())
    try:
        temp.chmod(mode)
    except OSError:
        pass
    os.replace(temp, path)
    _fsync_directory(path.parent)


def _durable_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    _fsync_directory(path.parent)


def _fsync_directory(directory: Path) -> None:
    """Persist directory entry changes on Linux; other platforms may not support it."""
    if os.name == "nt":
        return
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _update_id(pending: dict[str, Any]) -> str:
    value = str(pending.get("updateId", ""))
    if len(value) != 32 or any(character not in "0123456789abcdef" for character in value):
        raise RuntimeError("更新控制文件 ID 无效")
    return value


def _last_output(value: str, maximum: int = 1_500) -> str:
    clean = " ".join(value.strip().split())
    return clean[-maximum:] or "没有可用输出"
