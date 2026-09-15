from __future__ import annotations

import sqlite3

from flask import Blueprint, jsonify

from app.web.decorators import services


blueprint = Blueprint("health", __name__, url_prefix="/api/health")


@blueprint.get("/live")
def live():
    return jsonify({"status": "ok"})


@blueprint.get("/ready")
def ready():
    ready_state = services().database.check_health()
    return (
        jsonify(
            {
                "status": "ok" if ready_state else "unavailable",
                "database": ready_state,
                "sqliteVersion": sqlite3.sqlite_version,
                "initialized": not services().bootstrap.is_required(),
            }
        ),
        200 if ready_state else 503,
    )

