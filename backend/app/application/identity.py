from __future__ import annotations

import json
import unicodedata
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.application.audit import RequestMetadata, add_audit
from app.application.auth import AuthContext, AuthService
from app.application.errors import AuthorizationError, ConflictError
from app.domain.identity import (
    ALL_MENU_KEYS,
    DEFAULT_OPERATOR_MENUS,
    MenuKey,
    UserRole,
    clean_customer_name,
    clean_display_name,
    clean_menu_keys,
    normalize_username,
    ordered_menu_keys,
    parse_role,
)
from app.domain.time import Clock
from app.infrastructure.database import Database
from app.infrastructure.models import AuditLogModel, CustomerModel, SessionModel, UserCustomerModel, UserMenuGrantModel, UserModel
from app.security.crypto import generate_temporary_password
from app.security.passwords import PasswordService


@dataclass(frozen=True, slots=True)
class CreatedUser:
    user: dict[str, Any]
    temporary_password: str


class IdentityService:
    def __init__(
        self,
        database: Database,
        passwords: PasswordService,
        auth: AuthService,
        clock: Clock,
    ) -> None:
        self.database = database
        self.passwords = passwords
        self.auth = auth
        self.clock = clock

    def list_authorized_customers(self, context: AuthContext) -> list[dict[str, Any]]:
        with self.database.session() as db:
            query = select(CustomerModel).where(CustomerModel.is_active.is_(True)).order_by(CustomerModel.name)
            if context.role is not UserRole.ADMIN:
                query = query.join(UserCustomerModel).where(UserCustomerModel.user_id == context.user_id)
            customers = db.scalars(query).all()
            return [self._customer_dict(customer) for customer in customers]

    def list_users(
        self, actor: AuthContext, *, page: int = 1, page_size: int = 20, role: str = ""
    ) -> tuple[list[dict[str, Any]], int]:
        self._ensure_menu(actor, MenuKey.USERS)
        if role not in {"", "admin", "operator"}:
            raise ConflictError("INVALID_USER_ROLE_FILTER", "用户类型筛选值无效")
        with self.database.session() as db:
            statement = select(UserModel)
            count_statement = select(func.count(UserModel.id))
            if role in {"admin", "operator"}:
                statement = statement.where(UserModel.role == role)
                count_statement = count_statement.where(UserModel.role == role)
            total = int(db.scalar(count_statement) or 0)
            users = db.scalars(
                statement
                .options(selectinload(UserModel.customer_links), selectinload(UserModel.menu_grants))
                .order_by(UserModel.created_at)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            return [self._user_dict(user) for user in users], total

    def create_user(
        self,
        *,
        actor: AuthContext,
        username: str,
        display_name: str,
        role: str,
        menu_keys: list[str] | None = None,
        customer_ids: list[str],
        request: RequestMetadata,
    ) -> CreatedUser:
        self._ensure_menu(actor, MenuKey.USERS)
        self.auth.require_recent_auth(actor)
        normalized_username = normalize_username(username)
        clean_username = unicodedata.normalize("NFKC", username).strip()
        clean_name = clean_display_name(display_name)
        clean_role = parse_role(role)
        if clean_role is UserRole.OPERATOR:
            effective_menus = clean_menu_keys(menu_keys) if menu_keys is not None else list(DEFAULT_OPERATOR_MENUS)
        else:
            effective_menus = []
        unique_customer_ids = list(dict.fromkeys(customer_ids))
        temp_password = generate_temporary_password()
        now = self.clock.now()
        try:
            with self.database.session() as db:
                customers = self._require_customers(db, unique_customer_ids)
                user = UserModel(
                    id=uuid.uuid4().hex,
                    username=clean_username,
                    username_normalized=normalized_username,
                    display_name=clean_name,
                    password_hash=self.passwords.hash(temp_password),
                    role=clean_role.value,
                    is_active=True,
                    must_change_password=True,
                    security_version=1,
                    created_at=now,
                    updated_at=now,
                    last_login_at=None,
                )
                for customer in customers:
                    user.customer_links.append(
                        UserCustomerModel(
                            customer_id=customer.id,
                            created_by=actor.user_id,
                            created_at=now,
                        )
                    )
                for menu_key in effective_menus:
                    user.menu_grants.append(
                        UserMenuGrantModel(
                            menu_key=menu_key,
                            created_by=actor.user_id,
                            created_at=now,
                        )
                    )
                db.add(user)
                db.flush()
                add_audit(
                    db,
                    now=now,
                    request=request,
                    action="admin.user.create",
                    outcome="success",
                    actor_user_id=actor.user_id,
                    session_id=actor.session_id,
                    target_type="user",
                    target_id=user.id,
                    details={"role": clean_role.value, "customerCount": len(customers), "menus": effective_menus},
                )
                return CreatedUser(user=self._user_dict(user), temporary_password=temp_password)
        except IntegrityError as exc:
            raise ConflictError("USERNAME_EXISTS", "用户名已经存在", status=409) from exc

    def update_user(
        self,
        *,
        actor: AuthContext,
        user_id: str,
        display_name: str | None,
        role: str | None,
        is_active: bool | None,
        customer_ids: list[str] | None,
        menu_keys: list[str] | None = None,
        request: RequestMetadata,
    ) -> dict[str, Any]:
        self._ensure_menu(actor, MenuKey.USERS)
        self.auth.require_recent_auth(actor)
        now = self.clock.now()
        with self.database.session() as db:
            user = db.get(UserModel, user_id)
            if user is None:
                raise ConflictError("USER_NOT_FOUND", "用户不存在", status=404)
            new_role = parse_role(role).value if role is not None else user.role
            new_active = is_active if is_active is not None else user.is_active
            effective_menus: list[str] | None = None
            if new_role == UserRole.OPERATOR:
                if menu_keys is not None:
                    effective_menus = clean_menu_keys(menu_keys)
                elif not user.menu_grants:
                    effective_menus = list(DEFAULT_OPERATOR_MENUS)
            if user.id == actor.user_id and (new_role != "admin" or not new_active):
                raise ConflictError("CANNOT_DISABLE_SELF", "不能停用或降级当前登录管理员", status=409)
            if user.role == "admin" and user.is_active and (new_role != "admin" or not new_active):
                other_admins = db.scalar(
                    select(func.count(UserModel.id)).where(
                        UserModel.id != user.id,
                        UserModel.role == "admin",
                        UserModel.is_active.is_(True),
                    )
                )
                if not other_admins:
                    raise ConflictError("LAST_ADMIN", "系统必须保留至少一名启用的管理员", status=409)

            customers = None
            if customer_ids is not None:
                customers = self._require_customers(db, list(dict.fromkeys(customer_ids)))
            security_changed = new_role != user.role or new_active != user.is_active
            if display_name is not None:
                user.display_name = clean_display_name(display_name)
            user.role = new_role
            user.is_active = new_active
            user.updated_at = now
            if security_changed:
                user.security_version += 1
                self._revoke_sessions(db, user.id, now, "user_security_changed")
            if customers is not None:
                self._replace_customer_links(user, customers, actor.user_id, now)
                db.flush()
            if effective_menus is not None:
                self._replace_menu_grants(user, effective_menus, actor.user_id, now)
                db.flush()
            add_audit(
                db,
                now=now,
                request=request,
                action="admin.user.update",
                outcome="success",
                actor_user_id=actor.user_id,
                session_id=actor.session_id,
                target_type="user",
                target_id=user.id,
                details={
                    "role": user.role,
                    "isActive": user.is_active,
                    "customerCount": len(user.customer_links),
                    "menus": ordered_menu_keys(grant.menu_key for grant in user.menu_grants),
                },
            )
            return self._user_dict(user)

    def set_user_customers(
        self,
        *,
        actor: AuthContext,
        user_id: str,
        customer_ids: list[str],
        request: RequestMetadata,
    ) -> dict[str, Any]:
        self._ensure_menu(actor, MenuKey.USERS)
        self.auth.require_recent_auth(actor)
        now = self.clock.now()
        unique_customer_ids = list(dict.fromkeys(customer_ids))
        with self.database.session() as db:
            user = db.get(UserModel, user_id)
            if user is None:
                raise ConflictError("USER_NOT_FOUND", "用户不存在", status=404)
            customers = self._require_customers(db, unique_customer_ids)
            self._replace_customer_links(user, customers, actor.user_id, now)
            db.flush()
            add_audit(
                db,
                now=now,
                request=request,
                action="admin.user.customers.update",
                outcome="success",
                actor_user_id=actor.user_id,
                session_id=actor.session_id,
                target_type="user",
                target_id=user.id,
                details={"customerCount": len(customers)},
            )
            return self._user_dict(user)

    def reset_password(
        self,
        *,
        actor: AuthContext,
        user_id: str,
        request: RequestMetadata,
    ) -> str:
        self._ensure_menu(actor, MenuKey.USERS)
        self.auth.require_recent_auth(actor)
        if user_id == actor.user_id:
            raise ConflictError("USE_CHANGE_PASSWORD", "请通过个人密码修改入口更新当前账号密码", status=409)
        now = self.clock.now()
        temp_password = generate_temporary_password()
        with self.database.session() as db:
            user = db.get(UserModel, user_id)
            if user is None:
                raise ConflictError("USER_NOT_FOUND", "用户不存在", status=404)
            user.password_hash = self.passwords.hash(temp_password)
            user.must_change_password = True
            user.security_version += 1
            user.updated_at = now
            count = self._revoke_sessions(db, user.id, now, "password_reset")
            add_audit(
                db,
                now=now,
                request=request,
                action="admin.user.password.reset",
                outcome="success",
                actor_user_id=actor.user_id,
                session_id=actor.session_id,
                target_type="user",
                target_id=user.id,
                details={"revokedSessions": count},
            )
            return temp_password

    def delete_user(
        self,
        *,
        actor: AuthContext,
        user_id: str,
        request: RequestMetadata,
    ) -> dict[str, Any]:
        """硬删除业务员账号：管理员不可删除，历史审计保留账号快照。"""
        self._ensure_menu(actor, MenuKey.USERS)
        self.auth.require_recent_auth(actor, max_age_seconds=120)  # 高危操作：要求刚刚验证过密码
        if user_id == actor.user_id:
            raise ConflictError("CANNOT_DELETE_SELF", "不能删除当前登录账号", status=409)
        now = self.clock.now()
        with self.database.session() as db:
            user = db.get(UserModel, user_id)
            if user is None:
                raise ConflictError("USER_NOT_FOUND", "用户不存在", status=404)
            if user.role == UserRole.ADMIN:
                raise ConflictError("CANNOT_DELETE_ADMIN", "不能删除系统管理员账户", status=409)
            snapshot = {
                "username": user.username,
                "displayName": user.display_name,
                "role": user.role,
                "customerCount": len(user.customer_links),
            }
            db.execute(delete(SessionModel).where(SessionModel.user_id == user.id))
            add_audit(
                db,
                now=now,
                request=request,
                action="admin.user.delete",
                outcome="success",
                actor_user_id=actor.user_id,
                session_id=actor.session_id,
                target_type="user",
                target_id=user.id,
                details=snapshot,
            )
            db.delete(user)
            return {"deleted": True, "userId": user_id}

    def list_customers(self, actor: AuthContext, *, page: int = 1, page_size: int = 20) -> tuple[list[dict[str, Any]], int]:
        self._ensure_menu(actor, MenuKey.CUSTOMERS)
        with self.database.session() as db:
            total = int(db.scalar(select(func.count(CustomerModel.id))) or 0)
            customers = db.scalars(
                select(CustomerModel)
                .order_by(CustomerModel.created_at)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            return [self._customer_dict(customer) for customer in customers], total

    def create_customer(
        self,
        *,
        actor: AuthContext,
        name: str,
        description: str,
        request: RequestMetadata,
    ) -> dict[str, Any]:
        self._ensure_menu(actor, MenuKey.CUSTOMERS)
        self.auth.require_recent_auth(actor)
        clean_name = clean_customer_name(name)
        clean_description = description.strip()
        if len(clean_description) > 500:
            raise ConflictError("DESCRIPTION_TOO_LONG", "客户说明不能超过 500 个字符")
        now = self.clock.now()
        try:
            with self.database.session() as db:
                customer = CustomerModel(
                    id=uuid.uuid4().hex,
                    name=clean_name,
                    name_normalized=clean_name.casefold(),
                    description=clean_description,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
                db.add(customer)
                db.flush()
                add_audit(
                    db,
                    now=now,
                    request=request,
                    action="admin.customer.create",
                    outcome="success",
                    actor_user_id=actor.user_id,
                    session_id=actor.session_id,
                    target_type="customer",
                    target_id=customer.id,
                )
                return self._customer_dict(customer)
        except IntegrityError as exc:
            raise ConflictError("CUSTOMER_EXISTS", "客户名称已经存在", status=409) from exc

    def update_customer(
        self,
        *,
        actor: AuthContext,
        customer_id: str,
        name: str | None,
        description: str | None,
        is_active: bool | None,
        request: RequestMetadata,
    ) -> dict[str, Any]:
        self._ensure_menu(actor, MenuKey.CUSTOMERS)
        self.auth.require_recent_auth(actor)
        now = self.clock.now()
        try:
            with self.database.session() as db:
                customer = db.get(CustomerModel, customer_id)
                if customer is None:
                    raise ConflictError("CUSTOMER_NOT_FOUND", "客户不存在", status=404)
                if name is not None:
                    customer.name = clean_customer_name(name)
                    customer.name_normalized = customer.name.casefold()
                if description is not None:
                    clean_description = description.strip()
                    if len(clean_description) > 500:
                        raise ConflictError("DESCRIPTION_TOO_LONG", "客户说明不能超过 500 个字符")
                    customer.description = clean_description
                if is_active is not None:
                    customer.is_active = is_active
                customer.updated_at = now
                add_audit(
                    db,
                    now=now,
                    request=request,
                    action="admin.customer.update",
                    outcome="success",
                    actor_user_id=actor.user_id,
                    session_id=actor.session_id,
                    target_type="customer",
                    target_id=customer.id,
                    details={"isActive": customer.is_active},
                )
                return self._customer_dict(customer)
        except IntegrityError as exc:
            raise ConflictError("CUSTOMER_EXISTS", "客户名称已经存在", status=409) from exc

    def list_audit_logs(
        self,
        actor: AuthContext,
        *,
        page: int = 1,
        page_size: int = 20,
        category: str = "ALL",
        action: str = "",
        outcome: str = "",
        client_ip: str = "",
        occurred_from: int | None = None,
        occurred_to: int | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        self._ensure_menu(actor, MenuKey.AUDIT)
        if category not in {"ALL", "ADMIN", "OPERATOR", "AUTH_SYSTEM", "LEGACY"}:
            raise ConflictError("INVALID_AUDIT_CATEGORY", "审计分类筛选值无效")
        statement = select(AuditLogModel, UserModel.display_name).outerjoin(
            UserModel, AuditLogModel.actor_user_id == UserModel.id
        )
        if category == "ADMIN":
            statement = statement.where(AuditLogModel.actor_role == "admin")
        elif category == "OPERATOR":
            statement = statement.where(AuditLogModel.actor_role == "operator")
        elif category == "AUTH_SYSTEM":
            statement = statement.where(
                or_(
                    AuditLogModel.actor_user_id.is_(None),
                    AuditLogModel.action.like("auth.%"),
                    AuditLogModel.action.like("setup.%"),
                    AuditLogModel.action.like("recovery.%"),
                )
            )
        elif category == "LEGACY":
            statement = statement.where(AuditLogModel.actor_user_id.is_not(None), AuditLogModel.actor_role.is_(None))
        if action:
            statement = statement.where(AuditLogModel.action.contains(action[:100]))
        if outcome in {"success", "failure", "denied", "blocked", "ignored"}:
            statement = statement.where(AuditLogModel.outcome == outcome)
        if client_ip:
            statement = statement.where(AuditLogModel.client_ip.contains(client_ip[:64]))
        if occurred_from is not None:
            statement = statement.where(AuditLogModel.occurred_at >= occurred_from)
        if occurred_to is not None:
            statement = statement.where(AuditLogModel.occurred_at <= occurred_to)
        with self.database.session() as db:
            total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
            rows = db.execute(
                statement.order_by(AuditLogModel.id.desc()).offset((page - 1) * page_size).limit(page_size)
            ).all()
            items = [
                {
                    "id": audit.id,
                    "occurredAt": audit.occurred_at,
                    "actorUserId": audit.actor_user_id,
                    "actorRole": audit.actor_role,
                    "actorUsername": audit.actor_username,
                    "actorDisplayName": audit.actor_display_name or display_name,
                    "action": audit.action,
                    "outcome": audit.outcome,
                    "targetType": audit.target_type,
                    "targetId": audit.target_id,
                    "targetName": audit.target_name,
                    "customerId": audit.customer_id,
                    "customerName": audit.customer_name,
                    "clientIp": audit.client_ip,
                    "requestMethod": audit.request_method,
                    "requestPath": audit.request_path,
                    "requestId": audit.request_id,
                    "userAgent": audit.user_agent,
                    "details": json.loads(audit.details_json),
                }
                for audit, display_name in rows
            ]
            return items, total

    @staticmethod
    def _ensure_menu(actor: AuthContext, *menu_keys: str) -> None:
        if not actor.has_menu(*menu_keys):
            raise AuthorizationError("MENU_PERMISSION_REQUIRED", "当前账号没有访问该菜单的权限", status=403)

    @staticmethod
    def _require_customers(db: Any, customer_ids: list[str]) -> list[CustomerModel]:
        if not customer_ids:
            return []
        customers = list(
            db.scalars(
                select(CustomerModel).where(
                    CustomerModel.id.in_(customer_ids),
                    CustomerModel.is_active.is_(True),
                )
            )
        )
        if len(customers) != len(customer_ids):
            raise ConflictError("CUSTOMER_NOT_AVAILABLE", "选择的客户不存在或已停用", status=409)
        return customers

    @staticmethod
    def _revoke_sessions(db: Any, user_id: str, now: int, reason: str) -> int:
        sessions = list(
            db.scalars(select(SessionModel).where(SessionModel.user_id == user_id, SessionModel.revoked_at.is_(None)))
        )
        for session in sessions:
            session.revoked_at = now
            session.revoked_reason = reason
        return len(sessions)

    @staticmethod
    def _replace_customer_links(
        user: UserModel,
        customers: list[CustomerModel],
        actor_user_id: str,
        now: int,
    ) -> None:
        desired_ids = {customer.id for customer in customers}
        existing_ids = {link.customer_id for link in user.customer_links}
        for link in list(user.customer_links):
            if link.customer_id not in desired_ids:
                user.customer_links.remove(link)
        for customer in customers:
            if customer.id not in existing_ids:
                user.customer_links.append(
                    UserCustomerModel(
                        customer_id=customer.id,
                        created_by=actor_user_id,
                        created_at=now,
                    )
                )

    @staticmethod
    def _replace_menu_grants(
        user: UserModel,
        menu_keys: list[str],
        actor_user_id: str,
        now: int,
    ) -> None:
        desired = set(menu_keys)
        existing = {grant.menu_key for grant in user.menu_grants}
        for grant in list(user.menu_grants):
            if grant.menu_key not in desired:
                user.menu_grants.remove(grant)
        for menu_key in menu_keys:
            if menu_key not in existing:
                user.menu_grants.append(
                    UserMenuGrantModel(
                        menu_key=menu_key,
                        created_by=actor_user_id,
                        created_at=now,
                    )
                )

    @staticmethod
    def _user_dict(user: UserModel) -> dict[str, Any]:
        customer_ids = sorted(link.customer_id for link in user.customer_links)
        if user.role == UserRole.ADMIN:
            menu_keys = list(ALL_MENU_KEYS)
        else:
            menu_keys = ordered_menu_keys(grant.menu_key for grant in user.menu_grants)
        return {
            "id": user.id,
            "username": user.username,
            "displayName": user.display_name,
            "role": user.role,
            "isActive": user.is_active,
            "mustChangePassword": user.must_change_password,
            "customerIds": customer_ids,
            "menuKeys": menu_keys,
            "createdAt": user.created_at,
            "lastLoginAt": user.last_login_at,
        }

    @staticmethod
    def _customer_dict(customer: CustomerModel) -> dict[str, Any]:
        return {
            "id": customer.id,
            "name": customer.name,
            "description": customer.description,
            "isActive": customer.is_active,
            "createdAt": customer.created_at,
            "updatedAt": customer.updated_at,
        }
