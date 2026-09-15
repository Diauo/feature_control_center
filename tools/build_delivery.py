from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
# 客户业务素材（旧包、客户源码、兼容示例等）：仅内网保存，.gitignore 已排除，不随仓库分发。
CLIENT_ASSETS = ROOT / "delivery-assets"
COPY_DIRECTORIES = ("backend", "frontend", "docs", "deployment", "examples", "tools")
COPY_ROOT_FILES = (
    ".dockerignore",
    ".gitignore",
    "Dockerfile",
    "docker-compose.yml",
    "install.sh",
    "manage.sh",
    "start.bat",
    "start.sh",
    "stop.bat",
    "stop.sh",
    "VERSION",
)
SKIP_PARTS = {
    ".git",
    ".idea",
    ".pytest_cache",
    ".venv",
    ".vscode",
    "__pycache__",
    "dist",
    "htmlcov",
    "node_modules",
}
SKIP_SUFFIXES = (".pyc", ".pyo", ".tsbuildinfo")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成功能控制中心客户交付 ZIP")
    parser.add_argument("--output", type=Path, help="输出 ZIP；默认写入项目 dist 目录")
    parser.add_argument(
        "--image-dir",
        type=Path,
        default=ROOT / "delivery-assets" / "images",
        help="可选的 Docker 离线镜像目录",
    )
    parser.add_argument(
        "--wheel-dir",
        type=Path,
        default=ROOT / "delivery-assets" / "feature-wheels" / "ozon-linux-amd64",
        help="可选的 OZON Linux amd64 离线 wheel 目录",
    )
    return parser.parse_args()


def should_copy(relative: Path) -> bool:
    if any(part in SKIP_PARTS for part in relative.parts):
        return False
    if relative.suffix.lower() in SKIP_SUFFIXES:
        return False
    if relative.name in {".coverage", "first-run.txt"} or relative.name.endswith(".egg-info"):
        return False
    normalized = "/".join(relative.parts)
    if normalized == "app/web/static" or normalized.startswith("app/web/static/"):
        return False
    return True


def copy_tree(source: Path, target: Path) -> None:
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if not should_copy(relative):
            continue
        destination = target / relative
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)


def write_feature_archive(source: Path, target: Path, wheel_dir: Path | None = None) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file() or path.name == "README.md" or not should_copy(path.relative_to(source)):
                continue
            write_zip_member(archive, path, path.relative_to(source).as_posix())
        if wheel_dir is not None:
            wheels = sorted(wheel_dir.glob("*.whl"))
            if not wheels:
                raise RuntimeError(f"离线依赖目录没有 wheel：{wheel_dir}")
            for wheel in wheels:
                write_zip_member(archive, wheel, f"wheels/{wheel.name}")


def write_zip_member(archive: zipfile.ZipFile, source: Path, archive_name: str) -> None:
    stat = source.stat()
    stamp = datetime.fromtimestamp(stat.st_mtime, UTC)
    safe_year = max(1980, min(2107, stamp.year))
    info = zipfile.ZipInfo(
        archive_name,
        (safe_year, stamp.month, stamp.day, stamp.hour, stamp.minute, stamp.second),
    )
    info.create_system = 3
    executable = source.suffix == ".sh" or source.name in {"install.sh", "manage.sh"}
    info.external_attr = ((0o100755 if executable else 0o100644) << 16)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.flag_bits |= 0x800
    if hasattr(info, "compress_level"):
        info.compress_level = 9
    else:
        info._compresslevel = 9
    with source.open("rb") as input_file, archive.open(info, "w", force_zip64=True) as output_file:
        shutil.copyfileobj(input_file, output_file, length=1024 * 1024)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def copy_images(image_dir: Path, destination: Path, version: str) -> list[str]:
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    if image_dir.is_dir():
        candidates = [
            image_dir / f"feature-control-center-{version}-linux-amd64.tar",
            image_dir / f"feature-control-center-{version}-linux-arm64.tar",
        ]
        for source in candidates:
            if not source.is_file():
                continue
            sidecar = source.with_name(f"{source.name}.sha256")
            if not sidecar.is_file():
                raise RuntimeError(f"Docker 镜像缺少校验文件：{sidecar}")
            expected = sidecar.read_text(encoding="utf-8").strip().split()[0].lower()
            actual = sha256_file(source)
            if expected != actual:
                raise RuntimeError(f"Docker 镜像校验失败：{source}")
            target = destination / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(target.name)
    if not copied:
        (destination / "README.md").write_text(
            "# Docker 离线镜像\n\n"
            "本交付包生成环境未提供 Linux Docker 引擎，因此这里没有伪造镜像文件。"
            "目标服务器首次安装时会从本包源代码构建。若需完全离线部署，请在联网 Linux 构建机执行 "
            "`./deployment/build-offline-bundle.sh`，再重新运行 `python3 tools/build_delivery.py`。\n",
            encoding="utf-8",
            newline="\n",
        )
    return copied


def generate_checksums(root: Path) -> str:
    lines: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "checksums.sha256":
            continue
        digest = sha256_file(path)
        lines.append(f"{digest}  {path.relative_to(root).as_posix()}")
    return "\n".join(lines) + "\n"


