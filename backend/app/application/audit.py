from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.infrastructure.models import (
    AuditLogModel,
    CustomerFeatureModel,
    CustomerModel,
    FeatureVersionModel,
    RunModel,
    ScheduledTaskModel,
    UserModel,
)
from app.security.crypto import user_agent_digest


@dataclass(frozen=True, slots=True)
class RequestMetadata:
    client_ip: str
    user_agent: str
    method: str = ""
    path: str = ""
    request_id: str = ""


def add_audit(
    db: Session,
    *,
    now: int,
    request: RequestMetadata,
    action: str,
    outcome: str,
    actor_user_id: str | None = None,
    session_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    target_name: str | None = None,
    customer_id: str | None = None,
    customer_name: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    safe_details = details or {}
    actor = db.get(UserModel, actor_user_id) if actor_user_id else None
    context = _target_context(db, target_type, target_id)
    customer_id = customer_id or context[0]
    customer_name = customer_name or context[1]
    target_name = target_name or context[2]
    user_agent = "".join(character for character in request.user_agent if character >= " " and character != "\x7f")
    db.add(
        AuditLogModel(
            occurred_at=now,
            actor_user_id=actor_user_id,
            actor_role=actor.role if actor else None,
            actor_username=actor.username if actor else None,
            actor_display_name=actor.display_name if actor else None,
            session_id=session_id,
            action=action,
            outcome=outcome,
            target_type=target_type,
            target_id=target_id,
            target_name=target_name[:120] if target_name else None,
            customer_id=customer_id[:32] if customer_id else None,
            customer_name=customer_name[:120] if customer_name else None,
            client_ip=request.client_ip[:64],
            request_method=request.method[:10] or None,
            request_path=request.path[:300] or None,
            request_id=request.request_id[:32] or None,
            user_agent=user_agent[:512] or None,
            user_agent_hash=user_agent_digest(request.user_agent),
            details_json=json.dumps(safe_details, ensure_ascii=False, separators=(",", ":")),
        )
    )


def _target_context(db: Session, target_type: str | None, target_id: str | None) -> tuple[str | None, str | None, str | None]:
    if not target_type or not target_id:
        return None, None, None
    customer_id: str | None = None
    target_name: str | None = None
    if target_type == "customer_feature":
        row = db.get(CustomerFeatureModel, target_id)
        if row:
            customer_id, target_name = row.customer_id, row.display_name
    elif target_type == "run":
        row = db.get(RunModel, target_id)
        if row:
            customer_id, target_name = row.customer_id, row.feature_name
    elif target_type == "schedule":
        row = db.get(ScheduledTaskModel, target_id)
        if row:
            customer_id, target_name = row.customer_id, row.name
    elif target_type == "customer":
        row = db.get(CustomerModel, target_id)
        if row:
            customer_id, target_name = row.id, row.name
    elif target_type == "user":
        row = db.get(UserModel, target_id)
        if row:
            target_name = row.display_name
    elif target_type == "feature_version":
        row = db.get(FeatureVersionModel, target_id)
        if row:
            target_name = f"{row.name} · 代码版本 {row.version_number}"
    customer = db.get(CustomerModel, customer_id) if customer_id else None
    return customer_id, customer.name if customer else None, target_name
