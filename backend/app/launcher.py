from __future__ import annotations

import argparse
import importlib.metadata
import logging
import os
import shutil
import signal
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from app.infrastructure.paths import AppPaths
from app.infrastructure.runtime_permissions import (
    ensure_log_files_readable,
    prepare_root_directory,
    prepare_runs_root,
    repair_runtime_cache,
)
from app.infrastructure.system_logging import configure_system_logging
from app.update_supervisor import (
    ReleaseDescriptor,
    active_run_count,
    backup_database,
    clear_pending,
    clear_recovery,
    load_current_release,
    load_pending,
    recover_interrupted_update,
    reconcile_orphaned_handoff,
    recover_rejected_control,
    release_environment,
    restore_database,
    rollback_target,
    run_preflight,
    stage_apply_release,
    update_record,
    validate_pending_record,
    write_current_release,
    write_launcher_state,
    write_recovery,
)


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ManagedProcesses:
    web: subprocess.Popen[bytes]
    runner: subprocess.Popen[bytes]
    scheduler: subprocess.Popen[bytes]

    def all(self) -> tuple[subprocess.Popen[bytes], ...]:
        return self.web, self.runner, self.scheduler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="功能控制中心单容器启动器")
    parser.add_argument("--data-dir", type=Path, default=Path("/data"))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--public-url", default="http://localhost:8080")
    return parser


def _account(name: str) -> tuple[int, int]:
    import pwd

    account = pwd.getpwnam(name)
    return account.pw_uid, account.pw_gid


def _prepare_permissions(paths: AppPaths, web_uid: int, web_gid: int) -> None:
    _, script_gid = _account("fcc-script")
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    os.chown(paths.data_dir, web_uid, web_gid)
    os.chmod(paths.data_dir, 0o2771)
    for name in ("fcc.db", "fcc.db-wal", "fcc.db-shm", "instance.key", "first-run.txt"):
        path = paths.data_dir / name
        if path.exists():
            os.chown(path, web_uid, web_gid)
            os.chmod(path, 0o660 if name.startswith("fcc.db") else 0o640)
    for path, mode in ((paths.runtime_cache, 0o755), (paths.temp_dir, 0o711)):
        prepare_root_directory(path, mode)
    repair_runtime_cache(paths.runtime_cache, script_gid)
    prepare_runs_root(paths.temp_dir / "runs", script_gid)
    paths.system_logs.mkdir(exist_ok=True)
    os.chown(paths.system_logs, web_uid, web_gid)
    os.chmod(paths.system_logs, 0o2770)
    for service in ("web", "runner", "scheduler", "launcher"):
        directory = paths.system_logs / service
        directory.mkdir(exist_ok=True)
        os.chown(directory, web_uid, web_gid)
        os.chmod(directory, 0o2770)
        ensure_log_files_readable(directory, web_gid)

    paths.updates_dir.mkdir(exist_ok=True)
    os.chown(paths.updates_dir, 0, web_gid)
    os.chmod(paths.updates_dir, 0o2750)
    paths.update_inbox.mkdir(exist_ok=True)
    os.chown(paths.update_inbox, web_uid, web_gid)
    os.chmod(paths.update_inbox, 0o2770)
    paths.update_control.mkdir(exist_ok=True)
    os.chown(paths.update_control, web_uid, web_gid)
    os.chmod(paths.update_control, 0o2770)
    for path in (paths.releases_dir, paths.backups_dir):
        path.mkdir(exist_ok=True)
        os.chown(path, 0, web_gid)
        os.chmod(path, 0o2750)
    for path in (paths.current_release, paths.update_recovery):
        if path.exists():
            os.chown(path, 0, web_gid)
            os.chmod(path, 0o640)


