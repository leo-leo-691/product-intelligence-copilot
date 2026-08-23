"""Optional API-key auth for deployment. Empty API_KEY = open (local/dev)."""
import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend.app.config import settings


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not settings.api_key:
            return await call_next(request)

        path = request.url.path
        if path == "/health" or path.startswith("/docs") or path in ("/openapi.json", "/redoc"):
            return await call_next(request)

        if request.method == "OPTIONS":
            return await call_next(request)

        provided = request.headers.get("X-API-Key") or request.query_params.get("api_key") or ""
        if not hmac.compare_digest(provided, settings.api_key):
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})
        return await call_next(request)
