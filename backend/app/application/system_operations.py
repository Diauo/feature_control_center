from __future__ import annotations

import base64
import binascii
import hashlib
import importlib.metadata
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from sqlalchemy import func, select

from app.application.audit import RequestMetadata, add_audit
from app.application.auth import AuthContext
from app.application.errors import ConflictError
from app.application.settings import SettingsService
from app.domain.time import Clock
from app.infrastructure.database import Database
from app.infrastructure.models import RunModel, RunnerHeartbeatModel, SchedulerHeartbeatModel
from app.infrastructure.paths import AppPaths


SYSTEM_LOG_SERVICES = ("web", "runner", "scheduler", "launcher")
SYSTEM_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


@dataclass(frozen=True, slots=True)
class DownloadedSystemLog:
    filename: str
    content: bytes
    sha256: str


class SystemOperationsService:
    def __init__(self, database: Database, settings: SettingsService, paths: AppPaths, clock: Clock) -> None:
        self.database = database
        self.settings = settings
        self.paths = paths
        self.clock = clock
        self.started_at = clock.now()

    def status(self) -> dict[str, Any]:
        now = self.clock.now()
        runner_stale = self.settings.runner().stale_after_seconds
        scheduler_stale = self.settings.scheduler().stale_after_seconds
        with self.database.session() as db:
            runner = db.scalar(select(RunnerHeartbeatModel).order_by(RunnerHeartbeatModel.heartbeat_at.desc()))
            scheduler = db.scalar(
                select(SchedulerHeartbeatModel).order_by(SchedulerHeartbeatModel.heartbeat_at.desc())
            )
            active_runs = db.scalar(
                select(func.count(RunModel.request_id)).where(
                    RunModel.status.in_({"QUEUED", "STARTING", "RUNNING", "STOPPING"})
                )
            ) or 0
        return {
            "version": self.version(),
            "serverTime": now,
            "configuredTimezone": self.settings.timezone_name(),
            "activeRuns": active_runs,
            "services": [
                {"name": "web", "status": "ACTIVE", "heartbeatAt": now, "startedAt": self.started_at},
                self._heartbeat_status("runner", runner, now, runner_stale),
                self._heartbeat_status("scheduler", scheduler, now, scheduler_stale),
            ],
        }

    def timezone_catalogue(self) -> dict[str, Any]:
        return {
            "items": sorted(available_timezones()),
            "serverDetected": self._server_timezone(),
            "configured": self.settings.timezone_name(),
        }

    def release_history(self) -> list[dict[str, Any]]:
        path = Path(__file__).parents[1] / "release_history.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return value if isinstance(value, list) else []

    def list_logs(
        self,
        *,
        service: str,
        date: str,
        level: str,
        limit: int,
        cursor: str,
    ) -> dict[str, Any]:
        services = SYSTEM_LOG_SERVICES if service == "all" else (self._service(service),)
        safe_date = self._date(date)
        safe_level = level.upper()
        if safe_level and safe_level not in SYSTEM_LOG_LEVELS:
            raise ConflictError("INVALID_LOG_LEVEL", "程序日志级别无效", status=400)
        offsets = self._decode_cursor(cursor)
        next_offsets: dict[str, int] = {}
        entries: list[dict[str, Any]] = []
        for service_name in services:
            path = self.paths.system_logs / service_name / f"{safe_date}.jsonl"
            if not path.is_file():
                next_offsets[service_name] = 0
                continue
            size = path.stat().st_size
            requested_offset = offsets.get(service_name)
            start = max(0, size - 524_288) if requested_offset is None else min(requested_offset, size)
            with path.open("rb") as handle:
                handle.seek(start)
                if start:
                    handle.readline()
                data = handle.read(1_048_576)
                next_offsets[service_name] = handle.tell()
            for raw_line in data.splitlines():
                try:
                    item = json.loads(raw_line)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if not isinstance(item, dict) or (safe_level and item.get("level") != safe_level):
                    continue
                entries.append(item)
        entries.sort(key=lambda item: str(item.get("timestamp", "")))
        safe_limit = max(1, min(500, limit))
        return {
            "items": entries[-safe_limit:],
            "cursor": self._encode_cursor(next_offsets),
            "date": safe_date,
        }

    def download_log(
        self,
        *,
        actor: AuthContext,
        service: str,
        date: str,
        request: RequestMetadata,
    ) -> DownloadedSystemLog:
        service = self._service(service)
        date = self._date(date)
        path = self.paths.system_logs / service / f"{date}.jsonl"
        if not path.is_file():
            raise ConflictError("SYSTEM_LOG_NOT_FOUND", "指定日期没有程序日志", status=404)
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        with self.database.session() as db:
            add_audit(
                db,
                now=self.clock.now(),
                request=request,
                action="admin.system_log.download",
                outcome="success",
                actor_user_id=actor.user_id,
                session_id=actor.session_id,
                target_type="system_log",
                target_id=f"{service}:{date}",
                target_name=f"{service} · {date}",
                details={"service": service, "date": date, "size": len(content), "sha256": digest},
            )
        return DownloadedSystemLog(f"{service}-{date}.jsonl", content, digest)

    @staticmethod
    def _heartbeat_status(name: str, row: Any, now: int, stale_after: int) -> dict[str, Any]:
        if row is None:
            return {"name": name, "status": "OFFLINE", "heartbeatAt": None, "startedAt": None}
        healthy = row.status == "ACTIVE" and row.heartbeat_at >= now - stale_after
        return {
            "name": name,
            "status": "ACTIVE" if healthy else "OFFLINE",
            "heartbeatAt": row.heartbeat_at,
            "startedAt": row.started_at,
            "processId": row.process_id,
        }

    def version(self) -> str:
        managed_version = os.environ.get("FCC_ACTIVE_VERSION", "").strip()
        if managed_version:
            return managed_version[:32]
        history = self.release_history()
        if history and isinstance(history[0].get("version"), str):
            return str(history[0]["version"])
        try:
            return importlib.metadata.version("feature-control-center")
        except importlib.metadata.PackageNotFoundError:
            return "2.4.0"

    @staticmethod
    def _server_timezone() -> str:
        candidates: list[str] = []
        try:
            candidates.append(Path("/etc/timezone").read_text(encoding="utf-8").strip())
        except OSError:
            pass
        try:
            resolved = Path("/etc/localtime").resolve().as_posix()
            if "/zoneinfo/" in resolved:
                candidates.append(resolved.split("/zoneinfo/", 1)[1])
        except OSError:
            pass
        local_zone = datetime.now().astimezone().tzinfo
        if local_zone is not None and hasattr(local_zone, "key"):
            candidates.append(str(local_zone.key))
        for candidate in candidates:
            try:
                ZoneInfo(candidate)
                return candidate
            except (ZoneInfoNotFoundError, ValueError):
                continue
        return ""

    @staticmethod
    def _service(value: str) -> str:
        if value not in SYSTEM_LOG_SERVICES:
            raise ConflictError("INVALID_LOG_SERVICE", "程序日志服务无效", status=400)
        return value

    @staticmethod
    def _date(value: str) -> str:
        normalized = value or datetime.now(UTC).strftime("%Y-%m-%d")
        try:
            parsed = datetime.strptime(normalized, "%Y-%m-%d")
        except ValueError as exc:
            raise ConflictError("INVALID_LOG_DATE", "程序日志日期无效", status=400) from exc
        if parsed.year < 2020 or parsed.year > 2200:
            raise ConflictError("INVALID_LOG_DATE", "程序日志日期超出允许范围", status=400)
        return normalized

    @staticmethod
    def _decode_cursor(value: str) -> dict[str, int]:
        if not value:
            return {}
        try:
            padding = "=" * (-len(value) % 4)
            decoded = json.loads(base64.urlsafe_b64decode(value + padding))
            if not isinstance(decoded, dict):
                return {}
            return {
                key: position
                for key, position in decoded.items()
                if key in SYSTEM_LOG_SERVICES and isinstance(position, int) and position >= 0
            }
        except (ValueError, binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _encode_cursor(offsets: dict[str, int]) -> str:
        raw = json.dumps(offsets, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
