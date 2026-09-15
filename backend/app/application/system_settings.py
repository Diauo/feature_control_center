from __future__ import annotations

import ipaddress
import json
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.application.audit import RequestMetadata, add_audit
from app.application.auth import AuthContext, AuthService
from app.application.errors import ConflictError
from app.application.settings import SettingsService
from app.domain.report_limits import MAX_REPORT_MAX_ITEMS, MIN_REPORT_MAX_ITEMS
from app.domain.time import Clock
from app.infrastructure.database import Database
from app.infrastructure.models import SystemSettingModel


class SystemSettingsService:
    _EDITABLE_KEYS = {
        "system.name",
        "system.timezone",
        "security.session_idle_seconds",
        "security.session_absolute_seconds",
        "security.reauth_seconds",
        "security.max_sessions_per_user",
        "security.trusted_proxy_cidrs",
        "security.management_network_mode",
        "security.management_trusted_cidrs",
        "feature.package_max_bytes",
        "feature.package_max_entries",
        "feature.package_max_entry_bytes",
        "feature.package_max_total_bytes",
        "feature.package_max_compression_ratio",
        "feature.allowed_package_formats",
        "feature.data_source_max_bytes",
        "dependencies.index_url",
        "dependencies.download_timeout_seconds",
        "dependencies.offline_mode",
        "dependencies.cache_max_bytes",
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
        "logs.retention_days",
        "system_logs.retention_days",
        "system_logs.max_total_bytes",
        "updates.max_package_bytes",
        "scheduler.poll_interval_seconds",
        "scheduler.heartbeat_seconds",
        "scheduler.stale_after_seconds",
        "scheduler.misfire_grace_seconds",
    }

    def __init__(self, database: Database, settings: SettingsService, auth: AuthService, clock: Clock) -> None:
        self.database = database
        self.settings = settings
        self.auth = auth
        self.clock = clock

    def read(
        self,
        client_ip: str,
        actor: AuthContext | None = None,
        request: RequestMetadata | None = None,
    ) -> dict[str, Any]:
        values = {key: self.settings.get(key) for key in self._EDITABLE_KEYS}
        address = ipaddress.ip_address(client_ip)
        values["request.client_ip"] = str(address)
        values["request.suggested_cidr"] = f"{address}/{address.max_prefixlen}"
        if actor is not None and request is not None:
            with self.database.session() as db:
                add_audit(
                    db,
                    now=self.clock.now(),
                    request=request,
                    action="admin.settings.view",
                    outcome="success",
                    actor_user_id=actor.user_id,
                    session_id=actor.session_id,
                    target_type="system_settings",
                    target_id="platform",
                    details={"settingCount": len(self._EDITABLE_KEYS)},
                )
        return values

    def update(
        self,
        *,
        actor: AuthContext,
        values: dict[str, Any],
        client_ip: str,
        request: RequestMetadata,
    ) -> dict[str, Any]:
        self.auth.require_recent_auth(actor)
        unknown = set(values) - self._EDITABLE_KEYS
        if unknown:
            raise ConflictError("UNKNOWN_SETTING", f"包含不支持的系统设置：{', '.join(sorted(unknown))}")
        current = self.read(client_ip)
        normalized = dict(current)
        normalized.pop("request.client_ip", None)
        normalized.pop("request.suggested_cidr", None)
        normalized.update(values)
        normalized["system.name"] = self._system_name(normalized["system.name"])
        normalized["system.timezone"] = self._timezone(normalized["system.timezone"])
        normalized["security.trusted_proxy_cidrs"] = self._cidrs(
            normalized["security.trusted_proxy_cidrs"], "可信代理"
        )
        normalized["security.management_trusted_cidrs"] = self._cidrs(
            normalized["security.management_trusted_cidrs"], "管理区可信网络"
        )
        mode = normalized["security.management_network_mode"]
        if mode not in {"ACCOUNT_ONLY", "TRUSTED_NETWORKS"}:
            raise ConflictError("INVALID_NETWORK_MODE", "管理区网络模式无效")
        old_proxy = current["security.trusted_proxy_cidrs"]
        if (
            mode == "TRUSTED_NETWORKS"
            and current["security.management_network_mode"] != "TRUSTED_NETWORKS"
            and normalized["security.trusted_proxy_cidrs"] != old_proxy
        ):
            raise ConflictError(
                "CONFIGURE_PROXY_FIRST",
                "请先单独保存可信代理，确认识别出的客户端地址正确后，再启用管理区可信网络",
                status=409,
            )
        address = ipaddress.ip_address(client_ip)
        management_networks = [ipaddress.ip_network(item) for item in normalized["security.management_trusted_cidrs"]]
        if mode == "TRUSTED_NETWORKS" and not any(address in network for network in management_networks):
            raise ConflictError(
                "NETWORK_LOCKOUT_PREVENTED",
                "当前客户端地址不在新的可信网络中，系统已阻止可能导致管理区锁死的设置",
                status=409,
                details={"clientIp": str(address), "suggestedCidr": f"{address}/{address.max_prefixlen}"},
            )
        normalized["dependencies.index_url"] = self._index_url(normalized["dependencies.index_url"])
        normalized["dependencies.offline_mode"] = self._boolean(
            normalized["dependencies.offline_mode"], "离线模式"
        )
        normalized["feature.allowed_package_formats"] = self._package_formats(
            normalized["feature.allowed_package_formats"]
        )
        integer_rules = {
            "security.session_idle_seconds": (900, 604_800),
            "security.session_absolute_seconds": (3_600, 604_800),
            "security.reauth_seconds": (60, 3_600),
            "security.max_sessions_per_user": (1, 20),
            "feature.package_max_bytes": (1_048_576, 524_288_000),
            "feature.package_max_entries": (10, 10_000),
            "feature.package_max_entry_bytes": (1_048_576, 524_288_000),
            "feature.package_max_total_bytes": (1_048_576, 2_147_483_648),
            "feature.package_max_compression_ratio": (2, 1_000),
            "feature.data_source_max_bytes": (1_024, 524_288_000),
            "dependencies.download_timeout_seconds": (30, 3_600),
            "dependencies.cache_max_bytes": (104_857_600, 21_474_836_480),
            "runner.max_concurrency": (1, 16),
            "runner.poll_interval_ms": (100, 5_000),
            "runner.heartbeat_seconds": (1, 60),
            "runner.stale_after_seconds": (3, 600),
            "runner.stop_grace_seconds": (1, 300),
            "runner.log_batch_size": (1, 500),
            "runner.log_flush_ms": (50, 5_000),
            "runner.max_event_bytes": (1_024, 262_144),
            "runner.max_context_bytes": (1_024, 524_288),
            "runner.max_queued_runs": (1, 10_000),
            "runner.default_max_runtime_seconds": (0, 2_592_000),
            "runner.report_max_items": (MIN_REPORT_MAX_ITEMS, MAX_REPORT_MAX_ITEMS),
            "logs.retention_days": (0, 3_650),
            "system_logs.retention_days": (1, 3_650),
            "system_logs.max_total_bytes": (0, 1_099_511_627_776),
            "updates.max_package_bytes": (10_485_760, 2_147_483_648),
            "scheduler.poll_interval_seconds": (1, 60),
            "scheduler.heartbeat_seconds": (1, 60),
            "scheduler.stale_after_seconds": (3, 600),
            "scheduler.misfire_grace_seconds": (0, 3_600),
        }
        for key, (minimum, maximum) in integer_rules.items():
            normalized[key] = self._integer(normalized[key], key, minimum, maximum)
        if normalized["feature.package_max_total_bytes"] < normalized["feature.package_max_entry_bytes"]:
            raise ConflictError("INVALID_UPLOAD_LIMITS", "功能包解压总大小不能小于单文件大小限制")
        if normalized["runner.stale_after_seconds"] < normalized["runner.heartbeat_seconds"] * 3:
            raise ConflictError("INVALID_RUNNER_HEARTBEAT", "Runner 失联判定至少应为心跳间隔的 3 倍")
        if normalized["scheduler.stale_after_seconds"] < normalized["scheduler.heartbeat_seconds"] * 3:
            raise ConflictError("INVALID_SCHEDULER_HEARTBEAT", "Scheduler 失联判定至少应为心跳间隔的 3 倍")
        if normalized["security.session_absolute_seconds"] < normalized["security.session_idle_seconds"]:
            raise ConflictError("INVALID_SESSION_LIMITS", "会话绝对有效期不能短于闲置有效期")
        now = self.clock.now()
        changed = sorted(key for key in self._EDITABLE_KEYS if normalized[key] != current[key])
        with self.database.session() as db:
            for key in changed:
                row = db.get(SystemSettingModel, key)
                if row is None:
                    raise RuntimeError(f"系统设置 {key} 缺失")
                row.value_json = json.dumps(normalized[key], ensure_ascii=False, separators=(",", ":"))
                row.updated_at = now
                row.updated_by = actor.user_id
            add_audit(
                db,
                now=now,
                request=request,
                action="admin.settings.update",
                outcome="success",
                actor_user_id=actor.user_id,
                session_id=actor.session_id,
                target_type="system_settings",
                target_id="platform",
                details={"changedKeys": changed},
            )
        return self.read(client_ip)

    @staticmethod
    def _cidrs(value: object, label: str) -> list[str]:
        if not isinstance(value, list) or len(value) > 100:
            raise ConflictError("INVALID_CIDRS", f"{label}必须是最多 100 项的 CIDR 列表")
        result: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ConflictError("INVALID_CIDRS", f"{label}包含无效值")
            try:
                normalized = str(ipaddress.ip_network(item.strip(), strict=True))
            except ValueError as exc:
                raise ConflictError("INVALID_CIDRS", f"{label}中的 {item!r} 不是规范 CIDR") from exc
            if normalized not in result:
                result.append(normalized)
        return result

    @staticmethod
    def _index_url(value: object) -> str:
        if not isinstance(value, str) or len(value) > 500:
            raise ConflictError("INVALID_INDEX_URL", "依赖源地址无效")
        parsed = urlsplit(value.strip())
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ConflictError("INVALID_INDEX_URL", "依赖源必须是不含凭据、查询参数的 HTTPS 地址")
        return value.strip().rstrip("/")

    @staticmethod
    def _system_name(value: object) -> str:
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 80:
            raise ConflictError("INVALID_SYSTEM_NAME", "系统名称必须是 1 到 80 个字符")
        return value.strip()

    @staticmethod
    def _timezone(value: object) -> str:
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 80:
            raise ConflictError("INVALID_TIMEZONE", "时区名称无效")
        normalized = value.strip()
        try:
            ZoneInfo(normalized)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ConflictError("INVALID_TIMEZONE", "请输入有效的 IANA 时区，例如 Asia/Hong_Kong") from exc
        return normalized

    @staticmethod
    def _integer(value: object, label: str, minimum: int, maximum: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ConflictError("INVALID_SETTING_VALUE", f"设置 {label} 必须在 {minimum} 到 {maximum} 之间")
        return value

    @staticmethod
    def _boolean(value: object, label: str) -> bool:
        if not isinstance(value, bool):
            raise ConflictError("INVALID_SETTING_VALUE", f"{label}必须是布尔值")
        return value

    @staticmethod
    def _package_formats(value: object) -> list[str]:
        supported = ("zip", "7z", "rar", "tar", "tar_gz", "tar_bz2", "tar_xz")
        if not isinstance(value, list) or not value:
            raise ConflictError("INVALID_PACKAGE_FORMATS", "至少需要启用一种功能包格式")
        if any(not isinstance(item, str) or item not in supported for item in value):
            raise ConflictError("INVALID_PACKAGE_FORMATS", "功能包格式设置包含不支持的值")
        return [item for item in supported if item in value]