def _start_services(
    descriptor: ReleaseDescriptor,
    *,
    paths: AppPaths,
    host: str,
    port: int,
    public_url: str,
    web_uid: int,
    web_gid: int,
) -> ManagedProcesses:
    python = str(descriptor.python_executable)
    common = ["--data-dir", str(paths.data_dir), "--skip-migrations"]
    environment = release_environment(descriptor)
    started: list[subprocess.Popen[bytes]] = []
    try:
        web = subprocess.Popen(
            [
                python,
                "-m",
                "app.web.server",
                *common,
                "--host",
                host,
                "--port",
                str(port),
                "--public-url",
                public_url,
            ],
            user=web_uid,
            group=web_gid,
            extra_groups=[],
            env=environment,
        )
        started.append(web)
        runner = subprocess.Popen([python, "-m", "app.runner.main", *common], env=environment)
        started.append(runner)
        scheduler = subprocess.Popen(
            [python, "-m", "app.scheduler.main", *common],
            user=web_uid,
            group=web_gid,
            extra_groups=[],
            env=environment,
        )
        started.append(scheduler)
    except BaseException:
        logger.exception("平台子进程未能完整启动，正在清理已经启动的进程")
        for process in reversed(started):
            if process.poll() is None:
                try:
                    process.terminate()
                except OSError:
                    logger.warning("无法向已启动的子进程发送终止信号：pid=%s", process.pid)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and any(process.poll() is None for process in started):
            time.sleep(0.1)
        for process in started:
            if process.poll() is None:
                try:
                    process.kill()
                except OSError:
                    pass
            try:
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                logger.error("子进程清理超时：pid=%s", process.pid)
        raise
    logger.info("版本 %s 的 Web、Runner 与 Scheduler 已启动", descriptor.version)
    return ManagedProcesses(web, runner, scheduler)


def _stop_services(processes: ManagedProcesses, *, grace_seconds: int = 25) -> None:
    logger.info("正在停止平台子进程")
    for process in (processes.scheduler, processes.runner, processes.web):
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline and any(process.poll() is None for process in processes.all()):
        time.sleep(0.1)
    for process in processes.all():
        if process.poll() is None:
            process.kill()
    for process in processes.all():
        process.wait()


def _preflight(
    descriptor: ReleaseDescriptor,
    *,
    paths: AppPaths,
    public_url: str,
    web_uid: int,
    web_gid: int,
) -> None:
    run_preflight(
        descriptor,
        data_dir=paths.data_dir,
        public_url=public_url,
        uid=web_uid,
        gid=web_gid,
    )
    _prepare_permissions(paths, web_uid, web_gid)


def _wait_ready(
    processes: ManagedProcesses,
    *,
    paths: AppPaths,
    port: int,
    started_at: int,
    timeout: int = 70,
) -> None:
    deadline = time.monotonic() + timeout
    health_url = f"http://127.0.0.1:{port}/api/health/ready"
    last_error = "服务尚未就绪"
    while time.monotonic() < deadline:
        exited = [process.poll() for process in processes.all()]
        if any(code is not None for code in exited):
            raise RuntimeError(f"候选版本子进程提前退出：{exited}")
        web_ready = False
        try:
            with urllib.request.urlopen(health_url, timeout=2) as response:
                web_ready = response.status == 200
        except (OSError, urllib.error.URLError) as exc:
            last_error = str(exc)
        if web_ready and _worker_heartbeats_ready(paths, processes, started_at):
            return
        time.sleep(0.5)
    raise RuntimeError(f"候选版本健康检查超时：{last_error}")


def _worker_heartbeats_ready(paths: AppPaths, processes: ManagedProcesses, started_at: int) -> bool:
    try:
        with sqlite3.connect(paths.database) as connection:
            runner = connection.execute(
                "SELECT heartbeat_at, status, process_id, started_at, instance_token "
                "FROM runner_heartbeat WHERE process_id = ? ORDER BY heartbeat_at DESC LIMIT 1",
                (processes.runner.pid,),
            ).fetchone()
            scheduler = connection.execute(
                "SELECT heartbeat_at, status, process_id, started_at, instance_token "
                "FROM scheduler_heartbeat WHERE process_id = ? ORDER BY heartbeat_at DESC LIMIT 1",
                (processes.scheduler.pid,),
            ).fetchone()
        return bool(
            runner
            and scheduler
            and runner[0] >= started_at
            and scheduler[0] >= started_at
            and runner[1] == "ACTIVE"
            and scheduler[1] == "ACTIVE"
            and runner[2] == processes.runner.pid
            and scheduler[2] == processes.scheduler.pid
            and runner[3] >= started_at
            and scheduler[3] >= started_at
            and bool(runner[4])
            and bool(scheduler[4])
        )
    except sqlite3.Error:
        return False


