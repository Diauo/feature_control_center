from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppPaths:
    data_dir: Path

    @property
    def database(self) -> Path:
        return self.data_dir / "fcc.db"

    @property
    def instance_key(self) -> Path:
        return self.data_dir / "instance.key"

    @property
    def first_run_file(self) -> Path:
        return self.data_dir / "first-run.txt"

    @property
    def runtime_cache(self) -> Path:
        return self.data_dir / "runtime-cache"

    @property
    def temp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @property
    def system_logs(self) -> Path:
        return self.data_dir / "system-logs"

    @property
    def updates_dir(self) -> Path:
        return self.data_dir / "updates"

    @property
    def update_inbox(self) -> Path:
        return self.updates_dir / "inbox"

    @property
    def update_control(self) -> Path:
        return self.updates_dir / "control"

    @property
    def update_pending(self) -> Path:
        return self.update_control / "pending.json"

    @property
    def launcher_state(self) -> Path:
        return self.update_control / "launcher.json"

    @property
    def update_recovery(self) -> Path:
        return self.backups_dir / ".update-recovery.json"

    @property
    def releases_dir(self) -> Path:
        return self.data_dir / "releases"

    @property
    def current_release(self) -> Path:
        return self.releases_dir / "current.json"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    def create_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_cache.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.system_logs.mkdir(parents=True, exist_ok=True)
        self.update_inbox.mkdir(parents=True, exist_ok=True)
        self.update_control.mkdir(parents=True, exist_ok=True)
        self.releases_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
