from __future__ import annotations

import ast
import hashlib
import io
import stat
import tarfile
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

import py7zr
import rarfile
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from py7zr.io import BytesIOFactory

from app.domain.feature_metadata import NormalizedFeatureMetadata, normalize_feature_metadata
from app.domain.identity import ValidationError


PACKAGE_FORMATS: dict[str, tuple[str, ...]] = {
    "zip": (".zip",),
    "7z": (".7z",),
    "tar": (".tar",),
    "tar_gz": (".tar.gz", ".tgz"),
    "tar_bz2": (".tar.bz2", ".tbz2"),
    "tar_xz": (".tar.xz", ".txz"),
    "rar": (".rar",),
}


@dataclass(frozen=True, slots=True)
class PackageLimits:
    max_package_bytes: int
    max_entries: int
    max_entry_bytes: int
    max_total_bytes: int
    max_compression_ratio: int


@dataclass(frozen=True, slots=True)
class PackageFile:
    filename: str
    content: bytes
    sha256: bytes


@dataclass(frozen=True, slots=True)
class InspectedPackage:
    package_filename: str
    package_content: bytes
    package_sha256: bytes
    metadata: NormalizedFeatureMetadata
    source_encoding: str
    requirements_text: str
    default_data_source: PackageFile | None
    offline_wheels: tuple[PackageFile, ...]


@dataclass(frozen=True, slots=True)
class _Entry:
    name: str
    size: int
    compressed_size: int | None
    is_directory: bool
    is_link: bool
    is_special: bool
    encrypted: bool
    source: Any


@dataclass(slots=True)
class _OpenedArchive:
    entries: list[_Entry]
    read_many: Callable[[set[str]], dict[str, bytes]]
    close: Callable[[], None]


