from __future__ import annotations

import io

from flask import Blueprint, g, jsonify, request, send_file

from app.application.errors import ApplicationError
from app.web.decorators import (
    request_security,
    require_admin,
    require_auth,
    require_management_network,
    require_session_csrf,
    services,
)
from app.web.http import json_body, pagination_args, pagination_payload


blueprint = Blueprint("features", __name__)


@blueprint.get("/api/customers/<customer_id>/features")
@require_auth()
def list_customer_features(customer_id: str):
    return jsonify({"items": services().features.list_customer_features(g.auth, customer_id)})


@blueprint.get("/api/customer-features")
@require_auth()
def list_scoped_customer_features():
    page, page_size = pagination_args()
    scope = request.args.get("scope", "customer").strip().lower()
    customer_id = request.args.get("customerId", "").strip() or None
    if scope not in {"all", "customer"} or (scope == "customer" and not customer_id):
        raise ApplicationError("CUSTOMER_SCOPE_INVALID", "客户范围无效", status=400)
    items, total = services().features.list_scoped_customer_features(
        g.auth,
        customer_id=None if scope == "all" else customer_id,
        page=page,
        page_size=page_size,
        search=request.args.get("search", ""),
        status=request.args.get("status", ""),
    )
    return jsonify({"items": items, "pagination": pagination_payload(page, page_size, total)})


@blueprint.get("/api/customer-features/<feature_id>/data-source")
@require_auth()
def data_source_metadata(feature_id: str):
    return jsonify(services().features.data_source_metadata(g.auth, feature_id))


@blueprint.put("/api/customer-features/<feature_id>/data-source")
@require_auth()
@require_session_csrf
def replace_data_source(feature_id: str):
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise ApplicationError("DATA_SOURCE_REQUIRED", "请选择数据源文件", status=400)
    maximum = services().settings.data_source_max_bytes()
    content = upload.stream.read(maximum + 1)
    result = services().features.replace_data_source(
        actor=g.auth,
        customer_feature_id=feature_id,
        filename=upload.filename,
        content=content,
        request=request_security().metadata(request),
    )
    return jsonify(result)


@blueprint.get("/api/customer-features/<feature_id>/data-source/download")
@require_auth()
def download_data_source(feature_id: str):
    item = services().features.download_data_source(
        g.auth, feature_id, request_security().metadata(request)
    )
    return _download(item)


@blueprint.get("/api/customer-features/<feature_id>/config")
@require_admin
@require_management_network
def get_config(feature_id: str):
    return jsonify(
        services().features.get_config(g.auth, feature_id, request_security().metadata(request))
    )


@blueprint.put("/api/customer-features/<feature_id>/config")
@require_admin
@require_management_network
@require_session_csrf
def update_config(feature_id: str):
    body = json_body()
    values = body.get("values", {})
    clear_secrets = body.get("clearSecrets", [])
    if not isinstance(values, dict) or not isinstance(clear_secrets, list) or any(not isinstance(item, str) for item in clear_secrets):
        raise ApplicationError("INVALID_CONFIG_PAYLOAD", "配置请求格式无效", status=400)
    return jsonify(services().features.update_config(
        actor=g.auth,
        customer_feature_id=feature_id,
        values=values,
        clear_secrets=clear_secrets,
        request=request_security().metadata(request),
    ))


@blueprint.get("/api/admin/feature-definitions")
@require_admin
@require_management_network
def list_definitions():
    page, page_size = pagination_args()
    items, total = services().features.list_definitions(page=page, page_size=page_size)
    return jsonify({"items": items, "pagination": pagination_payload(page, page_size, total)})


@blueprint.post("/api/admin/features/versions")
@require_admin
@require_management_network
@require_session_csrf
def upload_version():
    upload = request.files.get("package")
    customer_id = request.form.get("customerId", "")
    if upload is None or not upload.filename or not customer_id:
        raise ApplicationError("FEATURE_UPLOAD_REQUIRED", "请选择功能包和初始客户", status=400)
    maximum = services().settings.package_limits().max_package_bytes
    content = upload.stream.read(maximum + 1)
    result = services().features.register_package(
        actor=g.auth,
        customer_id=customer_id,
        filename=upload.filename,
        content=content,
        request=request_security().metadata(request),
    )
    return jsonify(result), 201


@blueprint.post("/api/admin/feature-versions/<version_id>/prepare")
@require_admin
@require_management_network
@require_session_csrf
def retry_prepare(version_id: str):
    return jsonify({"version": services().features.retry_prepare(
        actor=g.auth,
        version_id=version_id,
        request=request_security().metadata(request),
    )})


@blueprint.get("/api/admin/feature-versions/<version_id>/default-data-source/download")
@require_admin
@require_management_network
def download_default_data_source(version_id: str):
    return _download(
        services().features.download_default_data_source(
            g.auth, version_id, request_security().metadata(request)
        )
    )


@blueprint.post("/api/admin/customer-features/<feature_id>/activate-version")
@require_admin
@require_management_network
@require_session_csrf
def activate_version(feature_id: str):
    body = json_body()
    return jsonify({"feature": services().features.activate_version(
        actor=g.auth,
        customer_feature_id=feature_id,
        version_id=str(body.get("versionId", "")),
        use_default_data_source=body.get("useDefaultDataSource") is True,
        request=request_security().metadata(request),
    )})


@blueprint.post("/api/admin/customer-features/<feature_id>/copy")
@require_admin
@require_management_network
@require_session_csrf
def copy_customer_feature(feature_id: str):
    body = json_body()
    target_ids = body.get("targetCustomerIds")
    if not isinstance(target_ids, list) or any(not isinstance(item, str) for item in target_ids):
        raise ApplicationError("INVALID_COPY_TARGETS", "目标客户列表格式无效", status=400)
    return jsonify({
        "items": services().features.copy_to_customers(
            actor=g.auth,
            source_customer_feature_id=feature_id,
            target_customer_ids=target_ids,
            request=request_security().metadata(request),
        )
    })


@blueprint.patch("/api/admin/customer-features/<feature_id>")
@require_admin
@require_management_network
@require_session_csrf
def update_customer_feature(feature_id: str):
    body = json_body()
    enabled = body.get("isEnabled") if "isEnabled" in body else None
    if enabled is not None and not isinstance(enabled, bool):
        raise ApplicationError("INVALID_ENABLED", "启用状态必须是布尔值", status=400)
    if "isEnabled" not in body and "maxRuntimeSeconds" not in body:
        raise ApplicationError("FEATURE_POLICY_REQUIRED", "请至少提交一项运行策略", status=400)
    maximum = body.get("maxRuntimeSeconds") if "maxRuntimeSeconds" in body else ...
    return jsonify({"feature": services().features.set_enabled(
        actor=g.auth,
        customer_feature_id=feature_id,
        enabled=enabled,
        max_runtime_seconds=maximum,
        request=request_security().metadata(request),
    )})


def _download(item):
    response = send_file(
        io.BytesIO(item.content),
        as_attachment=True,
        download_name=item.filename,
        mimetype="application/octet-stream",
        max_age=0,
    )
    response.headers["X-Content-SHA256"] = item.sha256
    response.headers["Cache-Control"] = "private, no-store"
    return response
