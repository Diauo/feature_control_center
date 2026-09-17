from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.application.audit import RequestMetadata, add_audit
from app.application.auth import AuthContext
from app.application.errors import AuthorizationError, ConflictError
from app.application.report_export import build_report_workbook
from app.application.settings import SettingsService
from app.domain.identity import UserRole
from app.domain.time import Clock
from app.infrastructure.database import Database
from app.infrastructure.models import (
    CustomerFeatureDataSourceRevisionModel,
    CustomerFeatureModel,
    CustomerModel,
    FeatureConfigValueModel,
    FeatureVersionModel,
    RunEventModel,
    RunModel,
    RunReportItemModel,
    RunReportModel,
    RuntimeEnvironmentModel,
    SystemUpdateModel,
    UserCustomerModel,
)
from app.security.config_cipher import ConfigCipher
from app.security.run_snapshot_cipher import RunSnapshotCipher


TERMINAL_RUN_STATUSES = frozenset({"SUCCEEDED", "FAILED", "STOPPED", "TIMED_OUT", "INTERRUPTED"})
ACTIVE_RUN_STATUSES = frozenset({"QUEUED", "STARTING", "RUNNING", "STOPPING"})


class RunService:
    def __init__(
        self,
        database: Database,
        settings: SettingsService,
        clock: Clock,
        config_cipher: ConfigCipher,
        snapshot_cipher: RunSnapshotCipher,
    ) -> None:
        self.database = database
        self.settings = settings
        self.clock = clock
        self.config_cipher = config_cipher
        self.snapshot_cipher = snapshot_cipher

    def create_manual_run(
        self,
        *,
        actor: AuthContext,
        customer_feature_id: str,
        request: RequestMetadata,
    ) -> dict[str, Any]:
        """Freeze all mutable inputs and enqueue a run in one short transaction."""
        now = self.clock.now()
        runner_settings = self.settings.runner()
        with self.database.session() as db:
            feature = db.get(CustomerFeatureModel, customer_feature_id)
            if feature is None:
                raise ConflictError("CUSTOMER_FEATURE_NOT_FOUND", "客户功能不存在", status=404)
            self._require_customer_access(db, actor, feature.customer_id, require_active=True)
            run = self._enqueue_run(
                db,
                feature=feature,
                now=now,
                runner_settings=runner_settings,
                trigger_source="MANUAL",
                trigger_key=None,
                created_by=actor.user_id,
                scheduled_for=None,
            )
            add_audit(
                db,
                now=now,
                request=request,
                action="run.create",
                outcome="success",
                actor_user_id=actor.user_id,
                session_id=actor.session_id,
                target_type="run",
                target_id=run.request_id,
                details={"customerFeatureId": feature.id, "featureVersionId": run.feature_version_id},
            )
            db.flush()
            return self._run_dict(run)

    def create_scheduled_run(
        self,
        *,
        customer_feature_id: str,
        schedule_id: str,
        scheduled_for: int,
    ) -> tuple[dict[str, Any], bool]:
        """Create one idempotent scheduled run; the trigger key survives Scheduler restarts."""
        now = self.clock.now()
        trigger_key = f"schedule:{schedule_id}:{scheduled_for}"
        runner_settings = self.settings.runner()
        try:
            with self.database.session() as db:
                existing = db.scalar(select(RunModel).where(RunModel.trigger_key == trigger_key))
                if existing is not None:
                    return self._run_dict(existing), True
                feature = db.get(CustomerFeatureModel, customer_feature_id)
                if feature is None:
                    raise ConflictError("CUSTOMER_FEATURE_NOT_FOUND", "客户功能不存在", status=404)
                customer = db.get(CustomerModel, feature.customer_id)
                if customer is None or not customer.is_active:
                    raise ConflictError("CUSTOMER_NOT_AVAILABLE", "客户不存在或已停用", status=409)
                run = self._enqueue_run(
                    db,
                    feature=feature,
                    now=now,
                    runner_settings=runner_settings,
                    trigger_source="SCHEDULED",
                    trigger_key=trigger_key,
                    created_by=None,
                    scheduled_for=scheduled_for,
                )
                db.flush()
                return self._run_dict(run), False
        except ConflictError as exc:
            if exc.code != "FEATURE_RUN_ACTIVE":
                raise
            with self.database.session() as db:
                existing = db.scalar(select(RunModel).where(RunModel.trigger_key == trigger_key))
                if existing is not None:
                    return self._run_dict(existing), True
            raise

    def _enqueue_run(
        self,
        db: Any,
        *,
        feature: CustomerFeatureModel,
        now: int,
        runner_settings: Any,
        trigger_source: str,
        trigger_key: str | None,
        created_by: str | None,
        scheduled_for: int | None,
    ) -> RunModel:
        active_update = db.scalar(
            select(SystemUpdateModel.id).where(SystemUpdateModel.status.in_(("PENDING", "APPLYING"))).limit(1)
        )
        if active_update:
            raise ConflictError("SYSTEM_UPDATE_IN_PROGRESS", "系统正在更新或回退，暂时不能创建新任务", status=409)
        if feature.is_deleted:
            raise ConflictError("FEATURE_DELETED", "功能已删除，不能创建任务", status=409)
        if not feature.is_enabled or feature.status != "ACTIVE":
            raise ConflictError("FEATURE_NOT_RUNNABLE", "功能尚未满足运行条件", status=409)
        duplicate = db.scalar(
            select(RunModel.request_id).where(
                RunModel.customer_feature_id == feature.id,
                RunModel.status.in_(ACTIVE_RUN_STATUSES),
            )
        )
        if duplicate:
            raise ConflictError(
                "FEATURE_RUN_ACTIVE",
                "这个客户功能已经有任务在排队或运行",
                status=409,
                details={"requestId": duplicate},
            )
        queued = db.scalar(select(func.count(RunModel.request_id)).where(RunModel.status == "QUEUED")) or 0
        if queued >= runner_settings.max_queued_runs:
            raise ConflictError("RUN_QUEUE_FULL", "任务队列已满，请稍后再试", status=503)

        version = db.get(FeatureVersionModel, feature.feature_version_id)
        if version is None or version.status != "READY":
            raise ConflictError("FEATURE_VERSION_NOT_READY", "功能依赖尚未准备完成", status=409)
        if version.runtime_environment_id:
            environment = db.get(RuntimeEnvironmentModel, version.runtime_environment_id)
            if environment is None or environment.status != "READY" or not environment.environment_path:
                raise ConflictError("FEATURE_ENVIRONMENT_NOT_READY", "功能依赖环境不可用", status=409)

        schema = json.loads(version.config_schema_json)
        stored = {
            row.config_key: row
            for row in db.scalars(
                select(FeatureConfigValueModel).where(FeatureConfigValueModel.customer_feature_id == feature.id)
            )
        }
        config: dict[str, Any] = {}
        missing: list[str] = []
        secret_keys: list[str] = []
        for key, spec in schema.items():
            row = stored.get(key)
            if spec["type"] == "secret":
                secret_keys.append(key)
                if row is None or not row.encrypted_value:
                    if spec.get("required"):
                        missing.append(key)
                    continue
                config[key] = self.config_cipher.decrypt(feature.id, key, row.encrypted_value).decode("utf-8")
            elif row is not None and row.value_json is not None:
                config[key] = json.loads(row.value_json)
            elif "default" in spec:
                config[key] = spec["default"]
            elif spec.get("required"):
                missing.append(key)
            else:
                config[key] = None
        if missing:
            raise ConflictError(
                "FEATURE_CONFIG_INCOMPLETE",
                "功能仍有必填配置未设置",
                status=409,
                details={"keys": missing},
            )

        data_schema = json.loads(version.data_source_schema_json) if version.data_source_schema_json else None
        revision = None
        if feature.current_data_source_revision_id:
            revision = db.get(CustomerFeatureDataSourceRevisionModel, feature.current_data_source_revision_id)
            if revision is None or revision.customer_feature_id != feature.id:
                raise ConflictError("DATA_SOURCE_SNAPSHOT_INVALID", "当前数据源记录无效", status=409)
        if data_schema and data_schema.get("required") and revision is None:
            raise ConflictError("DATA_SOURCE_REQUIRED", "功能需要先上传数据源", status=409)

        request_id = uuid.uuid4().hex
        maximum = feature.max_runtime_seconds
        if maximum is None and runner_settings.default_max_runtime_seconds > 0:
            maximum = runner_settings.default_max_runtime_seconds
        run = RunModel(
            request_id=request_id,
            customer_id=feature.customer_id,
            customer_feature_id=feature.id,
            feature_version_id=version.id,
            data_source_revision_id=revision.id if revision else None,
            feature_name=feature.display_name,
            version_number=version.version_number,
            data_source_filename=revision.filename if revision else None,
            config_snapshot_ciphertext=self.snapshot_cipher.encrypt(request_id, config),
            secret_keys_json=json.dumps(secret_keys, ensure_ascii=False, separators=(",", ":")),
            trigger_source=trigger_source,
            trigger_key=trigger_key,
            status="QUEUED",
            queued_at=now,
            claimed_at=None,
            started_at=None,
            stop_requested_at=None,
            term_sent_at=None,
            kill_sent_at=None,
            finished_at=None,
            exit_code=None,
            process_id=None,
            failure_summary=None,
            stop_reason=None,
            runner_id=None,
            runner_heartbeat_at=None,
            created_by=created_by,
            max_runtime_seconds=maximum,
            last_event_sequence=1,
            final_event_sequence=None,
            logs_purged_at=None,
        )
        db.add(run)
        try:
            db.flush()
        except IntegrityError as exc:
            raise ConflictError("FEATURE_RUN_ACTIVE", "这个客户功能已经有任务在排队或运行", status=409) from exc
        context = {} if scheduled_for is None else {"scheduledFor": scheduled_for}
        db.add(
            RunEventModel(
                run_request_id=request_id,
                sequence=1,
                occurred_at_ms=now * 1000,
                level="INFO",
                source="PLATFORM",
                message="定时任务已进入执行队列" if trigger_source == "SCHEDULED" else "任务已进入执行队列",
                context_json=json.dumps(context, ensure_ascii=False, separators=(",", ":")),
            )
        )
        return run

    def request_stop(
        self,
        *,
        actor: AuthContext,
        request_id: str,
        request: RequestMetadata,
    ) -> dict[str, Any]:
        now = self.clock.now()
        with self.database.session() as db:
            run = db.get(RunModel, request_id)
            if run is None:
                raise ConflictError("RUN_NOT_FOUND", "任务不存在", status=404)
            self._require_customer_access(db, actor, run.customer_id, require_active=False)
            already_finished = run.status in TERMINAL_RUN_STATUSES
            if not already_finished and run.stop_requested_at is None:
                run.stop_requested_at = now
                run.stop_reason = "USER_REQUEST"
                run.status = "STOPPING"
            add_audit(
                db,
                now=now,
                request=request,
                action="run.stop.request",
                outcome="ignored" if already_finished else "success",
                actor_user_id=actor.user_id,
                session_id=actor.session_id,
                target_type="run",
                target_id=run.request_id,
                details={"alreadyFinished": already_finished},
            )
            db.flush()
            result = self._run_dict(run, report=db.get(RunReportModel, run.request_id))
            result["alreadyFinished"] = already_finished
            return result

    def list_runs(
        self,
        actor: AuthContext,
        *,
        customer_id: str | None,
        status: str | None = None,
        customer_feature_id: str | None = None,
        trigger_source: str | None = None,
        queued_from: int | None = None,
        queued_to: int | None = None,
        request_id_prefix: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        if queued_from is not None and queued_to is not None and queued_from > queued_to:
            raise ConflictError("INVALID_RUN_TIME_RANGE", "开始时间不能晚于结束时间")
        if trigger_source is not None and trigger_source not in {"MANUAL", "SCHEDULED"}:
            raise ConflictError("INVALID_TRIGGER_SOURCE", "触发来源筛选值无效")
        if request_id_prefix is not None:
            request_id_prefix = request_id_prefix.strip().lower()
            if not 1 <= len(request_id_prefix) <= 32 or any(
                char not in "0123456789abcdef" for char in request_id_prefix
            ):
                raise ConflictError("INVALID_REQUEST_ID", "请求 ID 必须是 1 到 32 位十六进制字符")
        with self.database.session() as db:
            statement = select(RunModel, CustomerModel.name).join(CustomerModel, CustomerModel.id == RunModel.customer_id)
            if customer_id:
                self._require_customer_access(db, actor, customer_id, require_active=False)
                statement = statement.where(RunModel.customer_id == customer_id)
            else:
                statement = statement.where(CustomerModel.is_active.is_(True))
                if actor.role is not UserRole.ADMIN:
                    statement = statement.join(
                        UserCustomerModel, UserCustomerModel.customer_id == RunModel.customer_id
                    ).where(UserCustomerModel.user_id == actor.user_id)
            if status:
                allowed = ACTIVE_RUN_STATUSES | TERMINAL_RUN_STATUSES
                if status not in allowed:
                    raise ConflictError("INVALID_RUN_STATUS", "任务状态筛选值无效")
                statement = statement.where(RunModel.status == status)
            if customer_feature_id:
                statement = statement.where(RunModel.customer_feature_id == customer_feature_id)
            if trigger_source:
                statement = statement.where(RunModel.trigger_source == trigger_source)
            if queued_from is not None:
                statement = statement.where(RunModel.queued_at >= queued_from)
            if queued_to is not None:
                statement = statement.where(RunModel.queued_at <= queued_to)
            if request_id_prefix:
                statement = statement.where(RunModel.request_id.startswith(request_id_prefix, autoescape=True))
            total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
            rows = db.execute(
                statement.order_by(RunModel.queued_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            request_ids = [item.request_id for item, _name in rows]
            reports = {
                report.run_request_id: report
                for report in db.scalars(
                    select(RunReportModel).where(RunReportModel.run_request_id.in_(request_ids))
                ).all()
            } if request_ids else {}
            return [
                self._run_dict(item, customer_name=name, report=reports.get(item.request_id))
                for item, name in rows
            ], total

    def get_run(self, actor: AuthContext, request_id: str) -> dict[str, Any]:
        with self.database.session() as db:
            run = self._authorized_run(db, actor, request_id)
            customer = db.get(CustomerModel, run.customer_id)
            report = db.get(RunReportModel, request_id)
            return self._run_dict(run, customer_name=customer.name if customer else "", report=report)

    def get_report(self, actor: AuthContext, request_id: str) -> dict[str, Any] | None:
        with self.database.session() as db:
            self._authorized_run(db, actor, request_id)
            report = db.get(RunReportModel, request_id)
            return self._report_dict(report) if report else None

    def list_report_items(
        self,
        actor: AuthContext,
        request_id: str,
        *,
        status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        if status is not None and status not in {"SUCCESS", "FAILED", "NO_DATA", "SKIPPED", "UNFINISHED"}:
            raise ConflictError("INVALID_REPORT_STATUS", "报表状态筛选值无效")
        with self.database.session() as db:
            self._authorized_run(db, actor, request_id)
            report = db.get(RunReportModel, request_id)
            if report is None:
                raise ConflictError("RUN_REPORT_NOT_FOUND", "这次运行没有结构化报表", status=404)
            if report.details_purged_at is not None:
                raise ConflictError(
                    "RUN_REPORT_DETAILS_PURGED",
                    "这次运行的报表明细已按日志保留策略自动清理",
                    status=410,
                    details={"purgedAt": report.details_purged_at},
                )
            statement = select(RunReportItemModel).where(RunReportItemModel.run_request_id == request_id)
            if status:
                statement = statement.where(RunReportItemModel.status == status)
            total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
            items = db.scalars(
                statement.order_by(RunReportItemModel.sequence)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            return [self._report_item_dict(item) for item in items], total

    def render_report(
        self,
        actor: AuthContext,
        request_id: str,
        request: RequestMetadata,
    ) -> tuple[str, bytes, str]:
        timezone_name = self.settings.timezone_name()
        with self.database.session() as db:
            run = self._authorized_run(db, actor, request_id)
            if run.status not in TERMINAL_RUN_STATUSES:
                raise ConflictError("RUN_REPORT_NOT_FINAL", "任务结束后才能下载最终报表", status=409)
            report = db.get(RunReportModel, request_id)
            if report is None:
                raise ConflictError("RUN_REPORT_NOT_FOUND", "这次运行没有结构化报表", status=404)
            if report.details_purged_at is not None:
                raise ConflictError(
                    "RUN_REPORT_DETAILS_PURGED",
                    "这次运行的报表明细已按日志保留策略自动清理",
                    status=410,
                    details={"purgedAt": report.details_purged_at},
                )
            customer = db.get(CustomerModel, run.customer_id)
            items = db.scalars(
                select(RunReportItemModel)
                .where(RunReportItemModel.run_request_id == request_id)
                .order_by(RunReportItemModel.sequence)
            ).all()
            schema = json.loads(report.schema_json)
            content = build_report_workbook(
                run=run,
                customer_name=customer.name if customer else "",
                report=report,
                schema=schema,
                items=list(items),
                timezone_name=timezone_name,
            )
            add_audit(
                db,
                now=self.clock.now(),
                request=request,
                action="run.report.download",
                outcome="success",
                actor_user_id=actor.user_id,
                session_id=actor.session_id,
                target_type="run",
                target_id=run.request_id,
                details={"format": "xlsx", "itemCount": report.reported_total, "complete": report.status == "COMPLETE"},
            )
            safe_customer = self._safe_report_filename(customer.name if customer else "客户")
            safe_feature = self._safe_report_filename(run.feature_name)
            return (
                f"{safe_customer}-{safe_feature}-{run.request_id}-最终报表.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    def get_events(
        self,
        actor: AuthContext,
        request_id: str,
        *,
        after: int = 0,
        limit: int = 500,
    ) -> dict[str, Any]:
        after = max(0, after)
        limit = max(1, min(limit, 500))
        with self.database.session() as db:
            run = self._authorized_run(db, actor, request_id)
            events = db.scalars(
                select(RunEventModel)
                .where(
                    RunEventModel.run_request_id == request_id,
                    RunEventModel.sequence > after,
                )
                .order_by(RunEventModel.sequence)
                .limit(limit)
            ).all()
            return {
                "items": [self._event_dict(item) for item in events],
                "latestSequence": run.last_event_sequence,
                "terminal": run.status in TERMINAL_RUN_STATUSES,
                "status": run.status,
                "logsPurgedAt": run.logs_purged_at,
            }

    def render_log(
        self,
        actor: AuthContext,
        request_id: str,
        output_format: str,
        request: RequestMetadata | None = None,
    ) -> tuple[str, bytes, str]:
        if output_format not in {"log", "jsonl"}:
            raise ConflictError("INVALID_LOG_FORMAT", "只支持 log 或 jsonl 格式", status=404)
        with self.database.session() as db:
            run = self._authorized_run(db, actor, request_id)
            if run.logs_purged_at is not None:
                raise ConflictError(
                    "RUN_LOGS_PURGED",
                    "这次任务的日志已按系统保留策略自动清理",
                    status=410,
                    details={"purgedAt": run.logs_purged_at},
                )
            events = db.scalars(
                select(RunEventModel)
                .where(RunEventModel.run_request_id == request_id)
                .order_by(RunEventModel.sequence)
            ).all()
            if output_format == "jsonl":
                body = "".join(
                    json.dumps(self._event_dict(item), ensure_ascii=False, separators=(",", ":")) + "\n"
                    for item in events
                ).encode("utf-8")
                if request is not None:
                    add_audit(db, now=self.clock.now(), request=request, action="run.log.download", outcome="success", actor_user_id=actor.user_id, session_id=actor.session_id, target_type="run", target_id=run.request_id, details={"format": output_format, "eventCount": len(events)})
                return f"{run.request_id}.jsonl", body, "application/x-ndjson"
            lines: list[str] = []
            for item in events:
                timestamp = datetime.fromtimestamp(item.occurred_at_ms / 1000, tz=UTC).isoformat(timespec="milliseconds")
                context = json.loads(item.context_json)
                suffix = "" if not context else " " + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
                lines.append(f"{timestamp} [{item.level}] [{item.source}] {item.message}{suffix}\n")
            if request is not None:
                add_audit(db, now=self.clock.now(), request=request, action="run.log.download", outcome="success", actor_user_id=actor.user_id, session_id=actor.session_id, target_type="run", target_id=run.request_id, details={"format": output_format, "eventCount": len(events)})
            return f"{run.request_id}.log", "".join(lines).encode("utf-8"), "text/plain; charset=utf-8"

    def authorize_stream(self, actor: AuthContext, request_id: str) -> None:
        with self.database.session() as db:
            self._authorized_run(db, actor, request_id)

    def _authorized_run(self, db: Any, actor: AuthContext, request_id: str) -> RunModel:
        run = db.get(RunModel, request_id)
        if run is None:
            raise ConflictError("RUN_NOT_FOUND", "任务不存在", status=404)
        self._require_customer_access(db, actor, run.customer_id, require_active=False)
        return run

    @staticmethod
    def _require_customer_access(
        db: Any,
        actor: AuthContext,
        customer_id: str,
        *,
        require_active: bool,
    ) -> None:
        customer = db.get(CustomerModel, customer_id)
        if customer is None or (require_active and not customer.is_active):
            raise ConflictError("CUSTOMER_NOT_AVAILABLE", "客户不存在或已停用", status=404)
        if actor.role is not UserRole.ADMIN and db.get(UserCustomerModel, (actor.user_id, customer_id)) is None:
            raise AuthorizationError("CUSTOMER_ACCESS_DENIED", "无权访问这个客户", status=403)

    @staticmethod
    def _run_dict(
        run: RunModel,
        *,
        customer_name: str = "",
        report: RunReportModel | None = None,
    ) -> dict[str, Any]:
        return {
            "requestId": run.request_id,
            "customerId": run.customer_id,
            "customerName": customer_name,
            "customerFeatureId": run.customer_feature_id,
            "featureVersionId": run.feature_version_id,
            "featureName": run.feature_name,
            "versionNumber": run.version_number,
            "dataSourceRevisionId": run.data_source_revision_id,
            "dataSourceFilename": run.data_source_filename,
            "triggerSource": run.trigger_source,
            "status": run.status,
            "queuedAt": run.queued_at,
            "claimedAt": run.claimed_at,
            "startedAt": run.started_at,
            "stopRequestedAt": run.stop_requested_at,
            "finishedAt": run.finished_at,
            "exitCode": run.exit_code,
            "failureSummary": run.failure_summary,
            "stopReason": run.stop_reason,
            "maxRuntimeSeconds": run.max_runtime_seconds,
            "latestSequence": run.last_event_sequence,
            "finalSequence": run.final_event_sequence,
            "logsPurgedAt": run.logs_purged_at,
            "report": RunService._report_dict(report) if report else None,
        }

    @staticmethod
    def _report_dict(report: RunReportModel) -> dict[str, Any]:
        schema = json.loads(report.schema_json)
        unreported = max((report.expected_total or report.reported_total) - report.reported_total, 0)
        total = max(report.expected_total or 0, report.reported_total)
        return {
            "title": report.title,
            "itemLabel": report.item_label,
            "columns": schema.get("columns", []),
            "status": report.status,
            "expectedTotal": report.expected_total,
            "reportedTotal": report.reported_total,
            "total": total,
            "successCount": report.success_count,
            "failedCount": report.failed_count,
            "noDataCount": report.no_data_count,
            "skippedCount": report.skipped_count,
            "unfinishedCount": report.unfinished_count + unreported,
            "unreportedCount": unreported,
            "validationErrorCount": report.validation_error_count,
            "startedAt": report.started_at,
            "completedAt": report.completed_at,
            "detailsPurgedAt": report.details_purged_at,
        }

    @staticmethod
    def _report_item_dict(item: RunReportItemModel) -> dict[str, Any]:
        return {
            "sequence": item.sequence,
            "status": item.status,
            "reason": item.reason,
            "values": json.loads(item.values_json),
            "reportedAtMs": item.reported_at_ms,
        }

    @staticmethod
    def _safe_report_filename(value: str) -> str:
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", value).strip(" .-")
        return cleaned[:80] or "报表"

    @staticmethod
    def _event_dict(event: RunEventModel) -> dict[str, Any]:
        return {
            "requestId": event.run_request_id,
            "sequence": event.sequence,
            "occurredAtMs": event.occurred_at_ms,
            "level": event.level,
            "source": event.source,
            "message": event.message,
            "context": json.loads(event.context_json),
        }
