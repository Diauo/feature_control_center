from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from app.domain.identity import ValidationError


_CONFIG_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,79}$")
_ENTRYPOINT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,79}$")
_SECRET_PARTS = {"secret", "token", "password", "passwd", "api_key", "app_key", "access_key"}
_CONFIG_TYPES = {"string", "integer", "number", "boolean", "enum", "text", "secret"}
_REPORT_TYPES = {"string", "integer", "number", "boolean"}
_REPORT_RESERVED_KEYS = {
    "sequence",
    "status",
    "reason",
    "reason_code",
    "reasoncode",
    "reported_at",
    "reportedat",
}


@dataclass(frozen=True, slots=True)
class NormalizedFeatureMetadata:
    name: str
    description: str
    entrypoint: str
    config_schema: dict[str, dict[str, Any]]
    data_source_schema: dict[str, Any] | None
    report_schema: dict[str, Any] | None
    warnings: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "entrypoint": self.entrypoint,
            "configs": self.config_schema,
            "data_source": self.data_source_schema,
            "report": self.report_schema,
        }


def normalize_feature_metadata(raw: object, archive_files: set[str]) -> NormalizedFeatureMetadata:
    if not isinstance(raw, dict):
        raise ValidationError("INVALID_FEATURE_META", "__meta__ 必须是字典字面量")
    warnings: list[str] = []
    name = _clean_text(raw.get("name"), "功能名称", 120, required=True)
    description = _clean_text(raw.get("description", ""), "功能说明", 500, required=False)
    entrypoint = str(raw.get("entrypoint", "run")).strip()
    if not _ENTRYPOINT.fullmatch(entrypoint):
        raise ValidationError("INVALID_ENTRYPOINT", "entrypoint 必须是当前模块中的函数名")
    config_schema = _normalize_configs(raw.get("configs", {}), warnings)
    data_source_schema = _normalize_data_source(raw.get("data_source"), archive_files, warnings)
    report_schema = _normalize_report(raw.get("report"))
    if "customer" in raw:
        warnings.append("已忽略旧元数据中的 customer；客户归属由平台操作决定。")
    return NormalizedFeatureMetadata(
        name=name,
        description=description,
        entrypoint=entrypoint,
        config_schema=config_schema,
        data_source_schema=data_source_schema,
        report_schema=report_schema,
        warnings=tuple(warnings),
    )


def _normalize_report(value: object) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValidationError("INVALID_REPORT_SCHEMA", "report 必须是字典")
    raw_columns = value.get("columns")
    if not isinstance(raw_columns, (list, tuple)) or not 1 <= len(raw_columns) <= 30:
        raise ValidationError("INVALID_REPORT_COLUMNS", "report.columns 必须包含 1 到 30 个字段")

    columns: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, raw_column in enumerate(raw_columns, start=1):
        if not isinstance(raw_column, dict):
            raise ValidationError("INVALID_REPORT_COLUMN", f"报表第 {index} 个字段必须是字典")
        raw_key = raw_column.get("key")
        if not isinstance(raw_key, str) or not _CONFIG_KEY.fullmatch(raw_key):
            raise ValidationError("INVALID_REPORT_COLUMN_KEY", f"报表第 {index} 个字段键名无效")
        key = raw_key.strip()
        normalized_key = key.casefold()
        if normalized_key in seen:
            raise ValidationError("DUPLICATE_REPORT_COLUMN", f"报表字段 {key} 重复")
        if normalized_key in _REPORT_RESERVED_KEYS:
            raise ValidationError("REPORT_COLUMN_RESERVED", f"报表字段 {key} 使用了平台保留名称")
        if _looks_secret(key):
            raise ValidationError("REPORT_SECRET_FIELD_FORBIDDEN", f"报表字段 {key} 疑似包含密钥，不允许登记")
        field_type = str(raw_column.get("type", "string")).strip().lower()
        if field_type not in _REPORT_TYPES:
            raise ValidationError("INVALID_REPORT_COLUMN_TYPE", f"报表字段 {key} 的类型 {field_type!r} 不受支持")
        seen.add(normalized_key)
        columns.append(
            {
                "key": key,
                "label": _clean_text(raw_column.get("label", key), f"报表字段 {key} 的标签", 80, required=True),
                "type": field_type,
            }
        )
    return {
        "title": _clean_text(value.get("title", "执行结果"), "报表标题", 120, required=True),
        "item_label": _clean_text(value.get("item_label", "数据"), "报表对象名称", 40, required=True),
        "columns": columns,
    }


