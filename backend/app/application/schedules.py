from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import CroniterBadCronError, CroniterBadDateError, croniter
from sqlalchemy import func, select

from app.application.audit import RequestMetadata, add_audit
from app.application.auth import AuthContext
from app.application.errors import AuthorizationError, ConflictError
from app.application.runs import RunService
from app.application.settings import SettingsService
from app.domain.identity import UserRole
from app.domain.time import Clock
from app.infrastructure.database import Database
from app.infrastructure.models import (
    CustomerFeatureModel,
    CustomerModel,
    ScheduledTaskModel,
    UserCustomerModel,
)


_EXPECTED_SCHEDULING_ERRORS = frozenset(
    {
        "CUSTOMER_FEATURE_NOT_FOUND",
        "CUSTOMER_NOT_AVAILABLE",
        "FEATURE_DELETED",
        "FEATURE_NOT_RUNNABLE",
        "FEATURE_VERSION_NOT_READY",
        "FEATURE_ENVIRONMENT_NOT_READY",
        "FEATURE_CONFIG_INCOMPLETE",
        "DATA_SOURCE_SNAPSHOT_INVALID",
        "DATA_SOURCE_REQUIRED",
        "SYSTEM_UPDATE_IN_PROGRESS",
    }
)


class CronSchedule:
    """Five-field cron calculation with an explicit IANA timezone."""

    @staticmethod
    def normalize(expression: str) -> str:
        normalized = " ".join(expression.strip().split())
        if not 1 <= len(normalized) <= 120 or len(normalized.split(" ")) != 5:
            raise ConflictError("INVALID_CRON", "Cron 必须是标准的 5 段表达式")
        try:
            valid = croniter.is_valid(normalized)
        except (CroniterBadCronError, ValueError, KeyError) as exc:
            raise ConflictError("INVALID_CRON", "Cron 表达式无效") from exc
        if not valid:
            raise ConflictError("INVALID_CRON", "Cron 表达式无效")
        return normalized

    @staticmethod
    def next_after(expression: str, base_epoch: int, timezone_name: str) -> int:
        try:
            timezone = ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ConflictError("INVALID_TIMEZONE", "系统时区无效，请先在系统设置中修正") from exc
        local_base = datetime.fromtimestamp(base_epoch, tz=UTC).astimezone(timezone)
        try:
            upcoming = croniter(
                expression,
                local_base,
                max_years_between_matches=5,
            ).get_next(datetime)
        except (CroniterBadCronError, CroniterBadDateError, OverflowError, ValueError) as exc:
            raise ConflictError("CRON_NEXT_RUN_UNAVAILABLE", "未来 5 年内没有可计算的执行时间") from exc
        if upcoming.tzinfo is None:
            upcoming = upcoming.replace(tzinfo=timezone)
        return int(upcoming.timestamp())


