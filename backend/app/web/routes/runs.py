from __future__ import annotations

import io
import json
import time

from flask import Blueprint, Response, g, jsonify, request, send_file, stream_with_context

from app.application.errors import ApplicationError
from app.web.decorators import current_token, request_security, require_auth, require_session_csrf, services
from app.web.http import pagination_args, pagination_payload


blueprint = Blueprint("runs", __name__)


@blueprint.post("/api/customer-features/<feature_id>/runs")
@require_auth()
@require_session_csrf
def create_run(feature_id: str):
    run = services().runs.create_manual_run(
        actor=g.auth,
        customer_feature_id=feature_id,
        request=request_security().metadata(request),
    )
    return jsonify({"run": run}), 202


@blueprint.post("/api/runs/<request_id>/stop")
@require_auth()
@require_session_csrf
def stop_run(request_id: str):
    run = services().runs.request_stop(
        actor=g.auth,
        request_id=request_id,
        request=request_security().metadata(request),
    )
    return jsonify({"run": run})


@blueprint.get("/api/runs")
@require_auth()
def list_runs():
    scope = request.args.get("scope", "customer").strip().lower()
    customer_id = request.args.get("customerId", "").strip() or None
    if scope not in {"all", "customer"} or (scope == "customer" and customer_id is None):
        raise ApplicationError("CUSTOMER_SCOPE_INVALID", "客户范围无效")
    page, page_size = pagination_args()
    try:
        queued_from = _optional_integer("queuedFrom")
        queued_to = _optional_integer("queuedTo")
    except ValueError as exc:
        raise ApplicationError("INVALID_RUN_FILTER", "时间筛选必须是整数") from exc
    items, total = services().runs.list_runs(
        g.auth,
        customer_id=customer_id if scope == "customer" else None,
        status=request.args.get("status") or None,
        customer_feature_id=request.args.get("customerFeatureId") or None,
        trigger_source=request.args.get("triggerSource") or None,
        queued_from=queued_from,
        queued_to=queued_to,
        request_id_prefix=request.args.get("requestId") or None,
        page=page,
        page_size=page_size,
    )
    return jsonify({"items": items, "pagination": pagination_payload(page, page_size, total)})


@blueprint.get("/api/runs/<request_id>")
@require_auth()
def get_run(request_id: str):
    return jsonify({"run": services().runs.get_run(g.auth, request_id)})


@blueprint.get("/api/runs/<request_id>/events")
@require_auth()
def get_events(request_id: str):
    try:
        after = int(request.args.get("after", "0"))
        limit = int(request.args.get("limit", "500"))
    except ValueError as exc:
        raise ApplicationError("INVALID_EVENT_CURSOR", "日志游标必须是整数") from exc
    return jsonify(services().runs.get_events(g.auth, request_id, after=after, limit=limit))


@blueprint.get("/api/runs/<request_id>/report")
@require_auth()
def get_report(request_id: str):
    return jsonify({"report": services().runs.get_report(g.auth, request_id)})


@blueprint.get("/api/runs/<request_id>/report/items")
@require_auth()
def get_report_items(request_id: str):
    page, page_size = pagination_args()
    items, total = services().runs.list_report_items(
        g.auth,
        request_id,
        status=request.args.get("status") or None,
        page=page,
        page_size=page_size,
    )
    return jsonify({"items": items, "pagination": pagination_payload(page, page_size, total)})


@blueprint.get("/api/runs/<request_id>/events/stream")
@require_auth()
def stream_events(request_id: str):
    actor = g.auth
    session_token = current_token()
    run_service = services().runs
    run_service.authorize_stream(actor, request_id)
    raw_cursor = request.headers.get("Last-Event-ID") or request.args.get("after", "0")
    try:
        cursor = max(0, int(raw_cursor))
    except (TypeError, ValueError) as exc:
        raise ApplicationError("INVALID_EVENT_CURSOR", "日志游标必须是整数") from exc

    @stream_with_context
    def generate():
        nonlocal actor, cursor
        last_keepalive = time.monotonic()
        last_auth_check = time.monotonic()
        while True:
            now = time.monotonic()
            if now - last_auth_check >= 10:
                refreshed_actor = services().auth.authenticate(session_token)
                if refreshed_actor is None:
                    yield "event: auth\ndata: {\"expired\":true}\n\n"
                    return
                actor = refreshed_actor
                last_auth_check = now
            page = run_service.get_events(actor, request_id, after=cursor, limit=500)
            for item in page["items"]:
                cursor = item["sequence"]
                data = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
                yield f"id: {cursor}\nevent: log\ndata: {data}\n\n"
            if page["logsPurgedAt"] is not None:
                status = json.dumps(
                    {
                        "status": page["status"],
                        "latestSequence": page["latestSequence"],
                        "logsPurgedAt": page["logsPurgedAt"],
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                yield f"event: run\ndata: {status}\n\n"
                return
            if page["terminal"] and cursor >= page["latestSequence"]:
                status = json.dumps(
                    {"status": page["status"], "latestSequence": page["latestSequence"]},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                yield f"event: run\ndata: {status}\n\n"
                return
            now = time.monotonic()
            if now - last_keepalive >= 10:
                yield ": keep-alive\n\n"
                last_keepalive = now
            time.sleep(0.4)

    response = Response(generate(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache, no-store"
    response.headers["X-Accel-Buffering"] = "no"
    return response


@blueprint.get("/api/runs/<request_id>/log.<output_format>")
@require_auth()
def download_log(request_id: str, output_format: str):
    filename, content, mimetype = services().runs.render_log(
        g.auth, request_id, output_format, request_security().metadata(request)
    )
    response = send_file(
        io.BytesIO(content),
        as_attachment=True,
        download_name=filename,
        mimetype=mimetype,
        max_age=0,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@blueprint.get("/api/runs/<request_id>/report.xlsx")
@require_auth()
def download_report(request_id: str):
    filename, content, mimetype = services().runs.render_report(
        g.auth,
        request_id,
        request_security().metadata(request),
    )
    response = send_file(
        io.BytesIO(content),
        as_attachment=True,
        download_name=filename,
        mimetype=mimetype,
        max_age=0,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _optional_integer(name: str) -> int | None:
    value = request.args.get(name)
    if value is None or value == "":
        return None
    return int(value)
