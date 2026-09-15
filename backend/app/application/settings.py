from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from app.domain.report_limits import (
    DEFAULT_REPORT_MAX_ITEMS,
    MAX_REPORT_MAX_ITEMS,
    MIN_REPORT_MAX_ITEMS,
)
from app.infrastructure.database import Database
from app.infrastructure.models import SystemSettingModel
from app.infrastructure.package_inspector import PackageLimits
from app.infrastructure.runtime_environment import DependencySettings


@dataclass(frozen=True, slots=True)
class SecuritySettings:
    deployment_mode: str
    idle_seconds: int
    absolute_seconds: int
    reauth_seconds: int
    max_sessions: int


@dataclass(frozen=True, slots=True)
class ManagementNetworkSettings:
    mode: str
    trusted_cidrs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RunnerSettings:
    max_concurrency: int
    poll_interval_ms: int
    heartbeat_seconds: int
    stale_after_seconds: int
    stop_grace_seconds: int
    log_batch_size: int
    log_flush_ms: int
    max_event_bytes: int
    max_context_bytes: int
    max_queued_runs: int
    default_max_runtime_seconds: int
    report_max_items: int


@dataclass(frozen=True, slots=True)
class LogSettings:
    retention_days: int


@dataclass(frozen=True, slots=True)
class SystemLogSettings:
    retention_days: int
    max_total_bytes: int


@dataclass(frozen=True, slots=True)
class SchedulerSettings:
    poll_interval_seconds: int
    heartbeat_seconds: int
    stale_after_seconds: int
    misfire_grace_seconds: int


