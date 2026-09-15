"""Feature Control Center backend package."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from flask import Flask


def create_app(*, data_dir: Path | str | None = None, **kwargs: Any) -> "Flask":
    """Create the web application without importing it during Alembic model discovery."""
    from app.web.app_factory import create_app as factory

    return factory(data_dir=data_dir, **kwargs)


__all__ = ["create_app"]
