from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from app.domain.report_limits import normalize_report_max_items
from app.infrastructure.database import Database
from app.infrastructure.models import RunModel, RunReportItemModel, RunReportModel


REPORT_STATUSES = frozenset({"SUCCESS", "FAILED", "NO_DATA", "SKIPPED", "UNFINISHED"})
_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_.-]{0,79}$")
_MAX_ITEM_BYTES = 12_000
_MAX_SAFE_INTEGER = 9_007_199_254_740_991


@dataclass(frozen=True, slots=True)
class ReportCommand:
    occurred_at_ms: int
    kind: str
    payload: dict[str, Any]


class ReportCommandError(ValueError):
    pass


class RunReportWriter:
    def __init__(self, database: Database) -> None:
        self.database = database

    def apply_batch(
        self,
        request_id: str,
        report_schema: dict[str, object] | None,
        commands: list[ReportCommand],
        max_items: int,
    ) -> list[str]:
        if not commands:
            return []
        warnings: list[str] = []
        effective_max_items = normalize_report_max_items(max_items)
        with self.database.session() as db:
            run = db.get(RunModel, request_id)
            if run is None:
                return []
            for command in commands:
                report = db.get(RunReportModel, request_id)
                try:
                    schema, columns = self._schema(report_schema)
                    if report is None:
                        report = RunReportModel(
                            run_request_id=request_id,
                            title=str(schema["title"]),
                            item_label=str(schema["item_label"]),
                            schema_json=json.dumps(schema, ensure_ascii=False, separators=(",", ":")),
                            expected_total=None,
                            reported_total=0,
                            success_count=0,
                            failed_count=0,
                            no_data_count=0,
                            skipped_count=0,
                            unfinished_count=0,
                            validation_error_count=0,
                            status="OPEN",
                            started_at=command.occurred_at_ms // 1000,
                            completion_requested_at=None,
                            completed_at=None,
                            details_purged_at=None,
                        )
                        db.add(report)
                        db.flush()
                    if report.status != "OPEN":
                        raise ReportCommandError("报表已经封存")
                    if command.kind == "report.start":
                        self._apply_start(report, command.payload, effective_max_items)
                    elif command.kind == "report.item":
                        self._apply_item(db, report, columns, command, effective_max_items)
                    elif command.kind == "report.complete":
                        if report.completion_requested_at is None:
                            report.completion_requested_at = command.occurred_at_ms // 1000
                    else:
                        raise ReportCommandError("报表指令类型无效")
                except ReportCommandError as exc:
                    if report is not None:
                        report.validation_error_count += 1
                    warnings.append(str(exc))
        if not warnings:
            return []
        unique = list(dict.fromkeys(warnings))
        preview = "；".join(unique[:3])
        if len(unique) > 3:
            preview += f"；另有 {len(unique) - 3} 类错误"
        return [f"结构化报表有 {len(warnings)} 条指令被拒绝：{preview}"]

    def seal(self, request_id: str, run_status: str, completed_at: int) -> None:
        with self.database.session() as db:
            report = db.get(RunReportModel, request_id)
            if report is None or report.status != "OPEN":
                return
            counts_match = report.expected_total is None or report.expected_total == report.reported_total
            report.status = (
                "COMPLETE"
                if run_status == "SUCCEEDED"
                and report.completion_requested_at is not None
                and report.validation_error_count == 0
                and counts_match
                else "INCOMPLETE"
            )
            report.completed_at = completed_at

    @staticmethod
    def _schema(value: dict[str, object] | None) -> tuple[dict[str, object], dict[str, str]]:
        if not isinstance(value, dict):
            raise ReportCommandError("功能包没有声明结构化报表")
        title = value.get("title")
        item_label = value.get("item_label")
        raw_columns = value.get("columns")
        if not isinstance(title, str) or not isinstance(item_label, str) or not isinstance(raw_columns, list):
            raise ReportCommandError("功能包报表声明无效")
        columns: dict[str, str] = {}
        for column in raw_columns:
            if not isinstance(column, dict) or not isinstance(column.get("key"), str):
                raise ReportCommandError("功能包报表字段声明无效")
            columns[str(column["key"])] = str(column.get("type", "string"))
        return value, columns

    @staticmethod
    def _apply_start(report: RunReportModel, payload: dict[str, Any], max_items: int) -> None:
        expected = payload.get("expectedTotal")
        if expected is not None and (
            isinstance(expected, bool) or not isinstance(expected, int) or not 0 <= expected <= max_items
        ):
            raise ReportCommandError(f"预计总数必须是 0 到 {max_items} 的整数")
        if report.expected_total is not None and expected is not None and report.expected_total != expected:
            raise ReportCommandError("预计总数不能重复修改")
        if expected is not None:
            report.expected_total = expected

    @staticmethod
    def _apply_item(
        db: Any,
        report: RunReportModel,
        columns: dict[str, str],
        command: ReportCommand,
        max_items: int,
    ) -> None:
        if report.reported_total >= max_items:
            raise ReportCommandError(f"单次运行最多保存 {max_items} 条报表明细")
        payload = command.payload
        status = str(payload.get("status", "")).strip().upper()
        if status not in REPORT_STATUSES:
            raise ReportCommandError("报表状态无效")
        reason = payload.get("reason", "")
        if not isinstance(reason, str) or len(reason) > 1_000 or RunReportWriter._has_control(reason):
            raise ReportCommandError("报表原因格式无效")
        reason_code = payload.get("reasonCode")
        if reason_code is not None:
            if not isinstance(reason_code, str) or not _REASON_CODE.fullmatch(reason_code):
                raise ReportCommandError("报表原因代码格式无效")
        values = payload.get("values")
        if not isinstance(values, dict):
            raise ReportCommandError("报表业务字段必须是字典")
        unknown = set(values) - set(columns)
        if unknown:
            raise ReportCommandError(f"报表包含未声明字段：{', '.join(sorted(map(str, unknown)))}")
        normalized: dict[str, Any] = {}
        for key, value in values.items():
            field_type = columns[key]
            if value is None:
                normalized[key] = None
            elif field_type == "string" and isinstance(value, str):
                if len(value) > 2_000 or RunReportWriter._has_control(value):
                    raise ReportCommandError(f"报表字段 {key} 内容无效或过长")
                normalized[key] = value
            elif (
                field_type == "integer"
                and isinstance(value, int)
                and not isinstance(value, bool)
                and abs(value) <= _MAX_SAFE_INTEGER
            ):
                normalized[key] = value
            elif field_type == "number" and RunReportWriter._is_finite_number(value):
                normalized[key] = value
            elif field_type == "boolean" and isinstance(value, bool):
                normalized[key] = value
            else:
                raise ReportCommandError(f"报表字段 {key} 类型无效")
        values_json = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if len(values_json.encode("utf-8")) > _MAX_ITEM_BYTES:
            raise ReportCommandError("单条报表明细超过 12 KiB 限制")

        sequence = report.reported_total + 1
        db.add(
            RunReportItemModel(
                run_request_id=report.run_request_id,
                sequence=sequence,
                status=status,
                reason=reason,
                reason_code=reason_code,
                values_json=values_json,
                reported_at_ms=command.occurred_at_ms,
            )
        )
        report.reported_total = sequence
        counter = {
            "SUCCESS": "success_count",
            "FAILED": "failed_count",
            "NO_DATA": "no_data_count",
            "SKIPPED": "skipped_count",
            "UNFINISHED": "unfinished_count",
        }[status]
        setattr(report, counter, getattr(report, counter) + 1)

    @staticmethod
    def _has_control(value: str) -> bool:
        return any(unicodedata.category(char).startswith("C") and char not in {"\n", "\t"} for char in value)

    @staticmethod
    def _is_finite_number(value: object) -> bool:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        try:
            return math.isfinite(value)
        except OverflowError:
            return False
