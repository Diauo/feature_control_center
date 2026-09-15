from __future__ import annotations

import json
import math
import os
import re
import threading
import unicodedata
from pathlib import Path
from typing import Any


_cancellation = threading.Event()
_REPORT_STATUSES = {"SUCCESS", "FAILED", "NO_DATA", "SKIPPED", "UNFINISHED"}
_REPORT_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_.-]{0,79}$")
DEFAULT_REPORT_MAX_ITEMS = 60_000
ABSOLUTE_MAX_REPORT_ITEMS = 1_000_000
_MAX_REPORT_COMMAND_BYTES = 12_000
_MAX_SAFE_INTEGER = 9_007_199_254_740_991


class FeatureCancelled(RuntimeError):
    """Raised when the platform has asked the current run to stop."""


def request_cancellation() -> None:
    _cancellation.set()


class ConfigView:
    def __init__(self, values: dict[str, Any], secret_keys: set[str]) -> None:
        self._values = values
        self._secret_keys = secret_keys

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._secret_keys:
            raise KeyError(f"{key} 是密钥配置，请使用 get_secret()")
        return self._values.get(key, default)

    def get_secret(self, key: str) -> str:
        if key not in self._secret_keys:
            raise KeyError(f"{key} 不是已声明的密钥配置")
        value = self._values.get(key)
        if not isinstance(value, str) or not value:
            raise KeyError(f"密钥配置 {key} 未设置")
        return value


