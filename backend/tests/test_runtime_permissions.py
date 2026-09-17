from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from app.infrastructure import runtime_permissions
from app.infrastructure.runtime_permissions import (
    RuntimePermissionError,
    ensure_log_files_readable,
    prepare_runs_root,
    publish_runtime_environment,
    repair_runtime_cache,
    shared_file_mode,
)
from app.runner import dependencies
from app.runner.dependencies import DependencyPreparer
from app.runner.materializer import PreparedRun
from app.runner.worker import RunnerWorker


def test_shared_environment_is_root_owned_and_never_group_writable(tmp_path: Path, monkeypatch):
    environment = tmp_path / "runtime-cache" / "environments" / "fingerprint"
    binary = environment / "bin" / "python"
    module = environment / "lib" / "module.py"
    binary.parent.mkdir(parents=True)
    module.parent.mkdir()
    binary.write_text("python", encoding="utf-8")
    module.write_text("value = 1", encoding="utf-8")

    owners: list[tuple[Path, int, int, bool]] = []
    modes: list[tuple[Path, int]] = []
    monkeypatch.setattr(
        runtime_permissions,
        "_chown",
        lambda path, uid, gid, follow_symlinks=True: owners.append((path, uid, gid, follow_symlinks)),
    )
    monkeypatch.setattr(runtime_permissions, "_chmod", lambda path, mode: modes.append((path, mode)))

    publish_runtime_environment(environment.parent, environment, 10002)

    assert (environment.parent, 0, 10002, True) in owners
    assert (environment, 0, 10002, True) in owners
    assert (module, 0, 10002, True) in owners
    assert (environment.parent, 0o710) in modes
    assert (environment, 0o750) in modes
    assert (module, 0o440) in modes
    assert all(mode & 0o020 == 0 for _, mode in modes)


def test_runtime_repair_keeps_wheel_cache_private(tmp_path: Path, monkeypatch):
    runtime_cache = tmp_path / "runtime-cache"
    environment_file = runtime_cache / "environments" / "fingerprint" / "package.py"
    wheel_file = runtime_cache / "wheels" / "package.whl"
    environment_file.parent.mkdir(parents=True)
    wheel_file.parent.mkdir(parents=True)
    environment_file.write_text("value = 1", encoding="utf-8")
    wheel_file.write_bytes(b"wheel")

    owners: list[tuple[Path, int, int, bool]] = []
    modes: list[tuple[Path, int]] = []
    monkeypatch.setattr(
        runtime_permissions,
        "_chown",
        lambda path, uid, gid, follow_symlinks=True: owners.append((path, uid, gid, follow_symlinks)),
    )
    monkeypatch.setattr(runtime_permissions, "_chmod", lambda path, mode: modes.append((path, mode)))

    repair_runtime_cache(runtime_cache, 10002)

    assert (runtime_cache, 0, 0, True) in owners
    assert (runtime_cache / "environments", 0, 10002, True) in owners
    assert (runtime_cache / "wheels", 0, 0, True) in owners
    assert (runtime_cache, 0o755) in modes
    assert (runtime_cache / "environments", 0o710) in modes
    assert (runtime_cache / "wheels", 0o700) in modes
    assert (wheel_file, 0o600) in modes


def test_system_log_files_are_group_readable_for_web(tmp_path: Path, monkeypatch):
    directory = tmp_path / "system-logs" / "runner"
    directory.mkdir(parents=True)
    log_file = directory / "2026-09-17.jsonl"
    log_file.write_text("{}\n", encoding="utf-8")
    notes = directory / "notes.txt"
    notes.write_text("ignore", encoding="utf-8")

    owners: list[tuple[Path, int, int, bool]] = []
    modes: list[tuple[Path, int]] = []
    monkeypatch.setattr(
        runtime_permissions,
        "_chown",
        lambda path, uid, gid, follow_symlinks=True: owners.append((path, uid, gid, follow_symlinks)),
    )
    monkeypatch.setattr(runtime_permissions, "_chmod", lambda path, mode: modes.append((path, mode)))

    ensure_log_files_readable(directory, 10001)

    assert owners == [(log_file, -1, 10001, True)]
    assert modes == [(log_file, 0o660)]


def test_runs_root_allows_traversal_without_write_access(tmp_path: Path, monkeypatch):
    owners: list[tuple[Path, int, int, bool]] = []
    modes: list[tuple[Path, int]] = []
    monkeypatch.setattr(
        runtime_permissions,
        "_chown",
        lambda path, uid, gid, follow_symlinks=True: owners.append((path, uid, gid, follow_symlinks)),
    )
    monkeypatch.setattr(runtime_permissions, "_chmod", lambda path, mode: modes.append((path, mode)))
    runs_root = tmp_path / "runs"

    prepare_runs_root(runs_root, 10002)

    assert (runs_root, 0, 10002, True) in owners
    assert (runs_root, 0o710) in modes