class ScheduleService:
    def __init__(
        self,
        database: Database,
        settings: SettingsService,
        clock: Clock,
        runs: RunService,
    ) -> None:
        self.database = database
        self.settings = settings
        self.clock = clock
        self.runs = runs

    def list(
        self,
        actor: AuthContext,
        customer_id: str | None,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        with self.database.session() as db:
            statement = select(ScheduledTaskModel)
            if customer_id:
                self._require_customer_access(db, actor, customer_id, require_active=False)
                statement = statement.where(ScheduledTaskModel.customer_id == customer_id)
            else:
                statement = statement.join(
                    CustomerModel,
                    CustomerModel.id == ScheduledTaskModel.customer_id,
                ).where(CustomerModel.is_active.is_(True))
                if actor.role is not UserRole.ADMIN:
                    statement = statement.join(
                        UserCustomerModel,
                        UserCustomerModel.customer_id == ScheduledTaskModel.customer_id,
                    ).where(UserCustomerModel.user_id == actor.user_id)
            total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
            rows = db.scalars(
                statement.order_by(ScheduledTaskModel.created_at.desc(), ScheduledTaskModel.name)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            return [self._task_dict(db, row) for row in rows], total

    def create(
        self,
        *,
        actor: AuthContext,
        customer_id: str,
        customer_feature_id: str,
        name: str,
        cron_expression: str,
        is_enabled: bool,
        request: RequestMetadata,
    ) -> dict[str, Any]:
        normalized_name = self._name(name)
        normalized_cron = CronSchedule.normalize(cron_expression)
        if not isinstance(is_enabled, bool):
            raise ConflictError("INVALID_SCHEDULE_ENABLED", "启用状态必须是布尔值")
        now = self.clock.now()
        timezone_name = self.settings.timezone_name()
        next_run_at = CronSchedule.next_after(normalized_cron, now, timezone_name) if is_enabled else None
        with self.database.session() as db:
            self._require_customer_access(db, actor, customer_id, require_active=True)
            feature = db.get(CustomerFeatureModel, customer_feature_id)
            if feature is None or feature.customer_id != customer_id:
                raise ConflictError("CUSTOMER_FEATURE_NOT_FOUND", "所选功能不属于当前客户", status=404)
            task = ScheduledTaskModel(
                id=uuid.uuid4().hex,
                customer_id=customer_id,
                customer_feature_id=customer_feature_id,
                name=normalized_name,
                cron_expression=normalized_cron,
                timezone=timezone_name,
                is_enabled=is_enabled,
                next_run_at=next_run_at,
                last_scheduled_for=None,
                last_handled_at=None,
                last_run_request_id=None,
                last_outcome=None,
                last_message=None,
                missed_count=0,
                created_at=now,
                updated_at=now,
                created_by=actor.user_id,
            )
            db.add(task)
            add_audit(
                db,
                now=now,
                request=request,
                action="schedule.create",
                outcome="success",
                actor_user_id=actor.user_id,
                session_id=actor.session_id,
                target_type="scheduled_task",
                target_id=task.id,
                details={"customerId": customer_id, "customerFeatureId": customer_feature_id},
            )
            db.flush()
            return self._task_dict(db, task)

    def update(
        self,
        *,
        actor: AuthContext,
        task_id: str,
        name: str,
        cron_expression: str,
        is_enabled: bool,
        request: RequestMetadata,
    ) -> dict[str, Any]:
        normalized_name = self._name(name)
        normalized_cron = CronSchedule.normalize(cron_expression)
        if not isinstance(is_enabled, bool):
            raise ConflictError("INVALID_SCHEDULE_ENABLED", "启用状态必须是布尔值")
        now = self.clock.now()
        timezone_name = self.settings.timezone_name()
        next_run_at = CronSchedule.next_after(normalized_cron, now, timezone_name) if is_enabled else None
        with self.database.session() as db:
            task = db.get(ScheduledTaskModel, task_id)
            if task is None:
                raise ConflictError("SCHEDULE_NOT_FOUND", "定时任务不存在", status=404)
            self._require_customer_access(db, actor, task.customer_id, require_active=True)
            task.name = normalized_name
            task.cron_expression = normalized_cron
            task.timezone = timezone_name
            task.is_enabled = is_enabled
            task.next_run_at = next_run_at
            task.updated_at = now
            add_audit(
                db,
                now=now,
                request=request,
                action="schedule.update",
                outcome="success",
                actor_user_id=actor.user_id,
                session_id=actor.session_id,
                target_type="scheduled_task",
                target_id=task.id,
                details={"enabled": is_enabled, "cron": normalized_cron},
            )
            db.flush()
            return self._task_dict(db, task)

    def delete(
        self,
        *,
        actor: AuthContext,
        task_id: str,
        request: RequestMetadata,
    ) -> None:
        now = self.clock.now()
        with self.database.session() as db:
            task = db.get(ScheduledTaskModel, task_id)
            if task is None:
                raise ConflictError("SCHEDULE_NOT_FOUND", "定时任务不存在", status=404)
            self._require_customer_access(db, actor, task.customer_id, require_active=True)
            details = {
                "customerId": task.customer_id,
                "customerFeatureId": task.customer_feature_id,
                "name": task.name,
            }
            db.delete(task)
            add_audit(
                db,
                now=now,
                request=request,
                action="schedule.delete",
                outcome="success",
                actor_user_id=actor.user_id,
                session_id=actor.session_id,
                target_type="scheduled_task",
                target_id=task_id,
                details=details,
            )

    def reconcile_timezone(self) -> int:
        """Move schedules to the configured timezone without replaying old occurrences."""
        now = self.clock.now()
        timezone_name = self.settings.timezone_name()
        changed = 0
        with self.database.session() as db:
            rows = db.scalars(
                select(ScheduledTaskModel).where(ScheduledTaskModel.timezone != timezone_name)
            ).all()
            for task in rows:
                task.timezone = timezone_name
                task.next_run_at = (
                    CronSchedule.next_after(task.cron_expression, now, timezone_name)
                    if task.is_enabled
                    else None
                )
                task.updated_at = now
                changed += 1
        return changed

    def due_ids(self, *, now: int | None = None, limit: int = 100) -> list[str]:
        current = self.clock.now() if now is None else now
        with self.database.session() as db:
            return list(
                db.scalars(
                    select(ScheduledTaskModel.id)
                    .where(
                        ScheduledTaskModel.is_enabled.is_(True),
                        ScheduledTaskModel.next_run_at.is_not(None),
                        ScheduledTaskModel.next_run_at <= current,
                    )
                    .order_by(ScheduledTaskModel.next_run_at, ScheduledTaskModel.id)
                    .limit(max(1, min(limit, 500)))
                )
            )

    def handle_due(self, task_id: str) -> dict[str, Any] | None:
        """Handle one occurrence. Advancing separately makes run creation crash-idempotent."""
        now = self.clock.now()
        with self.database.session() as db:
            task = db.get(ScheduledTaskModel, task_id)
            if task is None or not task.is_enabled or task.next_run_at is None or task.next_run_at > now:
                return None
            due_at = task.next_run_at
            customer_feature_id = task.customer_feature_id
            expression = task.cron_expression
            timezone_name = task.timezone

        grace = self.settings.scheduler().misfire_grace_seconds
        request_id: str | None = None
        if now - due_at > grace:
            outcome = "MISSED"
            message = f"系统离线或调度延迟超过 {grace} 秒，本次不补跑"
            missed = True
        else:
            missed = False
            try:
                run, duplicate = self.runs.create_scheduled_run(
                    customer_feature_id=customer_feature_id,
                    schedule_id=task_id,
                    scheduled_for=due_at,
                )
                request_id = str(run["requestId"])
                outcome = "DUPLICATE" if duplicate else "ENQUEUED"
                message = "该时点已创建过任务，已完成防重复处理" if duplicate else "任务已进入执行队列"
            except ConflictError as exc:
                if exc.code == "FEATURE_RUN_ACTIVE":
                    outcome = "SKIPPED_ACTIVE"
                    message = "同一客户功能已有任务在处理，本次已跳过"
                elif exc.code == "RUN_QUEUE_FULL":
                    outcome = "QUEUE_FULL"
                    message = "运行队列已满，本次已跳过"
                elif exc.code in _EXPECTED_SCHEDULING_ERRORS:
                    outcome = "SKIPPED_UNAVAILABLE"
                    message = exc.message
                else:
                    raise

        next_run_at = CronSchedule.next_after(expression, now, timezone_name)
        with self.database.session() as db:
            task = db.get(ScheduledTaskModel, task_id)
            if task is None or not task.is_enabled or task.next_run_at != due_at:
                return None
            task.next_run_at = next_run_at
            task.last_scheduled_for = due_at
            task.last_handled_at = now
            task.last_run_request_id = request_id
            task.last_outcome = outcome
            task.last_message = message[:500]
            if missed:
                task.missed_count += 1
            task.updated_at = now
            db.flush()
            return self._task_dict(db, task)

    @staticmethod
    def _name(name: str) -> str:
        normalized = name.strip()
        if not 1 <= len(normalized) <= 120:
            raise ConflictError("INVALID_SCHEDULE_NAME", "定时任务名称必须是 1 到 120 个字符")
        return normalized

    @staticmethod
    def _require_customer_access(
        db: Any,
        actor: AuthContext,
        customer_id: str,
        *,
        require_active: bool,
    ) -> CustomerModel:
        customer = db.get(CustomerModel, customer_id)
        if customer is None or (require_active and not customer.is_active):
            raise ConflictError("CUSTOMER_NOT_AVAILABLE", "客户不存在或已停用", status=404)
        if actor.role is not UserRole.ADMIN and db.get(UserCustomerModel, (actor.user_id, customer_id)) is None:
            raise AuthorizationError("CUSTOMER_ACCESS_DENIED", "无权访问这个客户", status=403)
        return customer

    @staticmethod
    def _task_dict(db: Any, task: ScheduledTaskModel) -> dict[str, Any]:
        feature = db.get(CustomerFeatureModel, task.customer_feature_id)
        customer = db.get(CustomerModel, task.customer_id)
        return {
            "id": task.id,
            "customerId": task.customer_id,
            "customerName": customer.name if customer else "",
            "customerFeatureId": task.customer_feature_id,
            "featureName": feature.display_name if feature is not None else "已删除功能",
            "featureStatus": feature.status if feature is not None else "MISSING",
            "name": task.name,
            "cronExpression": task.cron_expression,
            "timezone": task.timezone,
            "isEnabled": task.is_enabled,
            "nextRunAt": task.next_run_at,
            "lastScheduledFor": task.last_scheduled_for,
            "lastHandledAt": task.last_handled_at,
            "lastRunRequestId": task.last_run_request_id,
            "lastOutcome": task.last_outcome,
            "lastMessage": task.last_message,
            "missedCount": task.missed_count,
            "createdAt": task.created_at,
            "updatedAt": task.updated_at,
        }
