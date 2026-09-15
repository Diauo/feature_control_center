from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
import zipfile
from email.parser import BytesParser
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from packaging.version import InvalidVersion, Version
from packaging.specifiers import InvalidSpecifier, SpecifierSet

from app.update_package import (
    LAUNCHER_PROTOCOL_VERSION,
    MANIFEST_NAME,
    PRODUCT_ID,
    SIGNATURE_NAME,
    UPDATE_SCHEMA_VERSION,
    canonical_manifest,
    runtime_platform,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="功能控制中心更新包工具")
    subcommands = parser.add_subparsers(dest="command", required=True)
    generate = subcommands.add_parser("generate-key", help="生成 Ed25519 更新签名密钥")
    generate.add_argument("--private-key", type=Path, required=True)
    generate.add_argument("--public-key", type=Path, required=True)

    build = subcommands.add_parser("build", help="从离线 wheelhouse 构建签名 FCUP 更新包")
    build.add_argument("--wheelhouse", type=Path, required=True)
    build.add_argument("--private-key", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--version", required=True)
    build.add_argument("--compatible-from", default=">=0.1.0,<1.0.0")
    build.add_argument("--platform", default=runtime_platform())
    build.add_argument("--python-version", default=f"{sys.version_info.major}.{sys.version_info.minor}")
    build.add_argument("--database-revision", required=True)
    build.add_argument("--notes-file", type=Path)
    build.add_argument("--rollback-compatible", action="store_true")
    arguments = parser.parse_args()

    if arguments.command == "generate-key":
        generate_key(arguments.private_key, arguments.public_key)
    else:
        build_update_package(
            wheelhouse=arguments.wheelhouse,
            private_key_file=arguments.private_key,
            output=arguments.output,
            version=arguments.version,
            compatible_from=arguments.compatible_from,
            target_platform=arguments.platform,
            python_version=arguments.python_version,
            database_revision=arguments.database_revision,
            notes_file=arguments.notes_file,
            rollback_compatible=arguments.rollback_compatible,
        )


def generate_key(private_key_file: Path, public_key_file: Path) -> None:
    for path in (private_key_file, public_key_file):
        if path.exists():
            raise SystemExit(f"不会覆盖现有密钥文件：{path}")
        path.parent.mkdir(parents=True, exist_ok=True)
    private_key = Ed25519PrivateKey.generate()
    private_key_file.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_key_file.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    try:
        private_key_file.chmod(0o600)
        public_key_file.chmod(0o644)
    except OSError:
        pass
    print(f"私钥：{private_key_file.resolve()}")
    print(f"公钥：{public_key_file.resolve()}")


def build_update_package(
    *,
    wheelhouse: Path,
    private_key_file: Path,
    output: Path,
    version: str,
    compatible_from: str,
    target_platform: str,
    python_version: str,
    database_revision: str,
    notes_file: Path | None,
    rollback_compatible: bool,
) -> None:
    try:
        normalized_version = str(Version(version))
    except InvalidVersion as exc:
        raise SystemExit("版本号无效") from exc
    try:
        SpecifierSet(compatible_from)
    except InvalidSpecifier as exc:
        raise SystemExit("兼容版本范围无效") from exc
    if output.suffix.casefold() != ".fcup":
        raise SystemExit("更新包输出文件必须使用 .fcup 扩展名")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", database_revision):
        raise SystemExit("数据库版本标识无效")
    wheels = sorted(path for path in wheelhouse.resolve().glob("*.whl") if path.is_file())
    if not wheels:
        raise SystemExit("wheelhouse 中没有 wheel 文件")
    if len({path.name.casefold() for path in wheels}) != len(wheels):
        raise SystemExit("wheelhouse 中存在大小写冲突的 wheel 文件名")
    app_wheel = _find_app_wheel(wheels, normalized_version)
    notes = []
    if notes_file is not None:
        notes = [line.strip() for line in notes_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(notes) > 100 or any(len(item) > 500 for item in notes):
        raise SystemExit("更新说明最多 100 行，每行最多 500 个字符")
    files = [
        {
            "path": f"wheels/{path.name}",
            "size": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in wheels
    ]
    manifest = {
        "schemaVersion": UPDATE_SCHEMA_VERSION,
        "product": PRODUCT_ID,
        "version": normalized_version,
        "compatibleFrom": compatible_from,
        "launcherProtocol": LAUNCHER_PROTOCOL_VERSION,
        "pythonVersion": python_version,
        "platform": target_platform,
        "databaseRevision": database_revision,
        "rollbackCompatible": rollback_compatible,
        "appWheel": f"wheels/{app_wheel.name}",
        "releaseNotes": notes,
        "files": files,
    }
    canonical = canonical_manifest(manifest)
    key = serialization.load_pem_private_key(private_key_file.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise SystemExit("更新签名私钥必须是 Ed25519 PKCS8 PEM")
    signature = base64.b64encode(key.sign(canonical))
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise SystemExit(f"不会覆盖现有更新包：{output}")
    with zipfile.ZipFile(output, mode="x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr(MANIFEST_NAME, canonical)
        archive.writestr(SIGNATURE_NAME, signature)
        for wheel in wheels:
            archive.write(wheel, f"wheels/{wheel.name}")
    print(f"更新包：{output}")
    print(f"SHA-256：{_sha256(output)}")


def _find_app_wheel(wheels: list[Path], expected_version: str) -> Path:
    candidates: list[Path] = []
    for wheel in wheels:
        with zipfile.ZipFile(wheel, mode="r") as archive:
            metadata_names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(metadata_names) != 1:
                continue
            metadata = BytesParser().parsebytes(archive.read(metadata_names[0]))
        if metadata.get("Name", "").strip().lower().replace("_", "-") != PRODUCT_ID:
            continue
        try:
            wheel_version = str(Version(metadata.get("Version", "")))
        except InvalidVersion as exc:
            raise SystemExit(f"应用 wheel 元数据版本无效：{wheel.name}") from exc
        if wheel_version != expected_version:
            raise SystemExit("应用 wheel 版本与 --version 不一致")
        candidates.append(wheel)
    if len(candidates) != 1:
        raise SystemExit("wheelhouse 必须且只能包含一个当前版本的 feature-control-center wheel")
    return candidates[0]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
