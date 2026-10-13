"""API key check for mutating requests (POST/DELETE).

Primary header: X-API-Key. Also accepts Authorization: Bearer <key>.
"""

import hmac
import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.errors import ApiError, error_response

log = logging.getLogger(__name__)

PROTECTED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def extract_key(request: Request) -> str | None:
    key = request.headers.get("x-api-key")
    if key:
        return key
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() == "bearer" and token:
        return token.strip()
    return None


class ApiKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_key: str) -> None:  # noqa: ANN001 - starlette ASGI app
        super().__init__(app)
        self.api_key = api_key
        if not api_key:
            log.warning("API_KEY is empty - authentication disabled (dev only)")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self.api_key or request.method not in PROTECTED_METHODS:
            return await call_next(request)
        provided = extract_key(request)
        if provided is None or not hmac.compare_digest(provided, self.api_key):
            return error_response(401, "unauthorized", "missing or invalid API key")
        return await call_next(request)


def require_api_key(request: Request) -> None:
    """Dependency for GET routes that must be protected (the middleware covers POST/DELETE)."""
    api_key: str = request.app.state.settings.api_key
    if not api_key:
        return
    provided = extract_key(request)
    if provided is None or not hmac.compare_digest(provided, api_key):
        raise ApiError("unauthorized", "missing or invalid API key", 401)
