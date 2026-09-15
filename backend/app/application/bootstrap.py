from __future__ import annotations

import json
import unicodedata
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.application.audit import RequestMetadata, add_audit
from app.application.auth import AuthService, IssuedSession
from app.application.errors import AuthenticationError, ConflictError
from app.domain.identity import clean_customer_name, clean_display_name, normalize_username
from app.domain.time import Clock
from app.infrastructure.database import Database
from app.infrastructure.instance_manager import InstanceManager
from app.infrastructure.models import (
    BootstrapStateModel,
    CustomerModel,
    SystemSettingModel,
    UserCustomerModel,
    UserModel,
)
from app.security.passwords import PasswordService


class BootstrapService:
    def __init__(
        self,
        database: Database,
        instance_manager: InstanceManager,
        auth: AuthService,
        passwords: PasswordService,
        clock: Clock,
        instance_key: bytes,
    ) -> None:
        self.database = database
        self.instance_manager = instance_manager
        self.auth = auth
        self.passwords = passwords
        self.clock = clock
        self.instance_key = instance_key

    def is_required(self) -> bool:
        with self.database.session() as db:
            return (db.scalar(select(func.count(UserModel.id))) or 0) == 0

    def initialize(
        self,
        *,
        bootstrap_code: str,
        system_name: str,
        admin_username: str,
        admin_display_name: str,
        password: str,
        customer_name: str,
        system_timezone: str = "Asia/Hong_Kong",
        request: RequestMetadata,
    ) -> IssuedSession:
        normalized_username = normalize_username(admin_username)
        username = unicodedata.normalize("NFKC", admin_username).strip()
        display_name = clean_display_name(admin_display_name)
        initial_customer_name = clean_customer_name(customer_name)
        clean_system_name = unicodedata.normalize("NFKC", system_name).strip()
        if not 1 <= len(clean_system_name) <= 80:
            raise ConflictError("INVALID_SYSTEM_NAME", "系统名称长度应为 1 到 80 个字符")
        clean_timezone = system_timezone.strip()
        try:
            ZoneInfo(clean_timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ConflictError("INVALID_TIMEZONE", "请选择有效的系统时区") from exc
        password_hash = self.passwords.hash(password)
        token_digest = self.instance_manager.bootstrap_digest(self.instance_key, bootstrap_code.strip())
        now = self.clock.now()
        issued: IssuedSession | None = None
        invalid_code = False

        try:
            with self.database.session() as db:
                claim = db.execute(
                    update(BootstrapStateModel)
                    .where(
                        BootstrapStateModel.id == 1,
                        BootstrapStateModel.used_at.is_(None),
                        BootstrapStateModel.token_digest == token_digest,
                    )
                    .values(used_at=now)
                )
                if claim.rowcount != 1:
                    invalid_code = True
                elif (db.scalar(select(func.count(UserModel.id))) or 0) != 0:
                    raise ConflictError("ALREADY_INITIALIZED", "系统已经完成初始化", status=409)

                if invalid_code:
                    add_audit(
                        db,
                        now=now,
                        request=request,
                        action="setup.initialize",
                        outcome="denied",
                        details={"reason": "invalid_bootstrap_code"},
                    )
                else:
                    user = UserModel(
                        id=uuid.uuid4().hex,
                        username=username,
                        username_normalized=normalized_username,
                        display_name=display_name,
                        password_hash=password_hash,
                        role="admin",
                        is_active=True,
                        must_change_password=False,
                        security_version=1,
                        created_at=now,
                        updated_at=now,
                        last_login_at=now,
                    )
                    customer = CustomerModel(
                        id=uuid.uuid4().hex,
                        name=initial_customer_name,
                        name_normalized=initial_customer_name.casefold(),
                        description="首次初始化创建",
                        is_active=True,
                        created_at=now,
                        updated_at=now,
                    )
                    db.add_all([user, customer])
                    db.flush()
                    db.add(
                        UserCustomerModel(
                            user_id=user.id,
                            customer_id=customer.id,
                            created_by=user.id,
                            created_at=now,
                        )
                    )
                    setting = db.get(SystemSettingModel, "system.name")
                    if setting is not None:
                        setting.value_json = json.dumps(clean_system_name, ensure_ascii=False)
                        setting.updated_at = now
                        setting.updated_by = user.id
                    timezone_setting = db.get(SystemSettingModel, "system.timezone")
                    if timezone_setting is not None:
                        timezone_setting.value_json = json.dumps(clean_timezone)
                        timezone_setting.updated_at = now
                        timezone_setting.updated_by = user.id
                    issued = self.auth.issue_session_in_transaction(
                        db,
                        user,
                        request,
                        now,
                        reauthenticated=True,
                    )
                    add_audit(
                        db,
                        now=now,
                        request=request,
                        action="setup.initialize",
                        outcome="success",
                        actor_user_id=user.id,
                        session_id=issued.context.session_id,
                        target_type="instance",
                        target_id="primary",
                        details={"initialCustomerId": customer.id, "systemTimezone": clean_timezone},
                    )
        except IntegrityError as exc:
            raise ConflictError("INITIALIZATION_CONFLICT", "初始化数据发生冲突，请刷新后重试", status=409) from exc

        if invalid_code:
            raise AuthenticationError("INVALID_BOOTSTRAP_CODE", "初始化码无效", status=401)
        if issued is None:
            raise ConflictError("INITIALIZATION_FAILED", "初始化未完成", status=409)
        self.instance_manager.mark_bootstrap_file_consumed()
        return issued
