from __future__ import annotations

from collections.abc import Iterator
import os
import stat
from pathlib import Path


class RuntimePermissionError(RuntimeError):
    pass


def prepare_root_directory(path: Path, mode: int) -> None:
    _ensure_directory(path, uid=0, gid=0, mode=mode)


def repair_runtime_cache(runtime_cache: Path, script_gid: int) -> None:
    """Restore the least-privilege boundary for reusable runtime artifacts."""
    _ensure_directory(runtime_cache, uid=0, gid=0, mode=0o755)
    environments = runtime_cache / "environments"
    wheels = runtime_cache / "wheels"
    _ensure_directory(environments, uid=0, gid=script_gid, mode=0o710)
    _ensure_directory(wheels, uid=0, gid=0, mode=0o700)

    for child in environments.iterdir():
        if child.is_symlink() or not child.is_dir():
            raise RuntimePermissionError(f"依赖环境目录包含异常条目：{child.name}")
        _apply_environment_tree(child, script_gid)
    _apply_private_tree(wheels)


def publish_runtime_environment(environments_root: Path, environment_dir: Path, script_gid: int) -> None:
    """Publish one completed venv as root-owned and read-only to fcc-script."""
    if environments_root.is_symlink():
        raise RuntimePermissionError("依赖环境根目录不能是符号链接")
    expected_root = environments_root.resolve()
    if environment_dir.parent.resolve() != expected_root:
        raise RuntimePermissionError("依赖环境不在平台缓存目录内")
    _ensure_directory(environments_root, uid=0, gid=script_gid, mode=0o710)
    if environment_dir.is_symlink() or not environment_dir.is_dir():
        raise RuntimePermissionError("依赖环境目录不存在或类型异常")
    _apply_environment_tree(environment_dir, script_gid)


def prepare_runs_root(runs_root: Path, script_gid: int) -> None:
    """Allow fcc-script to traverse the run parent without listing or modifying it."""
    _ensure_directory(runs_root, uid=0, gid=script_gid, mode=0o710)


def ensure_log_files_readable(directory: Path, web_gid: int) -> None:
    """把根进程（runner/launcher）写出的系统日志归一为 web 组可读。

    容器内 runner 需要 root 身份以便把功能脚本降权到 fcc-script，因此它写出的
    日志文件不会继承目录的 setgid 组；启动时统一修正已有文件，配合目录 setgid
    保证后续新文件同样可读，避免 web 服务读取程序日志时报 PermissionError。
    """
    if not directory.is_dir():
        return
    for path in sorted(directory.glob("*.jsonl")):
        if path.is_symlink():
            continue
        _chown(path, -1, web_gid)
        _chmod(path, 0o660)


def shared_file_mode(source_mode: int) -> int:
    return 0o550 if source_mode & 0o111 else 0o440


def _apply_environment_tree(root: Path, script_gid: int) -> None:
    for path in _tree(root):
        if path.is_symlink():
            _chown(path, 0, script_gid, follow_symlinks=False)
            continue
        if path.is_dir():
            _chown(path, 0, script_gid)
            _chmod(path, 0o750)
            continue
        if path.is_file():
            mode = path.stat().st_mode
            _chown(path, 0, script_gid)
            _chmod(path, shared_file_mode(mode))
            continue
        raise RuntimePermissionError(f"依赖环境包含不支持的文件类型：{path.name}")


def _apply_private_tree(root: Path) -> None:
    for path in _tree(root):
        if path.is_symlink():
            _chown(path, 0, 0, follow_symlinks=False)
            continue
        if path.is_dir():
            _chown(path, 0, 0)
            _chmod(path, 0o700)
            continue
        if path.is_file():
            mode = 0o700 if path.stat().st_mode & stat.S_IXUSR else 0o600
            _chown(path, 0, 0)
            _chmod(path, mode)
            continue
        raise RuntimePermissionError(f"wheel 缓存包含不支持的文件类型：{path.name}")


def _tree(root: Path) -> Iterator[Path]:
    yield root
    yield from root.rglob("*")


def _ensure_directory(path: Path, *, uid: int, gid: int, mode: int) -> None:
    if path.is_symlink():
        raise RuntimePermissionError(f"运行目录不能是符号链接：{path.name}")
    if path.exists() and not path.is_dir():
        raise RuntimePermissionError(f"运行目录类型异常：{path.name}")
    path.mkdir(parents=True, exist_ok=True)
    _chown(path, uid, gid)
    _chmod(path, mode)


def _chown(path: Path, uid: int, gid: int, *, follow_symlinks: bool = True) -> None:
    try:
        os.chown(path, uid, gid, follow_symlinks=follow_symlinks)
    except (AttributeError, NotImplementedError) as exc:
        raise RuntimePermissionError("当前系统不支持 POSIX 目录归属设置") from exc
    except OSError as exc:
        raise RuntimePermissionError(f"无法设置运行目录归属：{path.name}") from exc


def _chmod(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError as exc:
        raise RuntimePermissionError(f"无法设置运行目录权限：{path.name}") from exc