def test_runtime_roots_reject_symbolic_links(tmp_path: Path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "runs"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("当前 Windows 环境不允许创建测试符号链接")

    with pytest.raises(RuntimePermissionError, match="不能是符号链接"):
        prepare_runs_root(link, 10002)


def test_environment_publish_rejects_a_builder_path_outside_the_cache(tmp_path: Path):
    environments = tmp_path / "runtime-cache" / "environments"
    environments.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()

    with pytest.raises(RuntimePermissionError, match="不在平台缓存目录内"):
        publish_runtime_environment(environments, outside, 10002)


def test_shared_file_modes_preserve_execution_without_write_access():
    assert shared_file_mode(0o100755) == 0o550
    assert shared_file_mode(0o100644) == 0o440


def test_dependency_preparer_publishes_into_the_trusted_cache(tmp_path: Path, monkeypatch):
    environments = tmp_path / "runtime-cache" / "environments"
    environment = environments / "fingerprint"
    published: list[tuple[Path, Path, int]] = []
    monkeypatch.setattr(
        dependencies,
        "publish_runtime_environment",
        lambda root, target, gid: published.append((root, target, gid)),
    )
    preparer = object.__new__(DependencyPreparer)
    preparer.script_gid = 10002
    preparer.environments_root = environments

    preparer._publish_environment(environment)

    assert published == [(environments, environment, 10002)]


def test_feature_environment_uses_the_configured_timezone(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TZ", "UTC")
    work_dir = tmp_path / "run"
    prepared = PreparedRun(
        request_id="run-id",
        work_dir=work_dir,
        package_dir=work_dir / "package",
        input_file=work_dir / "input.json",
        cancel_file=work_dir / "cancel.requested",
        python_executable=Path("python"),
        event_token="event-token",
        report_schema=None,
        report_max_items=60_000,
    )

    environment = RunnerWorker._sanitized_environment(prepared, "Asia/Hong_Kong")

    assert environment["TZ"] == "Asia/Hong_Kong"
    assert environment["HOME"] == str(work_dir / "home")
    assert "FCC_DATA_DIR" not in environment


@pytest.mark.skipif(os.name == "nt" or not hasattr(os, "geteuid") or os.geteuid() != 0, reason="需要 Linux root")
def test_linux_script_identity_can_execute_but_cannot_modify_shared_roots():
    try:
        import pwd

        account = pwd.getpwnam("fcc-script")
    except (ImportError, KeyError):
        pytest.skip("系统没有 fcc-script 账户")

    base = Path(tempfile.mkdtemp(prefix="fcc-permissions-", dir="/tmp"))
    try:
        os.chmod(base, 0o755)
        runtime_cache = base / "runtime-cache"
        runtime_cache.mkdir(mode=0o755)
        environment = runtime_cache / "environments" / "fingerprint"
        tool = environment / "bin" / "probe"
        module = environment / "lib" / "module.py"
        tool.parent.mkdir(parents=True)
        module.parent.mkdir()
        tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        module.write_text("value = 1\n", encoding="utf-8")
        os.chmod(tool, 0o755)
        wheel = runtime_cache / "wheels" / "package.whl"
        wheel.parent.mkdir()
        wheel.write_bytes(b"wheel")
        repair_runtime_cache(runtime_cache, account.pw_gid)

        runs_root = base / "tmp" / "runs"
        runs_root.parent.mkdir(mode=0o711)
        prepare_runs_root(runs_root, account.pw_gid)

        process_options = {"user": account.pw_uid, "group": account.pw_gid, "extra_groups": []}
        assert subprocess.run([str(tool)], check=False, **process_options).returncode == 0
        assert subprocess.run(["cat", str(module)], capture_output=True, check=False, **process_options).returncode == 0
        assert subprocess.run(
            ["sh", "-c", f"echo changed >> '{module}'"], capture_output=True, check=False, **process_options
        ).returncode != 0
        assert subprocess.run(
            ["mkdir", str(environment.parent / "injected")], capture_output=True, check=False, **process_options
        ).returncode != 0
        assert subprocess.run(
            ["mkdir", str(runs_root / "injected")], capture_output=True, check=False, **process_options
        ).returncode != 0
        assert subprocess.run(
            ["cat", str(wheel)], capture_output=True, check=False, **process_options
        ).returncode != 0
    finally:
        shutil.rmtree(base, ignore_errors=True)
