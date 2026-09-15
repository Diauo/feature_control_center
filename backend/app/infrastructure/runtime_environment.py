from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import sysconfig
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

from app.infrastructure.package_inspector import PackageFile
from app.infrastructure.paths import AppPaths


@dataclass(frozen=True, slots=True)
class DependencySettings:
    index_url: str
    timeout_seconds: int
    offline_mode: bool
    cache_max_bytes: int


@dataclass(frozen=True, slots=True)
class EnvironmentBuildResult:
    resolved_fingerprint: str
    resolved_lock_text: str
    wheel_manifest: tuple[dict[str, object], ...]
    environment_path: str


class RuntimeEnvironmentBuilder(Protocol):
    def build(
        self,
        request_fingerprint: str,
        requirements_text: str,
        offline_wheels: tuple[PackageFile, ...],
        settings: DependencySettings,
    ) -> EnvironmentBuildResult: ...


class EnvironmentBuildError(RuntimeError):
    pass


def dependency_request_fingerprint(requirements_text: str, wheels: tuple[PackageFile, ...]) -> str:
    payload = {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "platform": sysconfig.get_platform(),
        "requirements": requirements_text.splitlines(),
        "wheels": sorted(file.sha256.hex() for file in wheels),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class PipRuntimeEnvironmentBuilder:
    """Create an isolated, reusable venv without changing the platform interpreter."""

    def __init__(self, paths: AppPaths) -> None:
        self._root = paths.runtime_cache.resolve()
        self._environments = self._root / "environments"
        self._wheel_cache = self._root / "wheels"

    def build(
        self,
        request_fingerprint: str,
        requirements_text: str,
        offline_wheels: tuple[PackageFile, ...],
        settings: DependencySettings,
    ) -> EnvironmentBuildResult:
        if not requirements_text.strip():
            raise EnvironmentBuildError("空依赖不需要创建运行环境")
        self._environments.mkdir(parents=True, exist_ok=True)
        self._wheel_cache.mkdir(parents=True, exist_ok=True)
        environment_dir = (self._environments / request_fingerprint).resolve()
        if environment_dir.parent != self._environments.resolve():
            raise EnvironmentBuildError("运行环境指纹无效")
        manifest_file = environment_dir / "fcc-environment.json"
        if manifest_file.is_file():
            return self._read_existing(manifest_file, environment_dir)
        if environment_dir.exists():
            shutil.rmtree(environment_dir)
        environment_dir.mkdir(mode=0o700)
        wheelhouse = environment_dir / "wheelhouse"
        wheelhouse.mkdir()
        requirements_file = environment_dir / "requirements.txt"
        requirements_file.write_text(requirements_text + ("" if requirements_text.endswith("\n") else "\n"), encoding="utf-8")
        try:
            for wheel in offline_wheels:
                target = wheelhouse / Path(wheel.filename).name
                if hashlib.sha256(wheel.content).digest() != wheel.sha256:
                    raise EnvironmentBuildError(f"离线 wheel {target.name} 内容校验失败")
                target.write_bytes(wheel.content)
            self._run([sys.executable, "-m", "venv", str(environment_dir)], settings.timeout_seconds, settings.index_url)
            python = environment_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            download = [
                str(python), "-m", "pip", "download", "--disable-pip-version-check", "--no-input", "--only-binary=:all:",
                "--requirement", str(requirements_file), "--dest", str(wheelhouse), "--find-links", str(wheelhouse),
            ]
            if settings.offline_mode:
                download.append("--no-index")
            else:
                download.extend(["--index-url", settings.index_url])
            self._run(download, settings.timeout_seconds, settings.index_url)
            wheels = sorted(wheelhouse.glob("*.whl"), key=lambda item: item.name.casefold())
            if not wheels:
                raise EnvironmentBuildError("依赖解析没有产生可安装的 wheel")
            total_bytes = sum(item.stat().st_size for item in wheels)
            if total_bytes > settings.cache_max_bytes:
                raise EnvironmentBuildError("本次依赖超过系统设置的依赖缓存上限")
            install = [
                str(python), "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--no-index",
                "--find-links", str(wheelhouse), "--requirement", str(requirements_file),
            ]
            self._run(install, settings.timeout_seconds, settings.index_url)
            self._run([str(python), "-m", "pip", "check"], settings.timeout_seconds, settings.index_url)
            lock = self._run(
                [str(python), "-m", "pip", "freeze", "--all"], settings.timeout_seconds, settings.index_url
            ).strip()
            wheel_manifest = tuple(self._wheel_record(item) for item in wheels)
            resolved_payload = {
                "python": f"{sys.version_info.major}.{sys.version_info.minor}",
                "platform": sysconfig.get_platform(),
                "lock": lock.splitlines(),
                "wheels": wheel_manifest,
            }
            resolved = hashlib.sha256(
                json.dumps(resolved_payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            for wheel in wheels:
                cached = self._wheel_cache / wheel.name
                if not cached.exists():
                    shutil.copyfile(wheel, cached)
            result = EnvironmentBuildResult(resolved, lock, wheel_manifest, str(environment_dir))
            manifest_file.write_text(
                json.dumps(
                    {
                        "requestFingerprint": request_fingerprint,
                        "resolvedFingerprint": resolved,
                        "resolvedLock": lock,
                        "wheels": wheel_manifest,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            return result
        except Exception as exc:
            shutil.rmtree(environment_dir, ignore_errors=True)
            if isinstance(exc, EnvironmentBuildError):
                raise
            raise EnvironmentBuildError("依赖环境准备失败") from exc

    @staticmethod
    def _wheel_record(path: Path) -> dict[str, object]:
        return {"filename": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size": path.stat().st_size}

    @staticmethod
    def _run(command: list[str], timeout: int, index_url: str) -> str:
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env={**os.environ, "PIP_NO_INPUT": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PYTHONNOUSERSITE": "1"},
            )
        except subprocess.TimeoutExpired as exc:
            raise EnvironmentBuildError(f"依赖命令超过 {timeout} 秒未完成") from exc
        if completed.returncode:
            output = (completed.stdout + "\n" + completed.stderr).strip()[-4_000:]
            safe_index = PipRuntimeEnvironmentBuilder._safe_url(index_url)
            output = output.replace(index_url, safe_index)
            raise EnvironmentBuildError(f"依赖命令失败（退出码 {completed.returncode}）：{output}")
        return completed.stdout

    @staticmethod
    def _safe_url(url: str) -> str:
        parts = urlsplit(url)
        host = parts.hostname or ""
        if parts.port:
            host += f":{parts.port}"
        return urlunsplit((parts.scheme, host, parts.path, "", ""))

    @staticmethod
    def _read_existing(manifest_file: Path, environment_dir: Path) -> EnvironmentBuildResult:
        try:
            value = json.loads(manifest_file.read_text(encoding="utf-8"))
            return EnvironmentBuildResult(
                str(value["resolvedFingerprint"]),
                str(value["resolvedLock"]),
                tuple(value["wheels"]),
                str(environment_dir),
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise EnvironmentBuildError("现有依赖环境清单损坏，请重新准备") from exc
