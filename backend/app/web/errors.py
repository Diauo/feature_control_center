from __future__ import annotations

import logging

from flask import Flask, jsonify
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException

from app.application.errors import ApplicationError
from app.domain.identity import ValidationError


logger = logging.getLogger(__name__)


def error_payload(code: str, message: str, details: dict[str, object] | None = None) -> dict[str, object]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApplicationError)
    def handle_application_error(error: ApplicationError):
        response = jsonify(error_payload(error.code, error.message, error.details))
        response.status_code = error.status
        retry_after = error.details.get("retryAfterSeconds")
        if error.status == 429 and isinstance(retry_after, int):
            response.headers["Retry-After"] = str(max(1, retry_after))
        return response

    @app.errorhandler(ValidationError)
    def handle_validation_error(error: ValidationError):
        details = {"field": error.field} if error.field else {}
        return jsonify(error_payload(error.code, error.message, details)), 400

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        if error.code == 404:
            return jsonify(error_payload("NOT_FOUND", "请求的资源不存在")), 404
        return jsonify(error_payload("HTTP_ERROR", error.description)), error.code or 500

    @app.errorhandler(SQLAlchemyError)
    def handle_database_error(error: SQLAlchemyError):
        logger.exception("Database operation failed", exc_info=error)
        return jsonify(error_payload("DATABASE_ERROR", "数据库操作失败，请稍后重试")), 503

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        logger.exception("Unhandled application error", exc_info=error)
        return jsonify(error_payload("INTERNAL_ERROR", "系统内部错误")), 500
