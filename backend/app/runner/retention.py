from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select, update

from app.application.runs import TERMINAL_RUN_STATUSES
from app.application.settings import SettingsService
from app.domain.time import Clock
from app.infrastructure.database import Database
from app.infrastructure.models import RunEventModel, RunModel, RunReportItemModel, RunReportModel
from app.infrastructure.paths import AppPaths


@dataclass(frozen=True, slots=True)
class LogPurgeResult:
    retention_days: int
    purged_runs: int
    deleted_events: int
    has_more: bool


@dataclass(frozen=True, slots=True)
class SystemLogPurgeResult:
    retention_days: int
    deleted_files: int
    deleted_bytes: int


class SystemLogRetentionCleaner:
    """Prunes closed daily JSONL files; the active UTC-day file is never removed."""

    def __init__(self, paths: AppPaths, settings: SettingsService, clock: Clock) -> None:
        self.paths = paths
        self.settings = settings
        self.clock = clock

    def purge(self) -> SystemLogPurgeResult:
        settings = self.settings.system_logs()
        today = datetime.fromtimestamp(self.clock.now(), UTC).date()
        cutoff = today - timedelta(days=settings.retention_days)
        deleted_files = 0
        deleted_bytes = 0
        for path in self.paths.system_logs.glob("*/*.jsonl"):
            try:
                file_date = datetime.strptime(path.stem, "%Y-%m-%d")
                size = path.stat().st_size
            except (ValueError, OSError):
                continue
            if file_date.date() >= today:
                continue
            if file_date.date() <= cutoff:
                try:
                    path.unlink()
                except OSError:
                    continue
                deleted_files += 1
                deleted_bytes += size
                continue
        max_total = settings.max_total_bytes
        if max_total > 0:
            live_files: list[tuple[datetime, Path, int]] = []
            total = 0
            for path in self.paths.system_logs.glob("*/*.jsonl"):
                try:
                    file_date = datetime.strptime(path.stem, "%Y-%m-%d")
                    size = path.stat().st_size
                except (ValueError, OSError):
                    continue
                total += size
                if file_date.date() < today:
                    live_files.append((file_date, path, size))
            for _, path, size in sorted(live_files, key=lambda item: (item[0], str(item[1]))):
                if total <= max_total:
                    break
                try:
                    path.unlink()
                except OSError:
                    continue
                total -= size
                deleted_files += 1
                deleted_bytes += size
        return SystemLogPurgeResult(settings.retention_days, deleted_files, deleted_bytes)


class RunLogRetentionCleaner:
    """Deletes terminal-run events in short transactions and keeps their summary rows."""

    _SECONDS_PER_DAY = 86_400
    _BATCH_SIZE = 200

    def __init__(self, database: Database, settings: SettingsService, clock: Clock) -> None:
        self.database = database
        self.settings = settings
        self.clock = clock

    def purge_batch(self) -> LogPurgeResult:
        retention_days = self.settings.logs().retention_days
        if retention_days == 0:
            return LogPurgeResult(retention_days=0, purged_runs=0, deleted_events=0, has_more=False)

        now = self.clock.now()
        cutoff = now - retention_days * self._SECONDS_PER_DAY
        with self.database.session() as db:
            candidates = list(
                db.scalars(
                    select(RunModel.request_id)
                    .where(
                        RunModel.status.in_(TERMINAL_RUN_STATUSES),
                        RunModel.finished_at.is_not(None),
                        RunModel.finished_at <= cutoff,
                        RunModel.logs_purged_at.is_(None),
                    )
                    .order_by(RunModel.finished_at, RunModel.request_id)
                    .limit(self._BATCH_SIZE + 1)
                )
            )
            has_more = len(candidates) > self._BATCH_SIZE
            request_ids = candidates[: self._BATCH_SIZE]
            if not request_ids:
                return LogPurgeResult(
                    retention_days=retention_days,
                    purged_runs=0,
                    deleted_events=0,
                    has_more=False,
                )

            deletion = db.execute(
                delete(RunEventModel).where(RunEventModel.run_request_id.in_(request_ids))
            )
            db.execute(
                delete(RunReportItemModel).where(RunReportItemModel.run_request_id.in_(request_ids))
            )
            db.execute(
                update(RunReportModel)
                .where(
                    RunReportModel.run_request_id.in_(request_ids),
                    RunReportModel.details_purged_at.is_(None),
                )
                .values(details_purged_at=now)
            )
            db.execute(
                update(RunModel)
                .where(
                    RunModel.request_id.in_(request_ids),
                    RunModel.logs_purged_at.is_(None),
                )
                .values(logs_purged_at=now)
            )
            return LogPurgeResult(
                retention_days=retention_days,
                purged_runs=len(request_ids),
                deleted_events=max(0, deletion.rowcount or 0),
                has_more=has_more,
            )
