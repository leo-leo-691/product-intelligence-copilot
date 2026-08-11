"""ASGI entrypoint: `uvicorn backend.app.main:app`."""
from backend.app.api.routes import app

__all__ = ["app"]