class FeatureLogger:
    def __init__(self, event_token: str) -> None:
        self._prefix = f"\x1eFCC:{event_token}:"

    def debug(self, message: object, **context: Any) -> None:
        self._write("DEBUG", message, context)

    def info(self, message: object, **context: Any) -> None:
        self._write("INFO", message, context)

    def warning(self, message: object, **context: Any) -> None:
        self._write("WARNING", message, context)

    def error(self, message: object, **context: Any) -> None:
        self._write("ERROR", message, context)

    def __call__(self, message: object, level: str = "info") -> None:
        """Compatibility with the original ctx.log(message, level) contract."""
        normalized = str(level).upper()
        self._write(normalized if normalized in {"DEBUG", "INFO", "WARNING", "ERROR"} else "INFO", message, {})

    def _write(self, level: str, message: object, context: dict[str, Any]) -> None:
        supplied_extra = context.pop("extra", None)
        if isinstance(supplied_extra, dict):
            context = {**supplied_extra, **context}
        payload = json.dumps(
            {"kind": "log", "level": level, "message": str(message), "context": context},
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        print(self._prefix + payload, flush=True)


class FeatureReport:
    def __init__(
        self,
        event_token: str,
        schema: dict[str, Any] | None,
        max_items: int = DEFAULT_REPORT_MAX_ITEMS,
    ) -> None:
        self._prefix = f"\x1eFCC:{event_token}:"
        self._schema = schema
        self._columns = {
            str(column["key"]): str(column["type"])
            for column in (schema or {}).get("columns", [])
            if isinstance(column, dict) and "key" in column and "type" in column
        }
        self._started = False
        self._completed = False
        self._expected_total: int | None = None
        self._item_count = 0
        self._max_items = (
            max_items
            if isinstance(max_items, int)
            and not isinstance(max_items, bool)
            and 1 <= max_items <= ABSOLUTE_MAX_REPORT_ITEMS
            else DEFAULT_REPORT_MAX_ITEMS
        )

    @property
    def available(self) -> bool:
        return self._schema is not None

    def start(self, expected_total: int | None = None) -> None:
        self._require_available()
        if expected_total is not None and (
            isinstance(expected_total, bool)
            or not isinstance(expected_total, int)
            or not 0 <= expected_total <= self._max_items
        ):
            raise ValueError(f"expected_total 必须是 0 到 {self._max_items} 的整数")
        if self._completed:
            raise RuntimeError("报表已经完成，不能重新开始")
        if self._started:
            if expected_total is not None and expected_total != self._expected_total:
                raise RuntimeError("报表总数已经声明，不能重复修改")
            return
        self._emit({"kind": "report.start", "expectedTotal": expected_total})
        self._expected_total = expected_total
        self._started = True

    def add(
        self,
        *,
        status: str,
        values: dict[str, Any],
        reason: str = "",
        reason_code: str | None = None,
    ) -> None:
        self._require_available()
        if self._completed:
            raise RuntimeError("报表已经完成，不能继续追加明细")
        normalized_status = str(status).strip().upper()
        if normalized_status not in _REPORT_STATUSES:
            raise ValueError(f"不支持的报表状态：{status}")
        if not isinstance(reason, str) or len(reason) > 1_000 or self._has_control(reason):
            raise ValueError("报表原因必须是不超过 1000 字符且不含控制字符的字符串")
        normalized_code = None
        if reason_code is not None:
            normalized_code = str(reason_code).strip().upper()
            if not _REPORT_REASON_CODE.fullmatch(normalized_code):
                raise ValueError("reason_code 必须是 1 到 80 位大写字母、数字、点、下划线或连字符")
        normalized_values = self._normalize_values(values)
        if not self._started:
            self.start()
        if self._item_count >= self._max_items:
            raise RuntimeError(f"单次运行最多提交 {self._max_items} 条报表明细")
        self._emit(
            {
                "kind": "report.item",
                "status": normalized_status,
                "reason": reason,
                "reasonCode": normalized_code,
                "values": normalized_values,
            }
        )
        self._item_count += 1

    def success(self, *, values: dict[str, Any], reason: str = "同步成功", reason_code: str | None = None) -> None:
        self.add(status="SUCCESS", values=values, reason=reason, reason_code=reason_code)

    def failed(self, *, values: dict[str, Any], reason: str, reason_code: str | None = None) -> None:
        self.add(status="FAILED", values=values, reason=reason, reason_code=reason_code)

    def no_data(self, *, values: dict[str, Any], reason: str = "无数据", reason_code: str | None = None) -> None:
        self.add(status="NO_DATA", values=values, reason=reason, reason_code=reason_code)

    def skipped(self, *, values: dict[str, Any], reason: str, reason_code: str | None = None) -> None:
        self.add(status="SKIPPED", values=values, reason=reason, reason_code=reason_code)

    def unfinished(self, *, values: dict[str, Any], reason: str, reason_code: str | None = None) -> None:
        self.add(status="UNFINISHED", values=values, reason=reason, reason_code=reason_code)

    def complete(self) -> None:
        self._require_available()
        if self._completed:
            return
        if not self._started:
            self.start(expected_total=0)
        self._emit({"kind": "report.complete"})
        self._completed = True

    def complete_if_started(self) -> None:
        if self._started and not self._completed:
            self.complete()

    def _normalize_values(self, values: object) -> dict[str, Any]:
        if not isinstance(values, dict):
            raise ValueError("报表 values 必须是字典")
        unknown = set(values) - set(self._columns)
        if unknown:
            raise ValueError(f"报表包含未声明字段：{', '.join(sorted(map(str, unknown)))}")
        normalized: dict[str, Any] = {}
        for key, value in values.items():
            field_type = self._columns[key]
            if value is None:
                normalized[key] = None
            elif field_type == "string" and isinstance(value, str):
                if len(value) > 2_000 or self._has_control(value):
                    raise ValueError(f"报表字段 {key} 超过 2000 字符或包含控制字符")
                normalized[key] = value
            elif (
                field_type == "integer"
                and isinstance(value, int)
                and not isinstance(value, bool)
                and abs(value) <= _MAX_SAFE_INTEGER
            ):
                normalized[key] = value
            elif field_type == "number" and self._is_finite_number(value):
                normalized[key] = value
            elif field_type == "boolean" and isinstance(value, bool):
                normalized[key] = value
            else:
                raise ValueError(f"报表字段 {key} 的值不符合 {field_type} 类型")
        return normalized

    def _require_available(self) -> None:
        if self._schema is None:
            raise RuntimeError("功能包没有在 __meta__.report 中声明结构化报表")

    def _emit(self, payload: dict[str, Any]) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if len(serialized.encode("utf-8")) > _MAX_REPORT_COMMAND_BYTES:
            raise ValueError("单条报表记录超过 12 KiB 限制")
        print(self._prefix + serialized, flush=True)

    @staticmethod
    def _is_finite_number(value: object) -> bool:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        try:
            return math.isfinite(value)
        except OverflowError:
            return False

    @staticmethod
    def _has_control(value: str) -> bool:
        return any(
            unicodedata.category(char).startswith("C") and char not in {"\n", "\t"}
            for char in value
        )


class FeatureContext:
    def __init__(
        self,
        *,
        request_id: str,
        customer_id: str,
        feature_id: str,
        config: dict[str, Any],
        secret_keys: set[str],
        data_source_path: str | None,
        cancel_file: str,
        event_token: str,
        report_schema: dict[str, Any] | None = None,
        report_max_items: int = DEFAULT_REPORT_MAX_ITEMS,
    ) -> None:
        self.request_id = request_id
        self.customer_id = customer_id
        self.feature_id = feature_id
        self.config = ConfigView(config, secret_keys)
        self.log = FeatureLogger(event_token)
        self.report = FeatureReport(event_token, report_schema, report_max_items)
        self._raw_config = dict(config)
        self._data_source_path = data_source_path
        self._cancel_file = cancel_file

    def debug(self, message: object, **context: Any) -> None:
        """Write a debug event through the platform logger."""
        self.log.debug(message, **context)

    def info(self, message: object, **context: Any) -> None:
        """Write an informational event through the platform logger."""
        self.log.info(message, **context)

    def warning(self, message: object, **context: Any) -> None:
        """Write a warning event through the platform logger."""
        self.log.warning(message, **context)

    def error(self, message: object, **context: Any) -> None:
        """Compatibility shortcut retained for existing feature packages."""
        self.log.error(message, **context)

    def get_data_source_path(self) -> Path | None:
        return Path(self._data_source_path) if self._data_source_path else None

    def raise_if_cancelled(self) -> None:
        if _cancellation.is_set() or os.path.exists(self._cancel_file):
            raise FeatureCancelled("任务已收到停止请求")

    def legacy_config(self) -> dict[str, Any]:
        return dict(self._raw_config)