def _process_update(
    pending: dict[str, object],
    current: ReleaseDescriptor,
    processes: ManagedProcesses,
    *,
    paths: AppPaths,
    bundled_version: str,
    host: str,
    port: int,
    public_url: str,
    web_uid: int,
    web_gid: int,
) -> tuple[ReleaseDescriptor, ManagedProcesses]:
    update_id = str(pending.get("updateId", ""))
    operation = str(pending.get("operation", ""))
    backup: Path | None = None
    candidate: ReleaseDescriptor | None = None
    candidate_processes: ManagedProcesses | None = None
    _stop_services(processes)
    try:
        # Keep the database row pending until a durable recovery marker exists.
        # A restart before that point can safely retry because no migration has run.
        update_record(paths, update_id, stage="VALIDATING", progress=20)
        if active_run_count(paths):
            raise RuntimeError("停止服务后仍检测到活动任务，已取消更新")
        if operation == "APPLY":
            update_record(paths, update_id, stage="INSTALLING_RELEASE", progress=30)
            candidate = stage_apply_release(
                paths,
                pending,
                current_version=current.version,
                maximum_bytes=2_147_483_648,
            )
        elif operation == "ROLLBACK":
            candidate = rollback_target(paths, update_id, bundled_version)
        else:
            raise RuntimeError("更新操作类型无效")

        update_record(paths, update_id, stage="BACKING_UP_DATABASE", progress=50)
        backup = backup_database(paths, update_id, current.version)
        write_recovery(paths, update_id=update_id, previous=current, backup=backup)
        update_record(paths, update_id, status="APPLYING", backup_filename=backup.name)

        update_record(paths, update_id, stage="DATABASE_PREFLIGHT", progress=62)
        _preflight(candidate, paths=paths, public_url=public_url, web_uid=web_uid, web_gid=web_gid)
        update_record(paths, update_id, stage="STARTING_CANDIDATE", progress=75)
        started_at = int(time.time())
        candidate_processes = _start_services(
            candidate,
            paths=paths,
            host=host,
            port=port,
            public_url=public_url,
            web_uid=web_uid,
            web_gid=web_gid,
        )
        try:
            _wait_ready(candidate_processes, paths=paths, port=port, started_at=started_at)
        except BaseException:
            _stop_services(candidate_processes)
            raise

        write_current_release(paths, candidate)
        update_record(
            paths,
            update_id,
            status="SUCCEEDED",
            stage="COMPLETED",
            progress=100,
            backup_filename=backup.name,
            release=candidate,
            previous=current,
            complete=True,
            audit_action=(
                "system.system_update.completed" if operation == "APPLY" else "system.system_update.rollback_completed"
            ),
        )
        clear_pending(paths)
        clear_recovery(paths)
        logger.info("系统版本切换完成：%s → %s", current.version, candidate.version)
        return candidate, candidate_processes
    except BaseException as exc:
        logger.exception("系统更新失败，正在恢复上一版本")
        if candidate_processes is not None:
            _stop_services(candidate_processes)
        restore_error: Exception | None = None
        if backup is not None:
            try:
                restore_database(paths, backup)
                _prepare_permissions(paths, web_uid, web_gid)
            except Exception as caught:
                restore_error = caught
                logger.exception("数据库自动恢复失败")
        if restore_error is not None:
            update_record(
                paths,
                update_id,
                status="FAILED",
                stage="RECOVERY_FAILED",
                progress=100,
                error=f"{exc}; 数据库恢复失败：{restore_error}",
                complete=True,
                audit_action="system.system_update.recovery_failed",
                audit_outcome="failure",
            )
            clear_pending(paths)
            raise RuntimeError("更新失败且数据库自动恢复失败，启动器停止以避免继续写入") from restore_error

        write_current_release(paths, current)
        _preflight(current, paths=paths, public_url=public_url, web_uid=web_uid, web_gid=web_gid)
        restored_at = int(time.time())
        restored_processes = _start_services(
            current,
            paths=paths,
            host=host,
            port=port,
            public_url=public_url,
            web_uid=web_uid,
            web_gid=web_gid,
        )
        try:
            _wait_ready(restored_processes, paths=paths, port=port, started_at=restored_at)
        except BaseException:
            _stop_services(restored_processes)
            raise
        final_status = "ROLLED_BACK" if backup is not None else "FAILED"
        update_record(
            paths,
            update_id,
            status=final_status,
            stage="AUTOMATIC_ROLLBACK" if backup is not None else "FAILED_BEFORE_DATABASE_CHANGE",
            progress=100,
            error=str(exc),
            backup_filename=backup.name if backup else None,
            complete=True,
            audit_action="system.system_update.automatic_rollback" if backup is not None else "system.system_update.failed",
            audit_outcome="failure",
        )
        clear_pending(paths)
        clear_recovery(paths)
        if operation == "APPLY" and candidate and candidate.release_dir_name:
            failed_release = paths.releases_dir / candidate.release_dir_name
            try:
                shutil.rmtree(failed_release)
            except OSError:
                logger.warning("无法清理未启用的候选版本目录：%s", failed_release)
        return current, restored_processes


