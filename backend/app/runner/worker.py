from __future__ import annotations

import json
import logging
import os
import queue
import secrets
import signal
import subprocess
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import select, update

from app.application.runs import TERMINAL_RUN_STATUSES
from app.application.settings import SettingsService
from app.domain.time import Clock
from app.infrastructure.database import Database
from app.infrastructure.models import RunEventModel, RunnerHeartbeatModel, RunModel
from app.runner.dependencies import DependencyPreparer
from app.runner.events import PendingEvent, RunEventWriter, normalize_context, sanitize_message
from app.runner.materializer import PreparedRun, RunMaterializer
from app.runner.reports import ReportCommand, RunReportWriter
from app.runner.retention import RunLogRetentionCleaner, SystemLogRetentionCleaner


logger = logging.getLogger(__name__)


class RunnerAlreadyActive(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RawLine:
    source: str
    occurred_at_ms: int
    text: str


@dataclass(slots=True)
class RunningProcess:
    prepared: PreparedRun
    process: subprocess.Popen[bytes]
    output: queue.Queue[RawLine]
    readers: tuple[threading.Thread, threading.Thread]
    started_monotonic: float
    max_runtime_seconds: int | None
    pending: list[PendingEvent] = field(default_factory=list)
    pending_reports: list[ReportCommand] = field(default_factory=list)
    last_flush_monotonic: float = field(default_factory=time.monotonic)
    termination_started_monotonic: float | None = None
    timeout_requested: bool = False
    interrupted: bool = False
    force_killed: bool = False


class RunnerWorker:
    """Persistent queue owner and process supervisor for feature scripts."""

    def __init__(
        self,
        *,
        database: Database,
        settings: SettingsService,
        clock: Clock,
        materializer: RunMaterializer,
        dependency_preparer: DependencyPreparer,
        runner_id: str = "primary",
    ) -> None:
        self.database = database
        self.settings = settings
        self.clock = clock
        self.materializer = materializer
        self.dependency_preparer = dependency_preparer
        self.log_retention = RunLogRetentionCleaner(database, settings, clock)
        self.system_log_retention = SystemLogRetentionCleaner(materializer.paths, settings, clock)
        self.report_writer = RunReportWriter(database)
        self.runner_id = runner_id
        self.instance_token = secrets.token_hex(16)
        self.processes: dict[str, RunningProcess] = {}
        self._dependency_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fcc-dependencies")
        self._dependency_jobs: dict[str, Future[None]] = {}
        self._started = False
        self._shutdown_requested = False
        self._last_heartbeat_monotonic = 0.0
        self._next_log_cleanup_monotonic = 0.0

    def start(self) -> None:
        if self._started:
            return
        runner_settings = self.settings.runner()
        now = self.clock.now()
        interrupted_reports: list[str] = []
        with self.database.session() as db:
            healthy_owners = db.scalars(
                select(RunnerHeartbeatModel).where(
                    RunnerHeartbeatModel.status == "ACTIVE",
                    RunnerHeartbeatModel.heartbeat_at >= now - runner_settings.stale_after_seconds,
                )
            ).all()
            for healthy_owner in healthy_owners:
                if healthy_owner.instance_token == self.instance_token:
                    continue
                if healthy_owner.process_id != os.getpid() and self._pid_is_alive(healthy_owner.process_id):
                    raise RunnerAlreadyActive("已有健康 Runner 持有执行权，拒绝启动第二个实例")
                healthy_owner.status = "STOPPING"
            heartbeat = db.get(RunnerHeartbeatModel, self.runner_id)
            if heartbeat is None:
                heartbeat = RunnerHeartbeatModel(
                    runner_id=self.runner_id,
                    instance_token=self.instance_token,
                    process_id=os.getpid(),
                    status="ACTIVE",
                    started_at=now,
                    heartbeat_at=now,
                )
                db.add(heartbeat)
            else:
                heartbeat.instance_token = self.instance_token
                heartbeat.process_id = os.getpid()
                heartbeat.status = "ACTIVE"
                heartbeat.started_at = now
                heartbeat.heartbeat_at = now

            stale_runs = db.scalars(
                select(RunModel).where(
                    (RunModel.status.in_({"STARTING", "RUNNING"}))
                    | ((RunModel.status == "STOPPING") & RunModel.runner_id.is_not(None))
                )
            ).all()
            for run in stale_runs:
                run.status = "INTERRUPTED"
                run.finished_at = now
                run.process_id = None
                run.failure_summary = "Runner 重启，无法确认原进程的最终状态"
                run.last_event_sequence += 1
                run.final_event_sequence = run.last_event_sequence
                db.add(
                    RunEventModel(
                        run_request_id=run.request_id,
                        sequence=run.last_event_sequence,
                        occurred_at_ms=now * 1000,
                        level="ERROR",
                        source="PLATFORM",
                        message="Runner 重启，任务被标记为已中断；平台不会自动重试",
                        context_json="{}",
                    )
                )
                interrupted_reports.append(run.request_id)
        for request_id in interrupted_reports:
            self.report_writer.seal(request_id, "INTERRUPTED", now)
        self._started = True
        self._last_heartbeat_monotonic = time.monotonic()

    def tick(self) -> None:
        if not self._started:
            self.start()
        runner_settings = self.settings.runner()
        self._heartbeat_if_due(runner_settings.heartbeat_seconds)
        self._cleanup_logs_if_due()
        self._maintain_dependency_job()
        self._finish_unstarted_stops()
        for request_id in list(self.processes):
            self._supervise(request_id, runner_settings)
        if not self._shutdown_requested:
            while len(self.processes) < runner_settings.max_concurrency:
                request_id = self._claim_next()
                if request_id is None:
                    break
                self._launch(request_id, runner_settings)

    def run_forever(self) -> None:
        self.start()
        try:
            while not self._shutdown_requested:
                self.tick()
                time.sleep(self.settings.runner().poll_interval_ms / 1000)
        finally:
            self.shutdown()

    def request_shutdown(self) -> None:
        self._shutdown_requested = True

    def run_until_idle(self, timeout_seconds: float = 15) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            self.tick()
            if not self.processes and not self._has_pending_run() and not self._dependency_jobs:
                return
            time.sleep(self.settings.runner().poll_interval_ms / 1000)
        raise TimeoutError("Runner 在测试等待时间内没有进入空闲状态")

    def shutdown(self) -> None:
        if not self._started:
            self._dependency_executor.shutdown(wait=False, cancel_futures=True)
            return
        self._shutdown_requested = True
        settings = self.settings.runner()
        deadline = time.monotonic() + settings.stop_grace_seconds + 2
        for running in self.processes.values():
            if running.termination_started_monotonic is None:
                running.interrupted = True
                self._begin_termination(running, "Runner 正在关闭，任务将标记为已中断")
        while self.processes and time.monotonic() < deadline:
            for request_id in list(self.processes):
                self._supervise(request_id, settings)
            time.sleep(0.05)
        for request_id, running in list(self.processes.items()):
            self._force_kill(running)
            try:
                running.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
            self._complete_process(request_id, running)
        self._dependency_executor.shutdown(wait=False, cancel_futures=True)
        with self.database.session() as db:
            heartbeat = db.get(RunnerHeartbeatModel, self.runner_id)
            if heartbeat is not None and heartbeat.instance_token == self.instance_token:
                heartbeat.status = "STOPPING"
                heartbeat.heartbeat_at = self.clock.now()
        self._started = False

    def _heartbeat_if_due(self, interval_seconds: int) -> None:
        now_monotonic = time.monotonic()
        if now_monotonic - self._last_heartbeat_monotonic < interval_seconds:
            return
        now = self.clock.now()
        with self.database.session() as db:
            heartbeat = db.get(RunnerHeartbeatModel, self.runner_id)
            if heartbeat is None or heartbeat.instance_token != self.instance_token:
                raise RunnerAlreadyActive("Runner 执行权已经丢失")
            heartbeat.heartbeat_at = now
            heartbeat.status = "ACTIVE"
            for request_id in self.processes:
                run = db.get(RunModel, request_id)
                if run is not None and run.status not in TERMINAL_RUN_STATUSES:
                    run.runner_heartbeat_at = now
        self._last_heartbeat_monotonic = now_monotonic

    def _cleanup_logs_if_due(self) -> None:
        now_monotonic = time.monotonic()
        if now_monotonic < self._next_log_cleanup_monotonic:
            return
        try:
            result = self.log_retention.purge_batch()
            system_result = self.system_log_retention.purge()
        except Exception:
            # Cleanup must not take down process supervision. A short retry delay also
            # avoids turning a persistent storage error into a busy loop.
            logger.exception("运行日志自动清理失败，将在 60 秒后重试")
            self._next_log_cleanup_monotonic = now_monotonic + 60
            return
        if result.purged_runs:
            logger.info(
                "已按 %s 天保留期清理 %s 个任务的 %s 条日志事件",
                result.retention_days,
                result.purged_runs,
                result.deleted_events,
            )
        if system_result.deleted_files:
            logger.info(
                "已按 %s 天保留期与可选容量上限清理 %s 个程序日志文件，共 %s 字节",
                system_result.retention_days,
                system_result.deleted_files,
                system_result.deleted_bytes,
            )
        self._next_log_cleanup_monotonic = now_monotonic + (1 if result.has_more else 3_600)

    def _maintain_dependency_job(self) -> None:
        for environment_id, future in list(self._dependency_jobs.items()):
            if future.done():
                try:
                    future.result()
                except Exception:
                    # DependencyPreparer normally seals failures itself. Keep Runner alive if a
                    # storage-level exception escapes, so existing feature runs remain controllable.
                    pass
                finally:
                    self._dependency_jobs.pop(environment_id, None)
        if self._shutdown_requested or self._dependency_jobs:
            return
        environment_id = self.dependency_preparer.next_environment_id(set(self._dependency_jobs))
        if environment_id:
            self._dependency_jobs[environment_id] = self._dependency_executor.submit(
                self.dependency_preparer.prepare, environment_id
            )

    def _finish_unstarted_stops(self) -> None:
        now = self.clock.now()
        with self.database.session() as db:
            rows = db.scalars(
                select(RunModel).where(
                    RunModel.status == "STOPPING",
                    RunModel.runner_id.is_(None),
                )
            ).all()
            for run in rows:
                run.last_event_sequence += 1
                run.status = "STOPPED"
                run.finished_at = now
                run.final_event_sequence = run.last_event_sequence
                db.add(
                    RunEventModel(
                        run_request_id=run.request_id,
                        sequence=run.last_event_sequence,
                        occurred_at_ms=now * 1000,
                        level="WARNING",
                        source="PLATFORM",
                        message="任务在启动前收到停止请求，未执行功能代码",
                        context_json="{}",
                    )
                )

    def _claim_next(self) -> str | None:
        now = self.clock.now()
        with self.database.session() as db:
            candidates = db.scalars(
                select(RunModel)
                .where(RunModel.status == "QUEUED")
                .order_by(RunModel.queued_at, RunModel.request_id)
                .limit(10)
            ).all()
            active_features: set[str] = set()
            for running in self.processes.values():
                active_run = db.get(RunModel, running.prepared.request_id)
                if active_run is not None:
                    active_features.add(active_run.customer_feature_id)
            candidate = next((item for item in candidates if item.customer_feature_id not in active_features), None)
            if candidate is None:
                return None
            changed = db.execute(
                update(RunModel)
                .where(RunModel.request_id == candidate.request_id, RunModel.status == "QUEUED")
                .values(
                    status="STARTING",
                    claimed_at=now,
                    runner_id=self.runner_id,
                    runner_heartbeat_at=now,
                )
            ).rowcount
            return candidate.request_id if changed == 1 else None

    def _launch(self, request_id: str, runner_settings) -> None:
        writer = self._writer(runner_settings)
        writer.append(
            request_id,
            [PendingEvent(self.clock.now() * 1000, "INFO", "PLATFORM", "Runner 已领取任务，正在准备隔离工作目录")],
        )
        event_token = secrets.token_urlsafe(18)
        prepared: PreparedRun | None = None
        process: subprocess.Popen[bytes] | None = None
        try:
            prepared = self.materializer.prepare(
                request_id,
                event_token,
                runner_settings.report_max_items,
            )
            command = [
                str(prepared.python_executable),
                "-u",
                "-B",
                str(prepared.work_dir / "_fcc_bootstrap.py"),
                str(prepared.input_file),
            ]
            output_queue: queue.Queue[RawLine] = queue.Queue()
            identity_options: dict[str, object] = {}
            identity = self.materializer.script_identity
            if os.name != "nt" and identity.uid is not None and identity.gid is not None:
                identity_options = {"user": identity.uid, "group": identity.gid, "extra_groups": []}
            process = subprocess.Popen(
                command,
                cwd=prepared.package_dir,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._sanitized_environment(prepared, self.settings.timezone_name()),
                close_fds=True,
                start_new_session=os.name != "nt",
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
                **identity_options,
            )
            assert process.stdout is not None and process.stderr is not None
            readers = (
                self._start_reader(process.stdout, "STDOUT", output_queue, runner_settings.max_event_bytes),
                self._start_reader(process.stderr, "STDERR", output_queue, runner_settings.max_event_bytes),
            )
            running = RunningProcess(
                prepared=prepared,
                process=process,
                output=output_queue,
                readers=readers,
                started_monotonic=time.monotonic(),
                max_runtime_seconds=self._max_runtime(request_id),
            )
            self.processes[request_id] = running
            now = self.clock.now()
            with self.database.session() as db:
                run = db.get(RunModel, request_id)
                if run is None:
                    raise RuntimeError("任务记录在启动时消失")
                run.status = "RUNNING"
                run.started_at = now
                run.process_id = process.pid
            writer.append(
                request_id,
                [PendingEvent(now * 1000, "INFO", "PLATFORM", "功能进程已启动", {"processId": process.pid})],
            )
        except Exception as exc:
            self.processes.pop(request_id, None)
            if process is not None and process.poll() is None:
                self._kill_process_group(process)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            if prepared is not None:
                self.materializer.cleanup(prepared)
            message = sanitize_message(exc, runner_settings.max_event_bytes)
            writer.append(
                request_id,
                [PendingEvent(self.clock.now() * 1000, "ERROR", "PLATFORM", f"任务启动失败：{message}")],
            )
            self._seal(request_id, "FAILED", None, "任务启动失败")

    def _supervise(self, request_id: str, runner_settings) -> None:
        running = self.processes.get(request_id)
        if running is None:
            return
        self._drain_output(running, runner_settings)
        with self.database.session() as db:
            run = db.get(RunModel, request_id)
            stop_requested = bool(run and run.stop_requested_at is not None)
        elapsed = time.monotonic() - running.started_monotonic
        timed_out = bool(
            running.max_runtime_seconds
            and running.max_runtime_seconds > 0
            and elapsed >= running.max_runtime_seconds
        )
        if timed_out and running.termination_started_monotonic is None:
            running.timeout_requested = True
            self._mark_stopping(request_id, "TIMEOUT")
            self._begin_termination(running, "任务超过最长运行时间，已请求停止")
        elif stop_requested and running.termination_started_monotonic is None:
            self._begin_termination(running, "已向功能进程发送停止请求")
        if (
            running.termination_started_monotonic is not None
            and running.process.poll() is None
            and time.monotonic() - running.termination_started_monotonic >= runner_settings.stop_grace_seconds
            and not running.force_killed
        ):
            self._force_kill(running)
            running.pending.append(
                PendingEvent(
                    self.clock.now() * 1000,
                    "WARNING",
                    "PLATFORM",
                    "功能进程未在宽限期内退出，已强制终止进程组",
                )
            )
        if self._should_flush(running, runner_settings):
            self._flush(running, runner_settings)
        if running.process.poll() is not None:
            self._complete_process(request_id, running)

    def _begin_termination(self, running: RunningProcess, message: str) -> None:
        running.termination_started_monotonic = time.monotonic()
        try:
            running.prepared.cancel_file.touch(exist_ok=True)
        except OSError:
            pass
        self._terminate_process_group(running.process)
        now = self.clock.now()
        with self.database.session() as db:
            run = db.get(RunModel, running.prepared.request_id)
            if run is not None and run.status not in TERMINAL_RUN_STATUSES:
                run.status = "STOPPING"
                run.term_sent_at = now
        running.pending.append(PendingEvent(now * 1000, "WARNING", "PLATFORM", message))

    def _force_kill(self, running: RunningProcess) -> None:
        running.force_killed = True
        self._kill_process_group(running.process)
        with self.database.session() as db:
            run = db.get(RunModel, running.prepared.request_id)
            if run is not None and run.status not in TERMINAL_RUN_STATUSES:
                run.kill_sent_at = self.clock.now()

    def _complete_process(self, request_id: str, running: RunningProcess) -> None:
        for thread in running.readers:
            thread.join()
        settings = self.settings.runner()
        self._drain_output(running, settings)
        self._flush(running, settings)
        exit_code = running.process.poll()
        if running.interrupted:
            status = "INTERRUPTED"
            level, message, failure = "ERROR", "Runner 关闭，任务执行被中断", "Runner 关闭"
        elif running.timeout_requested:
            status = "TIMED_OUT"
            level, message, failure = "ERROR", "任务已因超过最长运行时间而结束", "任务运行超时"
        else:
            with self.database.session() as db:
                run = db.get(RunModel, request_id)
                stopped = bool(run and run.stop_requested_at is not None)
            if stopped or exit_code == 20:
                status = "STOPPED"
                level, message, failure = "WARNING", "任务已停止", None
            elif exit_code == 0:
                status = "SUCCEEDED"
                level, message, failure = "INFO", "任务执行成功", None
            else:
                status = "FAILED"
                level, message, failure = "ERROR", f"任务执行失败，进程退出码 {exit_code}", "功能进程异常退出"
        self._writer(settings).append(
            request_id,
            [PendingEvent(self.clock.now() * 1000, level, "PLATFORM", message, {"exitCode": exit_code})],
        )
        self._seal(request_id, status, exit_code, failure)
        self.materializer.cleanup(running.prepared)
        self.processes.pop(request_id, None)

    def _seal(self, request_id: str, status: str, exit_code: int | None, failure: str | None) -> None:
        completed_at: int | None = None
        with self.database.session() as db:
            run = db.get(RunModel, request_id)
            if run is None or run.status in TERMINAL_RUN_STATUSES:
                return
            run.status = status
            run.exit_code = exit_code
            run.failure_summary = failure
            completed_at = self.clock.now()
            run.finished_at = completed_at
            run.process_id = None
            run.final_event_sequence = run.last_event_sequence
        if completed_at is not None:
            self.report_writer.seal(request_id, status, completed_at)

    def _mark_stopping(self, request_id: str, reason: str) -> None:
        with self.database.session() as db:
            run = db.get(RunModel, request_id)
            if run is not None and run.status not in TERMINAL_RUN_STATUSES:
                run.status = "STOPPING"
                run.stop_reason = reason

    def _drain_output(self, running: RunningProcess, runner_settings) -> None:
        while True:
            try:
                line = running.output.get_nowait()
            except queue.Empty:
                break
            parsed = self._parse_line(running.prepared.event_token, line, runner_settings)
            if isinstance(parsed, ReportCommand):
                running.pending_reports.append(parsed)
            elif parsed is not None:
                running.pending.append(parsed)

    @staticmethod
    def _parse_line(event_token: str, line: RawLine, runner_settings) -> PendingEvent | ReportCommand | None:
        prefix = f"\x1eFCC:{event_token}:"
        if line.source == "STDOUT" and line.text.startswith(prefix):
            try:
                payload = json.loads(line.text[len(prefix) :])
                if not isinstance(payload, dict):
                    raise ValueError
                kind = str(payload.get("kind", "log"))
                if kind in {"report.start", "report.item", "report.complete"}:
                    return ReportCommand(line.occurred_at_ms, kind, payload)
                if kind != "log":
                    raise ValueError
                return PendingEvent(
                    line.occurred_at_ms,
                    str(payload.get("level", "INFO")).upper(),
                    "SDK",
                    sanitize_message(payload.get("message", ""), runner_settings.max_event_bytes),
                    normalize_context(payload.get("context", {}), runner_settings.max_context_bytes),
                )
            except (ValueError, TypeError, json.JSONDecodeError):
                return PendingEvent(
                    line.occurred_at_ms,
                    "WARNING",
                    "PLATFORM",
                    "收到格式无效的 SDK 日志事件",
                )
        if not line.text:
            return None
        return PendingEvent(
            line.occurred_at_ms,
            "ERROR" if line.source == "STDERR" else "INFO",
            line.source,
            sanitize_message(line.text, runner_settings.max_event_bytes),
        )

    def _flush(self, running: RunningProcess, runner_settings) -> None:
        if running.pending_reports:
            warnings = self.report_writer.apply_batch(
                running.prepared.request_id,
                running.prepared.report_schema,
                running.pending_reports,
                running.prepared.report_max_items,
            )
            running.pending_reports.clear()
            running.pending.extend(
                PendingEvent(self.clock.now() * 1000, "WARNING", "PLATFORM", message)
                for message in warnings
            )
        if running.pending:
            self._writer(runner_settings).append(running.prepared.request_id, running.pending)
            running.pending.clear()
        running.last_flush_monotonic = time.monotonic()

    @staticmethod
    def _should_flush(running: RunningProcess, runner_settings) -> bool:
        pending_count = len(running.pending) + len(running.pending_reports)
        return pending_count >= runner_settings.log_batch_size or (
            pending_count > 0
            and (time.monotonic() - running.last_flush_monotonic) * 1000 >= runner_settings.log_flush_ms
        )

    def _writer(self, runner_settings) -> RunEventWriter:
        return RunEventWriter(
            self.database,
            max_event_bytes=runner_settings.max_event_bytes,
            max_context_bytes=runner_settings.max_context_bytes,
        )

    def _max_runtime(self, request_id: str) -> int | None:
        with self.database.session() as db:
            run = db.get(RunModel, request_id)
            return run.max_runtime_seconds if run else None

    def _has_pending_run(self) -> bool:
        with self.database.session() as db:
            return db.scalar(select(RunModel.request_id).where(RunModel.status.in_({"QUEUED", "STOPPING"}))) is not None

    @staticmethod
    def _start_reader(
        pipe: BinaryIO,
        source: str,
        output: queue.Queue[RawLine],
        max_event_bytes: int,
    ) -> threading.Thread:
        def collect() -> None:
            try:
                while chunk := pipe.readline(max_event_bytes + 1):
                    text = chunk.decode("utf-8", errors="replace").rstrip("\r\n")
                    output.put(RawLine(source, time.time_ns() // 1_000_000, text))
            finally:
                pipe.close()

        thread = threading.Thread(target=collect, name=f"fcc-{source.lower()}", daemon=True)
        thread.start()
        return thread

    @staticmethod
    def _sanitized_environment(prepared: PreparedRun, timezone_name: str) -> dict[str, str]:
        environment = {
            "PYTHONUTF8": "1",
            "PYTHONUNBUFFERED": "1",
            "PYTHONNOUSERSITE": "1",
            "HOME": str(prepared.work_dir / "home"),
            "TMPDIR": str(prepared.work_dir / "tmp"),
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "TZ": timezone_name,
        }
        if os.name == "nt":
            for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "PATH"):
                if value := os.environ.get(key):
                    environment[key] = value
        return environment

    @staticmethod
    def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name == "nt":
                process.terminate()
            else:
                os.killpg(process.pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass

    @staticmethod
    def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except (OSError, subprocess.TimeoutExpired, ProcessLookupError):
            try:
                process.kill()
            except OSError:
                pass

    @staticmethod
    def _pid_is_alive(process_id: int) -> bool:
        if process_id <= 0:
            return False
        try:
            os.kill(process_id, 0)
        except OSError:
            return False
        return True