def _normalize_configs(value: object, warnings: list[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise ValidationError("INVALID_CONFIG_SCHEMA", "configs 必须是字典")
    if len(value) > 100:
        raise ValidationError("TOO_MANY_CONFIGS", "单个功能最多声明 100 个配置项")
    result: dict[str, dict[str, Any]] = {}
    for raw_key, raw_spec in value.items():
        if not isinstance(raw_key, str) or not _CONFIG_KEY.fullmatch(raw_key):
            raise ValidationError("INVALID_CONFIG_KEY", f"配置键 {raw_key!r} 格式无效")
        if raw_key in result:
            raise ValidationError("DUPLICATE_CONFIG_KEY", f"配置键 {raw_key} 重复")
        if isinstance(raw_spec, (tuple, list)) and len(raw_spec) == 2:
            default, description = raw_spec
            secret = _looks_secret(raw_key)
            inferred_type = "secret" if secret else _infer_type(default)
            result[raw_key] = {
                "type": inferred_type,
                "label": raw_key,
                "description": _clean_text(description, f"配置 {raw_key} 的说明", 500, required=False),
                "required": True if secret else default is None,
            }
            if default is not None and not secret:
                result[raw_key]["default"] = _validate_scalar(inferred_type, default, raw_key, None)
            elif default is not None and secret:
                warnings.append(f"配置 {raw_key} 疑似密钥，旧包中的默认值已丢弃，必须在平台内重新填写。")
            warnings.append(f"配置 {raw_key} 使用旧式二元组，已转换为 {inferred_type} 类型。")
            continue
        if not isinstance(raw_spec, dict):
            raise ValidationError("INVALID_CONFIG_FIELD", f"配置 {raw_key} 的定义必须是字典")
        field_type = str(raw_spec.get("type", "string")).strip().lower()
        if field_type == "float":
            field_type = "number"
        if field_type not in _CONFIG_TYPES:
            raise ValidationError("INVALID_CONFIG_TYPE", f"配置 {raw_key} 的类型 {field_type!r} 不受支持")
        required = raw_spec.get("required", "default" not in raw_spec)
        if not isinstance(required, bool):
            raise ValidationError("INVALID_CONFIG_FIELD", f"配置 {raw_key} 的 required 必须是布尔值")
        normalized: dict[str, Any] = {
            "type": field_type,
            "label": _clean_text(raw_spec.get("label", raw_key), f"配置 {raw_key} 的标签", 80, required=True),
            "description": _clean_text(
                raw_spec.get("description", ""), f"配置 {raw_key} 的说明", 500, required=False
            ),
            "required": required,
        }
        options: list[Any] | None = None
        if field_type == "enum":
            raw_options = raw_spec.get("options")
            if not isinstance(raw_options, (list, tuple)) or not 1 <= len(raw_options) <= 100:
                raise ValidationError("INVALID_ENUM_OPTIONS", f"配置 {raw_key} 必须声明 1 到 100 个枚举选项")
            options = []
            for option in raw_options:
                if isinstance(option, bool) or not isinstance(option, (str, int, float)):
                    raise ValidationError("INVALID_ENUM_OPTIONS", f"配置 {raw_key} 的枚举选项格式无效")
                if option not in options:
                    options.append(option)
            normalized["options"] = options
        for bound in ("min", "max"):
            if bound in raw_spec:
                number = raw_spec[bound]
                if isinstance(number, bool) or not isinstance(number, (int, float)):
                    raise ValidationError("INVALID_CONFIG_BOUND", f"配置 {raw_key} 的 {bound} 必须是数字")
                normalized[bound] = number
        if "min" in normalized and "max" in normalized and normalized["min"] > normalized["max"]:
            raise ValidationError("INVALID_CONFIG_BOUND", f"配置 {raw_key} 的最小值不能大于最大值")
        if "default" in raw_spec:
            if field_type == "secret" and raw_spec["default"] not in (None, ""):
                raise ValidationError("SECRET_DEFAULT_FORBIDDEN", f"密钥配置 {raw_key} 不能在功能包中携带默认值")
            if field_type != "secret":
                default = _validate_scalar(field_type, raw_spec["default"], raw_key, options)
                if required and (default is None or (field_type in {"string", "text"} and default == "")):
                    raise ValidationError("CONFIG_REQUIRED_DEFAULT", f"必填配置 {raw_key} 的默认值不能为空")
                _validate_bounds(default, normalized, raw_key, "默认值")
                normalized["default"] = default
        result[raw_key] = normalized
    return result


def _normalize_data_source(
    value: object,
    archive_files: set[str],
    warnings: list[str],
) -> dict[str, Any] | None:
    if value is None:
        inferred = [name for name in archive_files if PurePosixPath(name).name.casefold().startswith("datasource.")]
        if len(inferred) > 1:
            raise ValidationError("AMBIGUOUS_DATA_SOURCE", "发现多个 dataSource 文件，请在元数据中明确声明")
        if not inferred:
            return None
        filename = inferred[0]
        suffix = PurePosixPath(filename).suffix.lower()
        warnings.append("已从旧功能包中的 dataSource 文件推断必需数据源，请尽快补充 data_source 元数据。")
        return {
            "filename": filename,
            "required": True,
            "extensions": [suffix] if suffix else [],
            "description": "功能数据源",
        }
    if not isinstance(value, dict):
        raise ValidationError("INVALID_DATA_SOURCE_SCHEMA", "data_source 必须是字典")
    filename = _safe_archive_path(value.get("filename"))
    required = value.get("required", False)
    if not isinstance(required, bool):
        raise ValidationError("INVALID_DATA_SOURCE_SCHEMA", "data_source.required 必须是布尔值")
    raw_extensions = value.get("extensions")
    if raw_extensions is None:
        suffix = PurePosixPath(filename).suffix.lower()
        extensions = [suffix] if suffix else []
    elif isinstance(raw_extensions, (list, tuple)) and len(raw_extensions) <= 30:
        extensions = []
        for extension in raw_extensions:
            if not isinstance(extension, str):
                raise ValidationError("INVALID_DATA_SOURCE_EXTENSION", "数据源扩展名必须是字符串")
            normalized = extension.strip().lower()
            if not normalized.startswith(".") or len(normalized) > 20 or "/" in normalized or "\\" in normalized:
                raise ValidationError("INVALID_DATA_SOURCE_EXTENSION", f"数据源扩展名 {extension!r} 无效")
            if normalized not in extensions:
                extensions.append(normalized)
    else:
        raise ValidationError("INVALID_DATA_SOURCE_EXTENSION", "data_source.extensions 格式无效")
    declared_suffix = PurePosixPath(filename).suffix.lower()
    if declared_suffix and extensions and declared_suffix not in extensions:
        raise ValidationError(
            "DATA_SOURCE_EXTENSION_MISMATCH",
            "默认数据源文件的扩展名必须包含在 data_source.extensions 中",
        )
    return {
        "filename": filename,
        "required": required,
        "extensions": extensions,
        "description": _clean_text(
            value.get("description", ""), "数据源说明", 500, required=False
        ),
    }


def _safe_archive_path(value: object) -> str:
    if not isinstance(value, str):
        raise ValidationError("INVALID_DATA_SOURCE_FILENAME", "数据源文件名不能为空")
    normalized = unicodedata.normalize("NFKC", value).strip()
    path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or "\\" in normalized
        or "//" in normalized
        or any(part in {"", ".", ".."} for part in path.parts)
        or (path.parts and ":" in path.parts[0])
        or len(normalized) > 255
    ):
        raise ValidationError("INVALID_DATA_SOURCE_FILENAME", "数据源文件名必须是功能包内的安全相对路径")
    return normalized


def _validate_scalar(field_type: str, value: object, key: str, options: list[Any] | None) -> Any:
    if value is None:
        return None
    if field_type in {"string", "text"}:
        if not isinstance(value, str):
            raise ValidationError("INVALID_CONFIG_DEFAULT", f"配置 {key} 的默认值必须是字符串")
        if len(value) > 10_000:
            raise ValidationError("INVALID_CONFIG_DEFAULT", f"配置 {key} 的默认值过长")
        return value
    if field_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValidationError("INVALID_CONFIG_DEFAULT", f"配置 {key} 的默认值必须是整数")
        return value
    if field_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValidationError("INVALID_CONFIG_DEFAULT", f"配置 {key} 的默认值必须是数字")
        if not math.isfinite(value):
            raise ValidationError("INVALID_CONFIG_DEFAULT", f"配置 {key} 的数字必须是有限值")
        return value
    if field_type == "boolean":
        if not isinstance(value, bool):
            raise ValidationError("INVALID_CONFIG_DEFAULT", f"配置 {key} 的默认值必须是布尔值")
        return value
    if field_type == "enum":
        if value not in (options or []):
            raise ValidationError("INVALID_CONFIG_DEFAULT", f"配置 {key} 的默认值不在枚举选项中")
        return value
    return value


def validate_config_value(key: str, schema: dict[str, Any], value: object) -> Any:
    """Validate one customer value using the package schema."""
    field_type = str(schema["type"])
    validated = _validate_scalar(field_type, value, key, schema.get("options"))
    _validate_bounds(validated, schema, key, "配置值")
    return validated


def _validate_bounds(value: object, schema: dict[str, Any], key: str, label: str) -> None:
    if value is None:
        return
    field_type = str(schema.get("type", ""))
    measure: int | float | None = None
    if field_type in {"string", "text"} and isinstance(value, str):
        measure = len(value)
    elif field_type in {"integer", "number"} and not isinstance(value, bool) and isinstance(value, (int, float)):
        measure = value
    if measure is not None and "min" in schema and measure < schema["min"]:
        raise ValidationError("CONFIG_VALUE_OUT_OF_RANGE", f"配置 {key} 的{label}小于允许范围")
    if measure is not None and "max" in schema and measure > schema["max"]:
        raise ValidationError("CONFIG_VALUE_OUT_OF_RANGE", f"配置 {key} 的{label}大于允许范围")


def _clean_text(value: object, label: str, maximum: int, *, required: bool) -> str:
    if not isinstance(value, str):
        if not required and value is None:
            return ""
        raise ValidationError("INVALID_FEATURE_META", f"{label}必须是字符串")
    cleaned = unicodedata.normalize("NFKC", value).strip()
    if required and not cleaned:
        raise ValidationError("INVALID_FEATURE_META", f"{label}不能为空")
    if len(cleaned) > maximum or any(unicodedata.category(char).startswith("C") for char in cleaned):
        raise ValidationError("INVALID_FEATURE_META", f"{label}包含不支持的字符或长度超限")
    return cleaned


def _looks_secret(key: str) -> bool:
    normalized = key.casefold()
    return any(part in normalized for part in _SECRET_PARTS)


def _infer_type(value: object) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return "string"
