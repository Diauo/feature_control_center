from __future__ import annotations

import logging
import os
import secrets
import time

from sqlalchemy import select

from app.application.schedules import ScheduleService
from app.application.settings import SettingsService
from app.domain.time import Clock
from app.infrastructure.database import Database
from app.infrastructure.models import SchedulerHeartbeatModel


logger = logging.getLogger(__name__)


class SchedulerAlreadyActive(RuntimeError):
    pass


class SchedulerWorker:
    """Single database-backed schedule owner. It only enqueues runs."""

    def __init__(
        self,
        *,
        database: Database,
        settings: SettingsService,
        schedules: ScheduleService,
        clock: Clock,
        scheduler_id: str = "primary",
    ) -> None:
        self.database = database
        self.settings = settings
        self.schedules = schedules
        self.clock = clock
        self.scheduler_id = scheduler_id
        self.instance_token = secrets.token_hex(16)
        self._started = False
        self._shutdown_requested = False
        self._last_heartbeat_monotonic = 0.0
        self._next_timezone_reconcile_monotonic = 0.0

    def start(self) -> None:
        if self._started:
            return
        config = self.settings.scheduler()
        now = self.clock.now()
        with self.database.session() as db:
            owners = db.scalars(
                select(SchedulerHeartbeatModel).where(
                    SchedulerHeartbeatModel.status == "ACTIVE",
                    SchedulerHeartbeatModel.heartbeat_at >= now - config.stale_after_seconds,
                )
            ).all()
            for owner in owners:
                if owner.instance_token == self.instance_token:
                    continue
                if owner.process_id != os.getpid() and self._pid_is_alive(owner.process_id):
                    raise SchedulerAlreadyActive("已有健康 Scheduler 持有调度权，拒绝启动第二个实例")
                owner.status = "STOPPING"
            heartbeat = db.get(SchedulerHeartbeatModel, self.scheduler_id)
            if heartbeat is None:
                db.add(
                    SchedulerHeartbeatModel(
                        scheduler_id=self.scheduler_id,
                        instance_token=self.instance_token,
                        process_id=os.getpid(),
                        status="ACTIVE",
                        started_at=now,
                        heartbeat_at=now,
                    )
                )
            else:
                heartbeat.instance_token = self.instance_token
                heartbeat.process_id = os.getpid()
                heartbeat.status = "ACTIVE"
                heartbeat.started_at = now
                heartbeat.heartbeat_at = now
        self._started = True
        self._last_heartbeat_monotonic = time.monotonic()

    def tick(self) -> int:
        if not self._started:
            self.start()
        config = self.settings.scheduler()
        self._heartbeat_if_due(config.heartbeat_seconds)
        now_monotonic = time.monotonic()
        if now_monotonic >= self._next_timezone_reconcile_monotonic:
            changed = self.schedules.reconcile_timezone()
            if changed:
                logger.info("系统时区变更后已重算 %s 个定时任务", changed)
            self._next_timezone_reconcile_monotonic = now_monotonic + 60
        handled = 0
        if self._shutdown_requested:
            return handled
        for task_id in self.schedules.due_ids(limit=100):
            if self._shutdown_requested:
                break
            try:
                result = self.schedules.handle_due(task_id)
            except Exception:
                logger.exception("定时任务 %s 处理失败，将保留到下一轮重试", task_id)
                continue
            if result is not None:
                handled += 1
                logger.info(
                    "定时任务 %s 已处理：%s，request_id=%s",
                    task_id,
                    result["lastOutcome"],
                    result["lastRunRequestId"] or "-",
                )
        return handled

    def run_forever(self) -> None:
        self.start()
        try:
            while not self._shutdown_requested:
                self.tick()
                time.sleep(self.settings.scheduler().poll_interval_seconds)
        finally:
            self.shutdown()

    def request_shutdown(self) -> None:
        self._shutdown_requested = True

    def shutdown(self) -> None:
        if not self._started:
            return
        self._shutdown_requested = True
        with self.database.session() as db:
            heartbeat = db.get(SchedulerHeartbeatModel, self.scheduler_id)
            if heartbeat is not None and heartbeat.instance_token == self.instance_token:
                heartbeat.status = "STOPPING"
                heartbeat.heartbeat_at = self.clock.now()
        self._started = False

    def _heartbeat_if_due(self, interval_seconds: int) -> None:
        current = time.monotonic()
        if current - self._last_heartbeat_monotonic < interval_seconds:
            return
        with self.database.session() as db:
            heartbeat = db.get(SchedulerHeartbeatModel, self.scheduler_id)
            if heartbeat is None or heartbeat.instance_token != self.instance_token:
                raise SchedulerAlreadyActive("Scheduler 调度权已经丢失")
            heartbeat.status = "ACTIVE"
            heartbeat.heartbeat_at = self.clock.now()
        self._last_heartbeat_monotonic = current

    @staticmethod
    def _pid_is_alive(process_id: int) -> bool:
        if process_id <= 0:
            return False
        try:
            os.kill(process_id, 0)
        except OSError:
            return False
        return True
