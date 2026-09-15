from __future__ import annotations

import base64
import binascii
import hashlib
import json
import platform
import re
import shutil
import stat
import sys
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version


UPDATE_SCHEMA_VERSION = 1
LAUNCHER_PROTOCOL_VERSION = 1
PRODUCT_ID = "feature-control-center"
MANIFEST_NAME = "manifest.json"
SIGNATURE_NAME = "manifest.sig"
MAX_MANIFEST_BYTES = 262_144
MAX_SIGNATURE_BYTES = 4_096
MAX_UPDATE_ENTRIES = 512
MAX_UPDATE_EXPANDED_BYTES = 2_147_483_648
MAX_UPDATE_COMPRESSION_RATIO = 200
_DATABASE_REVISION = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


class UpdatePackageError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class UpdateFile:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class UpdateManifest:
    version: str
    compatible_from: str
    python_version: str
    platform: str
    database_revision: str
    rollback_compatible: bool
    app_wheel: str
    release_notes: tuple[str, ...]
    files: tuple[UpdateFile, ...]
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class InspectedUpdatePackage:
    manifest: UpdateManifest
    package_sha256: bytes
    package_size: int


def trusted_update_public_key() -> Ed25519PublicKey:
    path = Path(__file__).with_name("update_public_key.pem")
    try:
        key = load_pem_public_key(path.read_bytes())
    except (OSError, ValueError, TypeError) as exc:
        raise UpdatePackageError("UPDATE_TRUST_UNAVAILABLE", "系统更新信任密钥不可用") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise UpdatePackageError("UPDATE_TRUST_INVALID", "系统更新信任密钥类型无效")
    return key


def runtime_platform() -> str:
    system = sys.platform
    if system.startswith("linux"):
        system = "linux"
    elif system.startswith("win"):
        system = "windows"
    elif system == "darwin":
        system = "macos"
    machine = platform.machine().lower()
    aliases = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "arm64", "arm64": "arm64"}
    return f"{system}_{aliases.get(machine, machine or 'unknown')}"


