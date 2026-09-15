from __future__ import annotations

import ipaddress
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

from flask import current_app, g, request

from app.application.auth import AuthContext
from app.application.audit import add_audit
from app.application.errors import AuthenticationError, AuthorizationError
from app.domain.identity import UserRole
from app.web.request_security import RequestSecurityResolver
from app.web.services import Services


F = TypeVar("F", bound=Callable[..., Any])


def services() -> Services:
    return cast(Services, current_app.extensions["fcc_services"])


def request_security() -> RequestSecurityResolver:
    return cast(RequestSecurityResolver, current_app.extensions["fcc_request_security"])


def current_token() -> str | None:
    secure = request_security().resolve(request).secure
    if services().settings.security().deployment_mode == "PUBLIC_HTTPS" and not secure:
        return None
    cookie_name = "__Host-fcc_session" if secure else "fcc_session"
    return request.cookies.get(cookie_name)


def optional_auth() -> AuthContext | None:
    existing = getattr(g, "auth", None)
    if existing is not None:
        return cast(AuthContext, existing)
    context = services().auth.authenticate(current_token())
    if context is not None:
        g.auth = context
    return context


def require_auth(*, allow_password_change: bool = False) -> Callable[[F], F]:
    def decorator(function: F) -> F:
        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any):
            context = optional_auth()
            if context is None:
                raise AuthenticationError("AUTHENTICATION_REQUIRED", "请先登录", status=401)
            if context.must_change_password and not allow_password_change:
                raise AuthenticationError("PASSWORD_CHANGE_REQUIRED", "首次登录需要先修改密码", status=403)
            return function(*args, **kwargs)

        return cast(F, wrapped)

    return decorator


def require_admin(function: F) -> F:
    @wraps(function)
    @require_auth()
    def wrapped(*args: Any, **kwargs: Any):
        context = cast(AuthContext, g.auth)
        if context.role is not UserRole.ADMIN:
            raise AuthorizationError("ADMIN_REQUIRED", "需要系统管理员权限", status=403)
        return function(*args, **kwargs)

    return cast(F, wrapped)


def require_management_network(function: F) -> F:
    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any):
        setting = services().settings.management_network()
        if setting.mode == "TRUSTED_NETWORKS":
            security = request_security().resolve(request)
            try:
                address = ipaddress.ip_address(security.client_ip)
                networks = [ipaddress.ip_network(value, strict=True) for value in setting.trusted_cidrs]
            except ValueError:
                networks = []
                address = None
            if address is None or not any(address in network for network in networks):
                context = cast(AuthContext, g.auth)
                metadata = request_security().metadata(request)
                with services().database.session() as db:
                    add_audit(
                        db,
                        now=services().clock.now(),
                        request=metadata,
                        action="security.management_network.denied",
                        outcome="denied",
                        actor_user_id=context.user_id,
                        session_id=context.session_id,
                        target_type="management_area",
                        target_id=request.path[:64],
                    )
                raise AuthorizationError(
                    "MANAGEMENT_NETWORK_REQUIRED",
                    "当前网络不能访问后台管理区",
                    status=403,
                    details={"clientIp": security.client_ip},
                )
        return function(*args, **kwargs)

    return cast(F, wrapped)


def require_session_csrf(function: F) -> F:
    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any):
        context = cast(AuthContext | None, getattr(g, "auth", None))
        if context is None or not services().auth.verify_csrf(context, request.headers.get("X-CSRF-Token")):
            raise AuthorizationError("CSRF_INVALID", "安全校验已失效，请刷新页面后重试", status=403)
        _validate_origin()
        return function(*args, **kwargs)

    return cast(F, wrapped)


def require_preauth_csrf(function: F) -> F:
    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any):
        token = request.headers.get("X-CSRF-Token", "")
        if not services().preauth_csrf.validate(token, services().clock.now()):
            raise AuthorizationError("CSRF_INVALID", "安全校验已失效，请刷新页面后重试", status=403)
        _validate_origin()
        return function(*args, **kwargs)

    return cast(F, wrapped)


def _validate_origin() -> None:
    origin = request.headers.get("Origin")
    if not origin:
        return
    security = request_security().resolve(request)
    scheme = "https" if security.secure else "http"
    expected = f"{scheme}://{request.host}"
    if origin.rstrip("/") != expected:
        raise AuthorizationError("ORIGIN_INVALID", "请求来源无效", status=403)
