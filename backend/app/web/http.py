from __future__ import annotations

from typing import Any

from flask import Response, jsonify, request

from app.application.auth import IssuedSession
from app.application.errors import ApplicationError
from app.web.decorators import request_security, services


def pagination_args(*, default_size: int = 20, maximum_size: int = 100) -> tuple[int, int]:
    try:
        page = int(request.args.get("page", "1"))
        page_size = int(request.args.get("pageSize", str(default_size)))
    except ValueError as exc:
        raise ApplicationError("INVALID_PAGINATION", "页码和每页数量必须是整数", status=400) from exc
    if page < 1 or page_size < 1 or page_size > maximum_size:
        raise ApplicationError(
            "INVALID_PAGINATION",
            f"页码必须大于 0，每页数量必须在 1 到 {maximum_size} 之间",
            status=400,
        )
    return page, page_size


def pagination_payload(page: int, page_size: int, total: int) -> dict[str, int]:
    total_pages = max(1, (total + page_size - 1) // page_size)
    return {"page": page, "pageSize": page_size, "total": total, "totalPages": total_pages}


def json_body() -> dict[str, Any]:
    if not request.is_json:
        raise ApplicationError("JSON_REQUIRED", "请求必须使用 JSON 格式", status=415)
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise ApplicationError("INVALID_JSON", "请求 JSON 格式无效")
    return value


def ensure_session_transport() -> None:
    state = request_security().resolve(request)
    if services().settings.security().deployment_mode == "PUBLIC_HTTPS" and not state.secure:
        raise ApplicationError("HTTPS_REQUIRED", "公网模式只允许通过 HTTPS 登录", status=400)


def set_session_cookie(response: Response, issued: IssuedSession) -> None:
    state = request_security().resolve(request)
    cookie_name = "__Host-fcc_session" if state.secure else "fcc_session"
    max_age = max(1, issued.absolute_expires_at - services().clock.now())
    response.set_cookie(
        cookie_name,
        issued.token,
        max_age=max_age,
        secure=state.secure,
        httponly=True,
        samesite="Lax",
        path="/",
    )
    stale_name = "fcc_session" if state.secure else "__Host-fcc_session"
    response.delete_cookie(stale_name, path="/", secure=not state.secure, httponly=True, samesite="Lax")


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie("fcc_session", path="/", secure=False, httponly=True, samesite="Lax")
    response.delete_cookie("__Host-fcc_session", path="/", secure=True, httponly=True, samesite="Lax")


def session_response(issued: IssuedSession, payload: dict[str, Any] | None = None, status: int = 200) -> Response:
    data = payload or {}
    data["csrfToken"] = issued.csrf_token
    response = jsonify(data)
    response.status_code = status
    set_session_cookie(response, issued)
    return response