def main() -> None:
    args = build_parser().parse_args()
    paths = AppPaths(args.data_dir.resolve())
    if os.name == "nt":
        raise RuntimeError("单容器启动器仅用于 Linux；Windows 开发环境请分别启动 Web、Runner 与 Scheduler")
    if os.geteuid() != 0:
        raise RuntimeError("单容器启动器需要 root，以便将功能进程降权到 fcc-script")
    os.umask(0o007)
    web_uid, web_gid = _account("fcc")
    _account("fcc-script")
    bundled_version = importlib.metadata.version("feature-control-center")
    _prepare_permissions(paths, web_uid, web_gid)
    configure_system_logging(paths.data_dir, "launcher")

    recovered = recover_interrupted_update(paths, bundled_version)
    if recovered is not None:
        # restore_database creates a new inode; restore the runtime ownership before
        # the unprivileged preflight opens SQLite.
        _prepare_permissions(paths, web_uid, web_gid)
    current = recovered or load_current_release(paths, bundled_version)
    _preflight(current, paths=paths, public_url=args.public_url, web_uid=web_uid, web_gid=web_gid)
    processes = _start_services(
        current,
        paths=paths,
        host=args.host,
        port=args.port,
        public_url=args.public_url,
        web_uid=web_uid,
        web_gid=web_gid,
    )
    stopping = False

    def stop(_signum, _frame) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    exit_code = 0
    last_state_write = 0.0
    last_handoff_reconcile = 0.0
    try:
        while not stopping:
            now = time.monotonic()
            if now - last_state_write >= 2:
                write_launcher_state(paths, current)
                last_state_write = now
            try:
                pending = load_pending(paths)
            except Exception:
                logger.exception("拒绝无法解析的更新控制文件")
                clear_pending(paths)
                reconcile_orphaned_handoff(paths, grace_seconds=0)
                continue
            if pending is not None:
                try:
                    validate_pending_record(paths, pending, current.version)
                except Exception as exc:
                    logger.exception("拒绝数据库状态不匹配的更新控制文件")
                    recover_rejected_control(paths, pending, exc)
                    clear_pending(paths)
                    continue
                current, processes = _process_update(
                    pending,
                    current,
                    processes,
                    paths=paths,
                    bundled_version=bundled_version,
                    host=args.host,
                    port=args.port,
                    public_url=args.public_url,
                    web_uid=web_uid,
                    web_gid=web_gid,
                )
                write_launcher_state(paths, current)
                continue
            if now - last_handoff_reconcile >= 5:
                last_handoff_reconcile = now
                if reconcile_orphaned_handoff(paths):
                    logger.warning("已恢复未完成控制文件交接的更新记录")
            codes = [process.poll() for process in processes.all()]
            if any(code is not None for code in codes):
                logger.error("子进程提前退出 web=%s runner=%s scheduler=%s", *codes)
                exit_code = next((code for code in codes if code not in (None, 0)), 1)
                stopping = True
                break
            time.sleep(0.25)
    finally:
        _stop_services(processes)
        paths.launcher_state.unlink(missing_ok=True)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