def write_delivery_zip(staging: Path, output: Path, archive_root: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.partial")
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(staging.rglob("*")):
                if not path.is_file():
                    continue
                name = PurePosixPath(archive_root) / path.relative_to(staging).as_posix()
                write_zip_member(archive, path, name.as_posix())
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def build(output: Path | None, image_dir: Path, wheel_dir: Path) -> Path:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not version:
        raise RuntimeError("VERSION 为空")
    output = output or ROOT / "dist" / f"功能控制中心-{version}-交付包.zip"
    output = output.resolve()
    archive_root = f"功能控制中心-{version}"

    with tempfile.TemporaryDirectory(prefix="fcc-delivery-") as temporary:
        staging = Path(temporary) / archive_root
        staging.mkdir(parents=True)
        for name in COPY_ROOT_FILES:
            source = ROOT / name
            if not source.is_file():
                raise RuntimeError(f"交付必需文件不存在：{name}")
            shutil.copy2(source, staging / name)
        for name in COPY_DIRECTORIES:
            source = ROOT / name
            if not source.is_dir():
                raise RuntimeError(f"交付必需目录不存在：{name}")
            copy_tree(source, staging / name)

        source_readme = staging / "README.md"
        shutil.copy2(ROOT / "README.md", staging / "docs" / "源代码与开发说明.md")
        shutil.copy2(ROOT / "docs" / "delivery" / "00-交付包说明.md", source_readme)
        history = staging / "docs" / "development-history"
        copy_tree(ROOT / ".md", history)
        client_features = CLIENT_ASSETS / "features"
        if not client_features.is_dir():
            raise RuntimeError(
                "客户端兼容示例缺失：delivery-assets/features（业务素材仅保留内网，不随仓库分发）"
            )
        copy_tree(client_features, staging / "features")

        reference = staging / "reference"
        reference.mkdir(parents=True, exist_ok=True)
        client_original = CLIENT_ASSETS / "ozon_Inventory.zip"
        if not client_original.is_file():
            raise RuntimeError(
                "客户端原始包缺失：delivery-assets/ozon_Inventory.zip（业务素材仅保留内网，不随仓库分发）"
            )
        shutil.copy2(client_original, reference / "ozon_Inventory.original.zip")

        package_dir = staging / "feature-packages"
        write_feature_archive(
            ROOT / "examples" / "feature-packages" / "smoke_test",
            package_dir / f"交付验收示例-{version}.zip",
        )
        write_feature_archive(
            ROOT / "examples" / "feature-packages" / "starter_template",
            package_dir / f"功能包起步模板-{version}.zip",
        )
        write_feature_archive(
            ROOT / "examples" / "feature-packages" / "log_stream_test",
            package_dir / f"实时日志稳定性测试-{version}.zip",
        )
        ozon_source = CLIENT_ASSETS / "ozon_inventory"
        if not ozon_source.is_dir():
            raise RuntimeError(
                "客户端 OZON 源码素材缺失：delivery-assets/ozon_inventory（业务素材仅保留内网，不随仓库分发）"
            )
        copy_tree(ozon_source, staging / "examples" / "feature-packages" / "ozon_inventory")
        write_feature_archive(ozon_source, package_dir / f"OZON库存同步-{version}-online.zip")
        offline_package = None
        if wheel_dir.is_dir() and any(wheel_dir.glob("*.whl")):
            offline_package = f"OZON库存同步-{version}-linux-amd64-offline.zip"
            write_feature_archive(ozon_source, package_dir / offline_package, wheel_dir)

        images = copy_images(image_dir, staging / "images", version)
        manifest = {
            "schemaVersion": 1,
            "product": "功能控制中心",
            "version": version,
            "builtAtUtc": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "deliveryMode": "offline-image" if images else "source-build",
            "sourceCodeIncluded": True,
            "containerPython": "3.14.4",
            "databaseRevision": "0009_run_reports",
            "supportedContainerPlatforms": ["linux/amd64", "linux/arm64"],
            "dockerImages": images,
            "featurePackages": {
                "acceptance": f"交付验收示例-{version}.zip",
                "starter": f"功能包起步模板-{version}.zip",
                "logStreamTest": f"实时日志稳定性测试-{version}.zip",
                "ozonOnline": f"OZON库存同步-{version}-online.zip",
                "ozonOfflineLinuxAmd64": offline_package,
            },
            "persistentDataPath": "data/",
            "backupPath": "backups/",
            "entrypoint": "./install.sh",
            "originalOzonSha256": "dff7ed7776bb9c76b1ab260ad0f489db1e8e613b8accd41c1633865b6318dddf",
        }
        (staging / "DELIVERY-MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        (staging / "checksums.sha256").write_text(
            generate_checksums(staging), encoding="utf-8", newline="\n"
        )
        write_delivery_zip(staging, output, archive_root)
    return output


def main() -> None:
    arguments = parse_arguments()
    output = build(arguments.output, arguments.image_dir.resolve(), arguments.wheel_dir.resolve())
    digest = sha256_file(output)
    sidecar = output.with_name(f"{output.name}.sha256")
    sidecar.write_text(f"{digest}  {output.name}\n", encoding="utf-8", newline="\n")
    print(f"交付包：{output}")
    print(f"SHA-256：{digest}")
    print(f"外部校验文件：{sidecar}")
    print(f"大小：{output.stat().st_size} bytes")


if __name__ == "__main__":
    main()