def inspect_update_package(
    package_path: Path,
    *,
    current_version: str,
    maximum_bytes: int,
    public_key: Ed25519PublicKey | None = None,
    expected_platform: str | None = None,
) -> InspectedUpdatePackage:
    try:
        package_size = package_path.stat().st_size
    except OSError as exc:
        raise UpdatePackageError("UPDATE_PACKAGE_UNREADABLE", "更新包无法读取") from exc
    if package_size <= 0 or package_size > maximum_bytes:
        raise UpdatePackageError("UPDATE_PACKAGE_SIZE_INVALID", "更新包为空或超过系统大小限制")
    package_sha256 = _file_sha256(package_path)
    try:
        archive = zipfile.ZipFile(package_path, mode="r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise UpdatePackageError("UPDATE_PACKAGE_INVALID", "更新包不是有效的 FCUP 文件") from exc
    with archive:
        infos = archive.infolist()
        if not infos or len(infos) > MAX_UPDATE_ENTRIES:
            raise UpdatePackageError("UPDATE_PACKAGE_ENTRY_LIMIT", "更新包条目为空或超过系统限制")
        by_name: dict[str, zipfile.ZipInfo] = {}
        collision_keys: set[str] = set()
        expanded_total = 0
        for info in infos:
            name = _safe_path(info.filename)
            collision = name.casefold()
            if collision in collision_keys:
                raise UpdatePackageError("UPDATE_PACKAGE_DUPLICATE_PATH", "更新包存在重复或大小写冲突路径")
            collision_keys.add(collision)
            mode = info.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            if info.flag_bits & 0x1:
                raise UpdatePackageError("UPDATE_PACKAGE_ENCRYPTED", "更新包不能设置密码")
            # DOS/Windows ZIP writers frequently store only 0o600 permission bits.
            # Reject links/devices only when the archive explicitly carries a Unix file type.
            if file_type and file_type not in {stat.S_IFREG, stat.S_IFDIR}:
                raise UpdatePackageError("UPDATE_PACKAGE_SPECIAL_FILE", "更新包不能包含链接或特殊文件")
            if info.is_dir():
                continue
            expanded_total += info.file_size
            if expanded_total > MAX_UPDATE_EXPANDED_BYTES:
                raise UpdatePackageError("UPDATE_PACKAGE_EXPANDED_LIMIT", "更新包展开后超过系统限制")
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > MAX_UPDATE_COMPRESSION_RATIO:
                raise UpdatePackageError("UPDATE_PACKAGE_RATIO_INVALID", "更新包包含异常压缩比例")
            by_name[name] = info
        if set((MANIFEST_NAME, SIGNATURE_NAME)) - set(by_name):
            raise UpdatePackageError("UPDATE_PACKAGE_STRUCTURE", "更新包缺少清单或签名")
        manifest_bytes = _bounded_read(archive, by_name[MANIFEST_NAME], MAX_MANIFEST_BYTES)
        signature_bytes = _bounded_read(archive, by_name[SIGNATURE_NAME], MAX_SIGNATURE_BYTES)
        try:
            manifest_value = json.loads(manifest_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UpdatePackageError("UPDATE_MANIFEST_INVALID", "更新清单不是有效的 UTF-8 JSON") from exc
        if not isinstance(manifest_value, dict):
            raise UpdatePackageError("UPDATE_MANIFEST_INVALID", "更新清单必须是 JSON 对象")
        canonical = canonical_manifest(manifest_value)
        if manifest_bytes != canonical:
            raise UpdatePackageError("UPDATE_MANIFEST_NOT_CANONICAL", "更新清单不是规范格式")
        try:
            signature = base64.b64decode(signature_bytes, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise UpdatePackageError("UPDATE_SIGNATURE_INVALID", "更新包签名格式无效") from exc
        try:
            (public_key or trusted_update_public_key()).verify(signature, canonical)
        except InvalidSignature as exc:
            raise UpdatePackageError("UPDATE_SIGNATURE_INVALID", "更新包签名验证失败") from exc
        manifest = _validate_manifest(
            manifest_value,
            current_version=current_version,
            expected_platform=expected_platform or runtime_platform(),
        )
        expected_paths = {item.path for item in manifest.files}
        actual_paths = set(by_name) - {MANIFEST_NAME, SIGNATURE_NAME}
        if actual_paths != expected_paths:
            raise UpdatePackageError("UPDATE_FILE_LIST_MISMATCH", "更新包文件与签名清单不一致")
        for item in manifest.files:
            info = by_name[item.path]
            if info.file_size != item.size:
                raise UpdatePackageError("UPDATE_FILE_SIZE_MISMATCH", f"更新文件大小不一致：{item.path}")
            with archive.open(info, "r") as source:
                digest = hashlib.sha256()
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != item.sha256:
                raise UpdatePackageError("UPDATE_FILE_HASH_MISMATCH", f"更新文件校验失败：{item.path}")
    return InspectedUpdatePackage(manifest, package_sha256, package_size)


def extract_update_wheels(package_path: Path, inspected: InspectedUpdatePackage, target: Path) -> None:
    target = target.resolve()
    target.mkdir(parents=True, exist_ok=False)
    try:
        with zipfile.ZipFile(package_path, mode="r") as archive:
            by_name = {info.filename: info for info in archive.infolist()}
            for item in inspected.manifest.files:
                destination = (target / Path(*PurePosixPath(item.path).parts)).resolve()
                if not destination.is_relative_to(target):
                    raise UpdatePackageError("UPDATE_PACKAGE_PATH_ESCAPE", "更新包路径越界")
                destination.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                with archive.open(by_name[item.path], "r") as source, destination.open("xb") as output:
                    while chunk := source.read(1024 * 1024):
                        digest.update(chunk)
                        output.write(chunk)
                if digest.hexdigest() != item.sha256:
                    raise UpdatePackageError("UPDATE_FILE_HASH_MISMATCH", f"更新文件校验失败：{item.path}")
                try:
                    destination.chmod(0o640)
                except OSError:
                    pass
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise


def canonical_manifest(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _validate_manifest(
    value: dict[str, Any], *, current_version: str, expected_platform: str
) -> UpdateManifest:
    required = {
        "schemaVersion",
        "product",
        "version",
        "compatibleFrom",
        "launcherProtocol",
        "pythonVersion",
        "platform",
        "databaseRevision",
        "rollbackCompatible",
        "appWheel",
        "releaseNotes",
        "files",
    }
    if set(value) != required:
        raise UpdatePackageError("UPDATE_MANIFEST_FIELDS", "更新清单字段不完整或包含未知字段")
    if value["schemaVersion"] != UPDATE_SCHEMA_VERSION or value["product"] != PRODUCT_ID:
        raise UpdatePackageError("UPDATE_MANIFEST_PRODUCT", "更新包不属于当前产品或协议版本")
    if value["launcherProtocol"] != LAUNCHER_PROTOCOL_VERSION:
        raise UpdatePackageError("UPDATE_LAUNCHER_INCOMPATIBLE", "更新包需要不同版本的基础启动器")
    target_text = _short_text(value["version"], "目标版本", 32)
    current_text = _short_text(current_version, "当前版本", 32)
    try:
        target_version = Version(target_text)
        parsed_current = Version(current_text)
    except InvalidVersion as exc:
        raise UpdatePackageError("UPDATE_VERSION_INVALID", "更新包版本号无效") from exc
    if target_version <= parsed_current:
        raise UpdatePackageError("UPDATE_VERSION_NOT_NEWER", "更新包版本必须高于当前运行版本")
    compatible_from = _short_text(value["compatibleFrom"], "兼容版本范围", 120)
    try:
        if parsed_current not in SpecifierSet(compatible_from):
            raise UpdatePackageError("UPDATE_SOURCE_INCOMPATIBLE", "当前版本不在更新包支持的升级范围内")
    except InvalidSpecifier as exc:
        raise UpdatePackageError("UPDATE_VERSION_RANGE_INVALID", "更新包兼容版本范围无效") from exc
    python_version = _short_text(value["pythonVersion"], "Python 版本", 16)
    actual_python = f"{sys.version_info.major}.{sys.version_info.minor}"
    if python_version != actual_python:
        raise UpdatePackageError("UPDATE_PYTHON_INCOMPATIBLE", "更新包与当前 Python 版本不兼容")
    target_platform = _short_text(value["platform"], "平台", 40)
    if target_platform != expected_platform:
        raise UpdatePackageError("UPDATE_PLATFORM_INCOMPATIBLE", "更新包与当前服务器平台不兼容")
    revision = _short_text(value["databaseRevision"], "数据库版本", 80)
    if not _DATABASE_REVISION.fullmatch(revision):
        raise UpdatePackageError("UPDATE_DATABASE_REVISION_INVALID", "更新包数据库版本标识无效")
    if not isinstance(value["rollbackCompatible"], bool):
        raise UpdatePackageError("UPDATE_ROLLBACK_FLAG_INVALID", "更新包回退兼容标识无效")
    app_wheel = _safe_path(_short_text(value["appWheel"], "应用 wheel", 300))
    if not app_wheel.startswith("wheels/") or not app_wheel.casefold().endswith(".whl"):
        raise UpdatePackageError("UPDATE_APP_WHEEL_INVALID", "更新包没有声明有效的应用 wheel")
    notes_value = value["releaseNotes"]
    if not isinstance(notes_value, list) or len(notes_value) > 100:
        raise UpdatePackageError("UPDATE_NOTES_INVALID", "更新说明格式无效")
    notes = tuple(_short_text(item, "更新说明", 500) for item in notes_value)
    files_value = value["files"]
    if not isinstance(files_value, list) or not files_value or len(files_value) > MAX_UPDATE_ENTRIES - 2:
        raise UpdatePackageError("UPDATE_FILES_INVALID", "更新文件清单为空或超过限制")
    files: list[UpdateFile] = []
    seen: set[str] = set()
    for raw in files_value:
        if not isinstance(raw, dict) or set(raw) != {"path", "size", "sha256"}:
            raise UpdatePackageError("UPDATE_FILE_INVALID", "更新文件清单条目无效")
        path = _safe_path(_short_text(raw["path"], "更新文件路径", 300))
        if not path.startswith("wheels/") or not path.casefold().endswith(".whl"):
            raise UpdatePackageError("UPDATE_FILE_TYPE_INVALID", "更新包只允许包含 wheel 文件")
        if path.casefold() in seen:
            raise UpdatePackageError("UPDATE_PACKAGE_DUPLICATE_PATH", "更新文件清单存在重复路径")
        seen.add(path.casefold())
        size = raw["size"]
        digest = raw["sha256"]
        if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_UPDATE_EXPANDED_BYTES:
            raise UpdatePackageError("UPDATE_FILE_SIZE_INVALID", "更新文件大小无效")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise UpdatePackageError("UPDATE_FILE_HASH_INVALID", "更新文件哈希无效")
        files.append(UpdateFile(path, size, digest))
    if app_wheel not in {item.path for item in files}:
        raise UpdatePackageError("UPDATE_APP_WHEEL_MISSING", "应用 wheel 不在更新文件清单中")
    return UpdateManifest(
        version=str(target_version),
        compatible_from=compatible_from,
        python_version=python_version,
        platform=target_platform,
        database_revision=revision,
        rollback_compatible=value["rollbackCompatible"],
        app_wheel=app_wheel,
        release_notes=notes,
        files=tuple(files),
        raw=value,
    )


def _bounded_read(archive: zipfile.ZipFile, info: zipfile.ZipInfo, maximum: int) -> bytes:
    if info.file_size > maximum:
        raise UpdatePackageError("UPDATE_METADATA_TOO_LARGE", "更新包元数据超过限制")
    with archive.open(info, "r") as source:
        content = source.read(maximum + 1)
    if len(content) > maximum:
        raise UpdatePackageError("UPDATE_METADATA_TOO_LARGE", "更新包元数据超过限制")
    return content


def _safe_path(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    path = PurePosixPath(normalized)
    if (
        normalized != value
        or not normalized
        or normalized.startswith("/")
        or "\\" in normalized
        or "//" in normalized
        or "\x00" in normalized
        or len(normalized) > 500
        or any(part in {"", ".", ".."} for part in path.parts)
        or (path.parts and ":" in path.parts[0])
    ):
        raise UpdatePackageError("UPDATE_PACKAGE_PATH_INVALID", "更新包包含不安全路径")
    return normalized


def _short_text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise UpdatePackageError("UPDATE_MANIFEST_VALUE_INVALID", f"{label}无效")
    return value.strip()


def _file_sha256(path: Path) -> bytes:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.digest()
