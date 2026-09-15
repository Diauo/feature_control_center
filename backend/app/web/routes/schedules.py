from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from app.application.errors import ApplicationError
from app.web.decorators import request_security, require_auth, require_session_csrf, services
from app.web.http import json_body, pagination_args, pagination_payload


blueprint = Blueprint("schedules", __name__)


@blueprint.get("/api/schedules")
@require_auth()
def list_schedules():
    scope = request.args.get("scope", "customer").strip().lower()
    customer_id = request.args.get("customerId", "").strip() or None
    if scope not in {"all", "customer"} or (scope == "customer" and customer_id is None):
        raise ApplicationError("CUSTOMER_SCOPE_INVALID", "客户范围无效", status=400)
    page, page_size = pagination_args()
    items, total = services().schedules.list(
        g.auth,
        customer_id if scope == "customer" else None,
        page=page,
        page_size=page_size,
    )
    return jsonify({"items": items, "pagination": pagination_payload(page, page_size, total)})


@blueprint.post("/api/schedules")
@require_auth()
@require_session_csrf
def create_schedule():
    body = json_body()
    enabled = body.get("isEnabled", True)
    if not isinstance(enabled, bool):
        raise ApplicationError("INVALID_SCHEDULE_ENABLED", "启用状态必须是布尔值", status=400)
    task = services().schedules.create(
        actor=g.auth,
        customer_id=str(body.get("customerId", "")),
        customer_feature_id=str(body.get("customerFeatureId", "")),
        name=str(body.get("name", "")),
        cron_expression=str(body.get("cronExpression", "")),
        is_enabled=enabled,
        request=request_security().metadata(request),
    )
    return jsonify({"schedule": task}), 201


@blueprint.put("/api/schedules/<task_id>")
@require_auth()
@require_session_csrf
def update_schedule(task_id: str):
    body = json_body()
    enabled = body.get("isEnabled")
    if not isinstance(enabled, bool):
        raise ApplicationError("INVALID_SCHEDULE_ENABLED", "启用状态必须是布尔值", status=400)
    task = services().schedules.update(
        actor=g.auth,
        task_id=task_id,
        name=str(body.get("name", "")),
        cron_expression=str(body.get("cronExpression", "")),
        is_enabled=enabled,
        request=request_security().metadata(request),
    )
    return jsonify({"schedule": task})


@blueprint.delete("/api/schedules/<task_id>")
@require_auth()
@require_session_csrf
def delete_schedule(task_id: str):
    services().schedules.delete(
        actor=g.auth,
        task_id=task_id,
        request=request_security().metadata(request),
    )
    return "", 204