class FeaturePackageInspector:
    def inspect(
        self,
        filename: str,
        content: bytes,
        limits: PackageLimits,
        allowed_formats: tuple[str, ...] | None = None,
    ) -> InspectedPackage:
        safe_filename = PurePosixPath(filename.replace("\\", "/")).name
        format_id = package_format_for_filename(safe_filename)
        if format_id is None:
            raise ValidationError("PACKAGE_FORMAT_UNKNOWN", "功能包扩展名不受支持")
        allowed = tuple(PACKAGE_FORMATS) if allowed_formats is None else allowed_formats
        if format_id not in allowed:
            raise ValidationError("PACKAGE_FORMAT_DISABLED", "系统设置中未启用这种功能包格式")
        if not content or len(content) > limits.max_package_bytes:
            raise ValidationError("PACKAGE_SIZE_INVALID", "功能包为空或超过系统大小限制")

        opened = _open_archive(format_id, content, limits.max_total_bytes)
        try:
            files = self._validate_entries(opened.entries, limits, len(content))
            initializer = files.get("__init__.py")
            if initializer is None:
                raise ValidationError("FEATURE_INIT_REQUIRED", "功能包根目录必须包含 __init__.py")
            source_bytes = opened.read_many({initializer.name})[initializer.name]
            source, encoding, encoding_warning = self._decode_source(source_bytes)
            metadata_literal, functions = self._read_metadata(source)
            metadata = normalize_feature_metadata(metadata_literal, set(files))
            if metadata.entrypoint not in functions:
                raise ValidationError("ENTRYPOINT_NOT_FOUND", f"未找到入口函数 {metadata.entrypoint}")
            warnings = list(metadata.warnings)
            if encoding_warning:
                warnings.append(encoding_warning)
            metadata = NormalizedFeatureMetadata(
                name=metadata.name,
                description=metadata.description,
                entrypoint=metadata.entrypoint,
                config_schema=metadata.config_schema,
                data_source_schema=metadata.data_source_schema,
                report_schema=metadata.report_schema,
                warnings=tuple(warnings),
            )

            requested: set[str] = set()
            if "requirements.txt" in files:
                requested.add("requirements.txt")
            if metadata.data_source_schema:
                data_source_name = metadata.data_source_schema["filename"]
                if data_source_name in files:
                    requested.add(data_source_name)
            wheel_names = {
                name for name in files if name.startswith("wheels/") and name.lower().endswith(".whl")
            }
            requested.update(wheel_names)
            selected = opened.read_many(requested) if requested else {}

            requirements_text = ""
            if raw_requirements := selected.get("requirements.txt"):
                if len(raw_requirements) > 65_536:
                    raise ValidationError("REQUIREMENTS_TOO_LARGE", "requirements.txt 不能超过 64 KiB")
                try:
                    requirement_source = raw_requirements.decode("utf-8-sig")
                except UnicodeDecodeError as exc:
                    raise ValidationError("REQUIREMENTS_ENCODING", "requirements.txt 必须使用 UTF-8") from exc
                requirements_text = self._normalize_requirements(requirement_source)

            default_data_source = None
            if metadata.data_source_schema:
                data_source_name = metadata.data_source_schema["filename"]
                if data_source_name in selected:
                    data = selected[data_source_name]
                    default_data_source = PackageFile(data_source_name, data, hashlib.sha256(data).digest())

            wheels_list: list[PackageFile] = []
            wheel_basenames: set[str] = set()
            for name in sorted(wheel_names):
                basename = PurePosixPath(name).name.casefold()
                if basename in wheel_basenames:
                    raise ValidationError("DUPLICATE_WHEEL_NAME", "wheels 目录包含同名 wheel 文件")
                wheel_basenames.add(basename)
                wheel_content = selected[name]
                wheels_list.append(PackageFile(name, wheel_content, hashlib.sha256(wheel_content).digest()))
        finally:
            opened.close()

        return InspectedPackage(
            package_filename=safe_filename[:255],
            package_content=content,
            package_sha256=hashlib.sha256(content).digest(),
            metadata=metadata,
            source_encoding=encoding,
            requirements_text=requirements_text,
            default_data_source=default_data_source,
            offline_wheels=tuple(wheels_list),
        )

    @staticmethod
    def _validate_entries(
        entries: list[_Entry], limits: PackageLimits, compressed_package_size: int
    ) -> dict[str, _Entry]:
        if not entries or len(entries) > limits.max_entries:
            raise ValidationError("PACKAGE_ENTRY_LIMIT", "功能包条目数为空或超过系统限制")
        files: dict[str, _Entry] = {}
        collision_keys: set[str] = set()
        total = 0
        for entry in entries:
            normalized = _safe_member_name(entry.name)
            if entry.encrypted:
                raise ValidationError("PACKAGE_ENCRYPTION_FORBIDDEN", "功能包不能设置密码")
            if entry.is_link or entry.is_special:
                raise ValidationError("PACKAGE_LINK_FORBIDDEN", f"功能包不允许链接或特殊文件：{entry.name}")
            if entry.is_directory:
                continue
            collision_key = normalized.casefold()
            if collision_key in collision_keys:
                raise ValidationError("DUPLICATE_PACKAGE_PATH", f"功能包存在重复或大小写冲突路径：{entry.name}")
            collision_keys.add(collision_key)
            if entry.size < 0 or entry.size > limits.max_entry_bytes:
                raise ValidationError("PACKAGE_ENTRY_TOO_LARGE", f"功能包文件 {entry.name} 超过单文件限制")
            total += entry.size
            if total > limits.max_total_bytes:
                raise ValidationError("PACKAGE_TOTAL_TOO_LARGE", "功能包解压后总大小超过系统限制")
            if entry.compressed_size is not None:
                ratio = entry.size / max(entry.compressed_size, 1)
                if ratio > limits.max_compression_ratio:
                    raise ValidationError("PACKAGE_RATIO_TOO_HIGH", f"功能包文件 {entry.name} 压缩比例异常")
            files[normalized] = entry
        if total / max(compressed_package_size, 1) > limits.max_compression_ratio:
            raise ValidationError("PACKAGE_RATIO_TOO_HIGH", "功能包整体压缩比例异常")
        return files

    @staticmethod
    def _decode_source(content: bytes) -> tuple[str, str, str | None]:
        try:
            return content.decode("utf-8-sig"), "utf-8", None
        except UnicodeDecodeError:
            try:
                return (
                    content.decode("gb18030"),
                    "gb18030",
                    "__init__.py 未使用 UTF-8，已按 GB18030 兼容读取；建议后续版本改为 UTF-8。",
                )
            except UnicodeDecodeError as exc:
                raise ValidationError("FEATURE_SOURCE_ENCODING", "__init__.py 必须使用 UTF-8 或兼容的 GB18030") from exc

    @staticmethod
    def _read_metadata(source: str) -> tuple[object, set[str]]:
        try:
            tree = ast.parse(source, filename="__init__.py")
        except SyntaxError as exc:
            raise ValidationError("FEATURE_SOURCE_SYNTAX", f"__init__.py 语法错误：第 {exc.lineno} 行") from exc
        meta_nodes: list[ast.AST] = []
        functions: set[str] = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.add(node.name)
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "__meta__" for target in node.targets
            ):
                meta_nodes.append(node.value)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "__meta__":
                if node.value is not None:
                    meta_nodes.append(node.value)
        if len(meta_nodes) != 1:
            raise ValidationError("FEATURE_META_REQUIRED", "__init__.py 必须且只能声明一次 __meta__")
        try:
            return ast.literal_eval(meta_nodes[0]), functions
        except (ValueError, TypeError, SyntaxError) as exc:
            raise ValidationError("FEATURE_META_NOT_LITERAL", "__meta__ 只能使用字典、列表、元组和基础字面量") from exc

    @staticmethod
    def _normalize_requirements(source: str) -> str:
        requirements: dict[str, str] = {}
        for line_number, raw_line in enumerate(source.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("-") or " #" in line:
                raise ValidationError(
                    "UNSAFE_REQUIREMENT", f"requirements.txt 第 {line_number} 行不允许 pip 参数或行尾选项"
                )
            try:
                requirement = Requirement(line)
            except InvalidRequirement as exc:
                raise ValidationError("INVALID_REQUIREMENT", f"requirements.txt 第 {line_number} 行格式无效") from exc
            if requirement.url is not None:
                raise ValidationError("DIRECT_URL_FORBIDDEN", "依赖不能使用 URL、VCS 或本地路径")
            key = canonicalize_name(requirement.name)
            canonical = key + str(requirement)[len(requirement.name) :]
            if key in requirements:
                raise ValidationError("DUPLICATE_REQUIREMENT", f"依赖 {requirement.name} 重复声明")
            requirements[key] = canonical
        return "\n".join(requirements[key] for key in sorted(requirements)) + ("\n" if requirements else "")


def package_format_for_filename(filename: str) -> str | None:
    lowered = filename.casefold()
    for format_id, suffixes in PACKAGE_FORMATS.items():
        if any(lowered.endswith(suffix) for suffix in suffixes):
            return format_id
    return None


def allowed_package_extensions(formats: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(suffix for format_id in formats for suffix in PACKAGE_FORMATS.get(format_id, ()))


def extract_feature_package(filename: str, content: bytes, target: Path) -> None:
    format_id = package_format_for_filename(filename)
    if format_id is None:
        raise ValidationError("PACKAGE_FORMAT_UNKNOWN", "功能包扩展名不受支持")
    target = target.resolve()
    opened = _open_archive(format_id, content, max(len(content) * 1_000, 2_147_483_648))
    try:
        for entry in opened.entries:
            normalized = _safe_member_name(entry.name)
            if entry.encrypted or entry.is_link or entry.is_special:
                raise ValidationError("PACKAGE_LINK_FORBIDDEN", "功能包包含链接、特殊文件或加密内容")
            destination = (target / Path(*PurePosixPath(normalized).parts)).resolve()
            if not destination.is_relative_to(target):
                raise ValidationError("UNSAFE_PACKAGE_PATH", "功能包路径越界")
            if entry.is_directory:
                destination.mkdir(parents=True, exist_ok=True)
        file_names = {entry.name for entry in opened.entries if not entry.is_directory}
        contents = opened.read_many(file_names)
        for entry in opened.entries:
            if entry.is_directory:
                continue
            normalized = _safe_member_name(entry.name)
            destination = (target / Path(*PurePosixPath(normalized).parts)).resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(contents[entry.name])
    finally:
        opened.close()


def _safe_member_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKC", name)
    path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized != name
        or normalized.startswith("/")
        or "\\" in normalized
        or "//" in normalized
        or "\x00" in normalized
        or len(normalized) > 500
        or any(part in {"", ".", ".."} for part in path.parts)
        or (path.parts and ":" in path.parts[0])
    ):
        raise ValidationError("UNSAFE_PACKAGE_PATH", f"功能包路径 {name!r} 不安全")
    return normalized


def _open_archive(format_id: str, content: bytes, memory_limit: int) -> _OpenedArchive:
    if format_id == "zip":
        return _open_zip(content)
    if format_id == "7z":
        return _open_7z(content, memory_limit)
    if format_id == "rar":
        return _open_rar(content)
    return _open_tar(format_id, content)


def _open_zip(content: bytes) -> _OpenedArchive:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
        entries = [
            _Entry(
                name=info.filename,
                size=info.file_size,
                compressed_size=info.compress_size,
                is_directory=info.is_dir(),
                is_link=bool((info.external_attr >> 16) and stat.S_ISLNK(info.external_attr >> 16)),
                is_special=bool(
                    ((info.external_attr >> 16) & 0o170000)
                    and not (
                        stat.S_ISREG(info.external_attr >> 16)
                        or stat.S_ISDIR(info.external_attr >> 16)
                        or stat.S_ISLNK(info.external_attr >> 16)
                    )
                ),
                encrypted=bool(info.flag_bits & 0x1),
                source=info,
            )
            for info in archive.infolist()
        ]
        if not any(entry.encrypted for entry in entries):
            bad_member = archive.testzip()
            if bad_member is not None:
                archive.close()
                raise ValidationError("PACKAGE_CRC_FAILED", f"功能包文件 {bad_member} 校验失败")
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError("INVALID_PACKAGE", "功能包内容与 ZIP 格式不匹配") from exc

    def read_many(names: set[str]) -> dict[str, bytes]:
        try:
            return {name: archive.read(name) for name in names}
        except Exception as exc:
            raise ValidationError("PACKAGE_READ_FAILED", "读取 ZIP 功能包失败") from exc

    return _OpenedArchive(entries, read_many, archive.close)


def _open_tar(format_id: str, content: bytes) -> _OpenedArchive:
    modes = {"tar": "r:", "tar_gz": "r:gz", "tar_bz2": "r:bz2", "tar_xz": "r:xz"}
    try:
        archive = tarfile.open(fileobj=io.BytesIO(content), mode=modes[format_id])
        entries = [
            _Entry(
                name=member.name,
                size=member.size,
                compressed_size=None,
                is_directory=member.isdir(),
                is_link=member.issym() or member.islnk(),
                is_special=not (member.isfile() or member.isdir() or member.issym() or member.islnk()),
                encrypted=False,
                source=member,
            )
            for member in archive.getmembers()
        ]
    except (tarfile.TarError, OSError, EOFError, KeyError) as exc:
        raise ValidationError("INVALID_PACKAGE", "功能包内容与 TAR 格式不匹配") from exc
    member_by_name = {entry.name: entry.source for entry in entries}

    def read_many(names: set[str]) -> dict[str, bytes]:
        try:
            result: dict[str, bytes] = {}
            for name in names:
                stream = archive.extractfile(member_by_name[name])
                if stream is None:
                    raise ValidationError("PACKAGE_READ_FAILED", f"无法读取功能包文件 {name}")
                with stream:
                    result[name] = stream.read()
            return result
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError("PACKAGE_READ_FAILED", "读取 TAR 功能包失败") from exc

    return _OpenedArchive(entries, read_many, archive.close)


def _open_7z(content: bytes, memory_limit: int) -> _OpenedArchive:
    if not content.startswith(b"7z\xbc\xaf'\x1c"):
        raise ValidationError("INVALID_PACKAGE", "功能包内容与 7z 格式不匹配")
    try:
        archive = py7zr.SevenZipFile(io.BytesIO(content), mode="r")
        if archive.needs_password():
            archive.close()
            raise ValidationError("PACKAGE_ENCRYPTION_FORBIDDEN", "功能包不能设置密码")
        infos = archive.list()
        entries = [
            _Entry(
                name=info.filename,
                size=int(info.uncompressed or 0),
                compressed_size=int(info.compressed) if info.compressed is not None else None,
                is_directory=bool(info.is_directory),
                is_link=bool(info.is_symlink),
                is_special=not (info.is_file or info.is_directory or info.is_symlink),
                encrypted=False,
                source=info,
            )
            for info in infos
        ]
        bad_member = archive.testzip()
        if bad_member is not None:
            archive.close()
            raise ValidationError("PACKAGE_CRC_FAILED", f"功能包文件 {bad_member} 校验失败")
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError("INVALID_PACKAGE", "功能包内容与 7z 格式不匹配") from exc

    def read_many(names: set[str]) -> dict[str, bytes]:
        if not names:
            return {}
        archive.reset()
        factory = BytesIOFactory(limit=memory_limit)
        try:
            archive.extract(targets=sorted(names), factory=factory)
            return {name: factory.get(name).read() for name in names}
        except Exception as exc:
            raise ValidationError("PACKAGE_READ_FAILED", "读取 7z 功能包失败") from exc

    return _OpenedArchive(entries, read_many, archive.close)


def _open_rar(content: bytes) -> _OpenedArchive:
    rar3_signature = b"Rar!\x1a\x07\x00"
    rar5_signature = b"Rar!\x1a\x07\x01\x00"
    if not (content.startswith(rar3_signature) or content.startswith(rar5_signature)):
        raise ValidationError("INVALID_PACKAGE", "功能包内容与 RAR 格式不匹配，或属于不允许的自解压包")
    try:
        archive = rarfile.RarFile(io.BytesIO(content), mode="r", errors="strict")
        infos = list(archive.infolist())
        if archive.needs_password():
            archive.close()
            raise ValidationError("PACKAGE_ENCRYPTION_FORBIDDEN", "功能包不能设置密码")
        if len(archive.volumelist()) > 1 or any(getattr(info, "volume", 0) not in (0, None) for info in infos):
            archive.close()
            raise ValidationError("PACKAGE_MULTIVOLUME_FORBIDDEN", "功能包不能使用分卷 RAR")
        entries = [
            _Entry(
                name=info.filename,
                size=int(info.file_size),
                compressed_size=int(info.compress_size) if info.compress_size is not None else None,
                is_directory=bool(info.is_dir()),
                is_link=bool(info.is_symlink() or getattr(info, "file_redir", None) is not None),
                is_special=not (info.is_file() or info.is_dir() or info.is_symlink()),
                encrypted=bool(info.needs_password()),
                source=info,
            )
            for info in infos
        ]
    except ValidationError:
        raise
    except rarfile.NeedFirstVolume as exc:
        raise ValidationError("PACKAGE_MULTIVOLUME_FORBIDDEN", "功能包不能使用分卷 RAR") from exc
    except rarfile.Error as exc:
        raise ValidationError("INVALID_PACKAGE", "功能包内容与 RAR 格式不匹配") from exc
    except Exception as exc:
        raise ValidationError("INVALID_PACKAGE", "无法读取 RAR 功能包") from exc
    info_by_name = {info.filename: info for info in infos}

    def read_many(names: set[str]) -> dict[str, bytes]:
        try:
            return {name: archive.read(info_by_name[name]) for name in names}
        except rarfile.RarCannotExec as exc:
            raise ValidationError(
                "RAR_EXTRACTOR_UNAVAILABLE",
                "服务器缺少 RAR 解码组件，请检查交付镜像中的 7zz",
            ) from exc
        except rarfile.Error as exc:
            raise ValidationError("PACKAGE_READ_FAILED", "读取 RAR 功能包失败") from exc

    return _OpenedArchive(entries, read_many, archive.close)