class SettingsService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get(self, key: str, default: Any = None) -> Any:
        with self.database.session() as db:
            setting = db.get(SystemSettingModel, key)
            return default if setting is None else json.loads(setting.value_json)

    def security(self) -> SecuritySettings:
        keys = {
            "security.deployment_mode",
            "security.session_idle_seconds",
            "security.session_absolute_seconds",
            "security.reauth_seconds",
            "security.max_sessions_per_user",
        }
        with self.database.session() as db:
            values = {
                setting.key: json.loads(setting.value_json)
                for setting in db.scalars(select(SystemSettingModel).where(SystemSettingModel.key.in_(keys)))
            }
        return SecuritySettings(
            deployment_mode=str(values.get("security.deployment_mode", "LAN_HTTP")),
            idle_seconds=self._bounded_value(values.get("security.session_idle_seconds"), 28_800, 900, 604_800),
            absolute_seconds=self._bounded_value(
                values.get("security.session_absolute_seconds"), 86_400, 3_600, 604_800
            ),
            reauth_seconds=self._bounded_value(values.get("security.reauth_seconds"), 600, 60, 3_600),
            max_sessions=self._bounded_value(values.get("security.max_sessions_per_user"), 5, 1, 20),
        )

    def system_name(self) -> str:
        return str(self.get("system.name", "功能控制中心"))

    def timezone_name(self) -> str:
        return str(self.get("system.timezone", "Asia/Hong_Kong"))

    def management_network(self) -> ManagementNetworkSettings:
        values = self._many({"security.management_network_mode", "security.management_trusted_cidrs"})
        mode = str(values.get("security.management_network_mode", "ACCOUNT_ONLY"))
        cidrs = values.get("security.management_trusted_cidrs", [])
        return ManagementNetworkSettings(
            mode=mode if mode in {"ACCOUNT_ONLY", "TRUSTED_NETWORKS"} else "ACCOUNT_ONLY",
            trusted_cidrs=tuple(str(item) for item in cidrs) if isinstance(cidrs, list) else (),
        )

    def package_limits(self) -> PackageLimits:
        values = self._many(
            {
                "feature.package_max_bytes",
                "feature.package_max_entries",
                "feature.package_max_entry_bytes",
                "feature.package_max_total_bytes",
                "feature.package_max_compression_ratio",
            }
        )
        return PackageLimits(
            max_package_bytes=self._bounded_value(values.get("feature.package_max_bytes"), 52_428_800, 1_048_576, 524_288_000),
            max_entries=self._bounded_value(values.get("feature.package_max_entries"), 1_000, 10, 10_000),
            max_entry_bytes=self._bounded_value(values.get("feature.package_max_entry_bytes"), 52_428_800, 1_048_576, 524_288_000),
            max_total_bytes=self._bounded_value(values.get("feature.package_max_total_bytes"), 209_715_200, 1_048_576, 2_147_483_648),
            max_compression_ratio=self._bounded_value(values.get("feature.package_max_compression_ratio"), 200, 2, 1_000),
        )

    def data_source_max_bytes(self) -> int:
        return self._bounded_value(self.get("feature.data_source_max_bytes"), 20_971_520, 1_024, 524_288_000)

    def update_package_max_bytes(self) -> int:
        return self._bounded_value(
            self.get("updates.max_package_bytes"),
            524_288_000,
            10_485_760,
            2_147_483_648,
        )

    def allowed_package_formats(self) -> tuple[str, ...]:
        supported = ("zip", "7z", "rar", "tar", "tar_gz", "tar_bz2", "tar_xz")
        configured = self.get("feature.allowed_package_formats", list(supported))
        if not isinstance(configured, list):
            return supported
        result = tuple(item for item in supported if item in configured)
        return result or supported

    def dependencies(self) -> DependencySettings:
        values = self._many(
            {
                "dependencies.index_url",
                "dependencies.download_timeout_seconds",
                "dependencies.offline_mode",
                "dependencies.cache_max_bytes",
            }
        )
        offline = values.get("dependencies.offline_mode", False)
        return DependencySettings(
            index_url=str(values.get("dependencies.index_url", "https://pypi.org/simple")),
            timeout_seconds=self._bounded_value(values.get("dependencies.download_timeout_seconds"), 600, 30, 3_600),
            offline_mode=offline if isinstance(offline, bool) else False,
            cache_max_bytes=self._bounded_value(values.get("dependencies.cache_max_bytes"), 2_147_483_648, 104_857_600, 21_474_836_480),
        )

    def runner(self) -> RunnerSettings:
        keys = {
            "runner.max_concurrency",
            "runner.poll_interval_ms",
            "runner.heartbeat_seconds",
            "runner.stale_after_seconds",
            "runner.stop_grace_seconds",
            "runner.log_batch_size",
            "runner.log_flush_ms",
            "runner.max_event_bytes",
            "runner.max_context_bytes",
            "runner.max_queued_runs",
            "runner.default_max_runtime_seconds",
            "runner.report_max_items",
        }
        values = self._many(keys)
        heartbeat = self._bounded_value(values.get("runner.heartbeat_seconds"), 5, 1, 60)
        return RunnerSettings(
            max_concurrency=self._bounded_value(values.get("runner.max_concurrency"), 2, 1, 16),
            poll_interval_ms=self._bounded_value(values.get("runner.poll_interval_ms"), 300, 100, 5_000),
            heartbeat_seconds=heartbeat,
            stale_after_seconds=self._bounded_value(
                values.get("runner.stale_after_seconds"), 30, heartbeat * 3, 600
            ),
            stop_grace_seconds=self._bounded_value(values.get("runner.stop_grace_seconds"), 10, 1, 300),
            log_batch_size=self._bounded_value(values.get("runner.log_batch_size"), 50, 1, 500),
            log_flush_ms=self._bounded_value(values.get("runner.log_flush_ms"), 200, 50, 5_000),
            max_event_bytes=self._bounded_value(values.get("runner.max_event_bytes"), 16_384, 1_024, 262_144),
            max_context_bytes=self._bounded_value(values.get("runner.max_context_bytes"), 32_768, 1_024, 524_288),
            max_queued_runs=self._bounded_value(values.get("runner.max_queued_runs"), 100, 1, 10_000),
            default_max_runtime_seconds=self._bounded_value(
                values.get("runner.default_max_runtime_seconds"), 0, 0, 2_592_000
            ),
            report_max_items=self._bounded_value(
                values.get("runner.report_max_items"),
                DEFAULT_REPORT_MAX_ITEMS,
                MIN_REPORT_MAX_ITEMS,
                MAX_REPORT_MAX_ITEMS,
            ),
        )

    def logs(self) -> LogSettings:
        return LogSettings(
            retention_days=self._bounded_value(self.get("logs.retention_days"), 180, 0, 3_650),
        )

    def system_logs(self) -> SystemLogSettings:
        values = self._many({"system_logs.retention_days", "system_logs.max_total_bytes"})
        return SystemLogSettings(
            retention_days=self._bounded_value(values.get("system_logs.retention_days"), 180, 1, 3_650),
            max_total_bytes=self._bounded_value(
                values.get("system_logs.max_total_bytes"), 0, 0, 1_099_511_627_776
            ),
        )

    def scheduler(self) -> SchedulerSettings:
        values = self._many(
            {
                "scheduler.poll_interval_seconds",
                "scheduler.heartbeat_seconds",
                "scheduler.stale_after_seconds",
                "scheduler.misfire_grace_seconds",
            }
        )
        heartbeat = self._bounded_value(values.get("scheduler.heartbeat_seconds"), 5, 1, 60)
        return SchedulerSettings(
            poll_interval_seconds=self._bounded_value(
                values.get("scheduler.poll_interval_seconds"), 5, 1, 60
            ),
            heartbeat_seconds=heartbeat,
            stale_after_seconds=self._bounded_value(
                values.get("scheduler.stale_after_seconds"), 30, heartbeat * 3, 600
            ),
            misfire_grace_seconds=self._bounded_value(
                values.get("scheduler.misfire_grace_seconds"), 60, 0, 3_600
            ),
        )

    def _many(self, keys: set[str]) -> dict[str, Any]:
        with self.database.session() as db:
            return {
                setting.key: json.loads(setting.value_json)
                for setting in db.scalars(select(SystemSettingModel).where(SystemSettingModel.key.in_(keys)))
            }

    @staticmethod
    def _bounded_value(value: Any, default: int, minimum: int, maximum: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            return default
        return max(minimum, min(maximum, value))
