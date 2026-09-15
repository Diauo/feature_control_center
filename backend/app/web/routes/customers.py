from __future__ import annotations

from flask import Blueprint, g, jsonify

from app.application.auth import AuthContext
from app.web.decorators import require_auth, services


blueprint = Blueprint("customers", __name__, url_prefix="/api/customers")


@blueprint.get("")
@require_auth()
def list_customers():
    context: AuthContext = g.auth
    return jsonify({"items": services().identity.list_authorized_customers(context)})

