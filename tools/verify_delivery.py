from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import re
import zipfile
from pathlib import PurePosixPath


REQUIRED_FILES = {
    "Dockerfile",
    "docker-compose.yml",
    "install.sh",
    "manage.sh",
    "VERSION",
    "DELIVERY-MANIFEST.json",
    "checksums.sha256",
    "backend/pyproject.toml",
    "frontend/package.json",
    "docs/delivery/00-交付包说明.md",
    "docs/delivery/03-功能包开发规范.md",
}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="校验功能控制中心客户交付 ZIP")
    parser.add_argument("archive", help="待校验的交付 ZIP")
    return parser.parse_args()


def inspect_feature_package(name: str, content: bytes) -> None:
    with zipfile.ZipFile(io.BytesIO(content)) as package:
        names = {PurePosixPath(item.filename).as_posix() for item in package.infolist() if not item.is_dir()}
        if "__init__.py" not in names:
            raise RuntimeError(f"{name} 根目录缺少 __init__.py")
        source = package.read("__init__.py").decode("utf-8-sig")
        tree = ast.parse(source, filename=f"{name}/__init__.py")
        metadata = []
        functions = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.add(node.name)
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "__meta__" for target in node.targets
            ):
                metadata.append(ast.literal_eval(node.value))
        if len(metadata) != 1 or not isinstance(metadata[0], dict):
            raise RuntimeError(f"{name} 的 __meta__ 无效")
        entrypoint = metadata[0].get("entrypoint", "run")
        if entrypoint not in functions:
            raise RuntimeError(f"{name} 缺少入口函数 {entrypoint}")
        data_source = metadata[0].get("data_source")
        if data_source and data_source.get("required") and data_source.get("filename") not in names:
            raise RuntimeError(f"{name} 缺少声明的数据源")


def member_sha256(archive: zipfile.ZipFile, name: str) -> str:
    digest = hashlib.sha256()
    with archive.open(name) as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify(archive_name: str) -> dict[str, object]:
    with zipfile.ZipFile(archive_name) as archive:
        files = [item.filename for item in archive.infolist() if not item.is_dir()]
        roots = {PurePosixPath(name).parts[0] for name in files}
        if len(roots) != 1:
            raise RuntimeError("交付 ZIP 必须只有一个顶层目录")
        root = next(iter(roots))
        relative = {PurePosixPath(name).relative_to(root).as_posix(): name for name in files}
        if "VERSION" not in relative:
            raise RuntimeError("交付文件缺少 VERSION")
        version = archive.read(relative["VERSION"]).decode("utf-8").strip()
        versioned_files = {
            f"feature-packages/交付验收示例-{version}.zip",
            f"feature-packages/功能包起步模板-{version}.zip",
            f"feature-packages/OZON库存同步-{version}-online.zip",
        }
        missing = sorted((REQUIRED_FILES | versioned_files) - set(relative))
        if missing:
            raise RuntimeError(f"交付文件缺失：{', '.join(missing)}")
        if any(path == "data" or path.startswith("data/") for path in relative):
            raise RuntimeError("交付 ZIP 不得包含运行数据目录")
        if any("node_modules" in PurePosixPath(path).parts or "__pycache__" in PurePosixPath(path).parts for path in relative):
            raise RuntimeError("交付 ZIP 包含应排除的构建缓存")
        if any(re.search(r"update-signing-private|\.env$", path, re.IGNORECASE) for path in relative):
            raise RuntimeError("交付 ZIP 包含疑似私密发布文件")

        checksums = archive.read(relative["checksums.sha256"]).decode("utf-8").splitlines()
        expected: dict[str, str] = {}
        for line in checksums:
            digest, separator, path = line.partition("  ")
            if not separator or not re.fullmatch(r"[0-9a-f]{64}", digest) or not path:
                raise RuntimeError("checksums.sha256 格式无效")
            if path in expected:
                raise RuntimeError(f"checksums.sha256 路径重复：{path}")
            expected[path] = digest
        checksummed_files = set(relative) - {"checksums.sha256"}
        if set(expected) != checksummed_files:
            raise RuntimeError("checksums.sha256 与交付文件集合不一致")
        for path, digest in expected.items():
            actual = member_sha256(archive, relative[path])
            if actual != digest:
                raise RuntimeError(f"文件校验失败：{path}")

        manifest = json.loads(archive.read(relative["DELIVERY-MANIFEST.json"]))
        if manifest.get("version") != version:
            raise RuntimeError("交付清单版本与 VERSION 不一致")
        image_files = sorted(path for path in relative if path.startswith("images/") and path.endswith(".tar"))
        manifest_images = sorted(f"images/{name}" for name in manifest.get("dockerImages", []))
        if image_files != manifest_images:
            raise RuntimeError("交付清单的 Docker 镜像列表与实际文件不一致")
        expected_mode = "offline-image" if image_files else "source-build"
        if manifest.get("deliveryMode") != expected_mode:
            raise RuntimeError("交付模式与 Docker 镜像文件不一致")
        compose = archive.read(relative["docker-compose.yml"]).decode("utf-8")
        if f"feature-control-center:{version}" not in compose:
            raise RuntimeError("Docker Compose 镜像版本不一致")
        for script in sorted(path for path in relative if path.endswith(".sh")):
            content = archive.read(relative[script])
            if not content.startswith(b"#!/usr/bin/env sh\n") or b"\r\n" in content:
                raise RuntimeError(f"{script} 不是可移植的 LF shell 脚本")
            mode = archive.getinfo(relative[script]).external_attr >> 16
            if mode & 0o111 == 0:
                raise RuntimeError(f"{script} 没有 Unix 可执行权限")
        for path in sorted(value for value in relative if value.startswith("feature-packages/") and value.endswith(".zip")):
            inspect_feature_package(path, archive.read(relative[path]))
        return {
            "root": root,
            "version": version,
            "deliveryMode": manifest.get("deliveryMode"),
            "files": len(relative),
            "featurePackages": len(
                [path for path in relative if path.startswith("feature-packages/") and path.endswith(".zip")]
            ),
        }


def main() -> None:
    result = verify(parse_arguments().archive)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("交付包完整性校验通过。")


if __name__ == "__main__":
    main()
