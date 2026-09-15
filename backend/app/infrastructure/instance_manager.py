from __future__ import annotations

import base64
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select

from app.domain.report_limits import DEFAULT_REPORT_MAX_ITEMS
from app.domain.time import Clock
from app.infrastructure.database import Database
from app.infrastructure.models import BootstrapStateModel, SystemSettingModel, UserModel
from app.infrastructure.paths import AppPaths
from app.security.crypto import derive_key, digest_value


class InstanceStateError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BootstrapStatus:
    required: bool
    first_run_file: Path | None


class InstanceManager:
    _KEY_BYTES = 32
    _BOOTSTRAP_ID = 1

    def __init__(self, paths: AppPaths, clock: Clock) -> None:
        self.paths = paths
        self.clock = clock

    def prepare_key(self, database_existed: bool) -> bytes:
        self.paths.create_directories()
        if not self.paths.instance_key.exists():
            if database_existed and self.paths.database.stat().st_size > 0:
                raise InstanceStateError(
                    "检测到现有数据库，但 instance.key 缺失。请恢复正确密钥，系统不会自动覆盖。"
                )
            self._write_key_atomic(secrets.token_bytes(self._KEY_BYTES))
        return self._read_key()

    def bind_and_seed(self, database: Database, instance_key: bytes) -> None:
        now = self.clock.now()
        fingerprint = hmac.digest(derive_key(instance_key, b"instance-binding"), b"fcc-instance-v1", "sha256").hex()
        defaults: dict[str, object] = {
            "security.instance_key_fingerprint": fingerprint,
            "security.deployment_mode": "LAN_HTTP",
            "security.session_idle_seconds": 28_800,
            "security.session_absolute_seconds": 86_400,
            "security.reauth_seconds": 600,
            "security.max_sessions_per_user": 5,
            "security.trusted_proxy_cidrs": [],
            "security.management_network_mode": "ACCOUNT_ONLY",
            "security.management_trusted_cidrs": [],
            "feature.package_max_bytes": 52_428_800,
            "feature.package_max_entries": 1_000,
            "feature.package_max_entry_bytes": 52_428_800,
            "feature.package_max_total_bytes": 209_715_200,
            "feature.package_max_compression_ratio": 200,
            "feature.allowed_package_formats": ["zip", "7z", "rar", "tar", "tar_gz", "tar_bz2", "tar_xz"],
            "feature.data_source_max_bytes": 20_971_520,
            "dependencies.index_url": "https://pypi.org/simple",
            "dependencies.download_timeout_seconds": 600,
            "dependencies.offline_mode": False,
            "dependencies.cache_max_bytes": 2_147_483_648,
            "runner.max_concurrency": 2,
            "runner.poll_interval_ms": 300,
            "runner.heartbeat_seconds": 5,
            "runner.stale_after_seconds": 30,
            "runner.stop_grace_seconds": 10,
            "runner.log_batch_size": 50,
            "runner.log_flush_ms": 200,
            "runner.max_event_bytes": 16_384,
            "runner.max_context_bytes": 32_768,
            "runner.max_queued_runs": 100,
            "runner.default_max_runtime_seconds": 0,
            "runner.report_max_items": DEFAULT_REPORT_MAX_ITEMS,
            "logs.retention_days": 180,
            "system_logs.retention_days": 180,
            "system_logs.max_total_bytes": 0,
            "updates.max_package_bytes": 524_288_000,
            "scheduler.poll_interval_seconds": 5,
            "scheduler.heartbeat_seconds": 5,
            "scheduler.stale_after_seconds": 30,
            "scheduler.misfire_grace_seconds": 60,
            "system.name": "功能控制中心",
            "system.timezone": "Asia/Hong_Kong",
        }
        with database.session() as db:
            existing = db.get(SystemSettingModel, "security.instance_key_fingerprint")
            if existing is not None and json.loads(existing.value_json) != fingerprint:
                raise InstanceStateError("instance.key 与现有数据库不匹配，请恢复同一实例的密钥。")
            for key, value in defaults.items():
                if db.get(SystemSettingModel, key) is None:
                    db.add(
                        SystemSettingModel(
                            key=key,
                            value_json=json.dumps(value, ensure_ascii=False),
                            updated_at=now,
                            updated_by=None,
                        )
                    )

    def ensure_bootstrap(self, database: Database, instance_key: bytes, public_url: str) -> BootstrapStatus:
        with database.session() as db:
            user_count = db.scalar(select(func.count(UserModel.id))) or 0
            if user_count > 0:
                self.paths.first_run_file.unlink(missing_ok=True)
                return BootstrapStatus(required=False, first_run_file=None)

            state = db.get(BootstrapStateModel, self._BOOTSTRAP_ID)
            token = self._read_bootstrap_token_from_file()
            digest_key = derive_key(instance_key, b"bootstrap-token")
            if token is not None and state is not None and state.used_at is None:
                if hmac.compare_digest(state.token_digest, digest_value(digest_key, token)):
                    return BootstrapStatus(required=True, first_run_file=self.paths.first_run_file)

            token = base64.urlsafe_b64encode(secrets.token_bytes(18)).rstrip(b"=").decode("ascii")
            token_digest = digest_value(digest_key, token)
            if state is None:
                state = BootstrapStateModel(
                    id=self._BOOTSTRAP_ID,
                    token_digest=token_digest,
                    created_at=self.clock.now(),
                    used_at=None,
                )
                db.add(state)
            else:
                state.token_digest = token_digest
                state.created_at = self.clock.now()
                state.used_at = None
            self._write_bootstrap_file(token, public_url)
            return BootstrapStatus(required=True, first_run_file=self.paths.first_run_file)

    def bootstrap_digest(self, instance_key: bytes, token: str) -> bytes:
        return digest_value(derive_key(instance_key, b"bootstrap-token"), token)

    def mark_bootstrap_file_consumed(self) -> None:
        self.paths.first_run_file.unlink(missing_ok=True)

    def _read_key(self) -> bytes:
        try:
            encoded = self.paths.instance_key.read_text(encoding="ascii").strip()
            value = base64.urlsafe_b64decode(encoded.encode("ascii"))
        except (OSError, ValueError) as exc:
            raise InstanceStateError("instance.key 无法读取或格式错误。") from exc
        if len(value) != self._KEY_BYTES:
            raise InstanceStateError("instance.key 长度错误。")
        return value

    def _write_key_atomic(self, value: bytes) -> None:
        encoded = base64.urlsafe_b64encode(value).decode("ascii")
        temp = self.paths.instance_key.with_suffix(".key.tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            descriptor = os.open(temp, flags, 0o600)
        except FileExistsError:
            temp.unlink(missing_ok=True)
            descriptor = os.open(temp, flags, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as handle:
                handle.write(encoded + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self.paths.instance_key)
            try:
                os.chmod(self.paths.instance_key, 0o600)
            except OSError:
                pass
        finally:
            temp.unlink(missing_ok=True)

    def _write_bootstrap_file(self, token: str, public_url: str) -> None:
        text = (
            "功能控制中心首次初始化\n"
            "========================\n\n"
            f"访问地址：{public_url.rstrip('/')}/setup\n"
            f"初始化码：{token}\n\n"
            "创建第一个管理员后，本文件会自动删除。请勿将初始化码发送给无关人员。\n"
        )
        temp = self.paths.first_run_file.with_suffix(".txt.tmp")
        temp.write_text(text, encoding="utf-8", newline="\n")
        try:
            os.chmod(temp, 0o600)
        except OSError:
            pass
        os.replace(temp, self.paths.first_run_file)

    def _read_bootstrap_token_from_file(self) -> str | None:
        try:
            for line in self.paths.first_run_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("初始化码："):
                    return line.removeprefix("初始化码：").strip()
        except OSError:
            return None
        return None
