"""FastAPI middleware for multi-dimensional tenant context injection.

On each incoming request:
1. Check if the route is in the whitelist (skip auth for login, health, docs)
2. Extract Bearer token from Authorization header
3. Decode enterprise JWT to identify the user
4. Load trusted visibility scope and build TenantContext
5. Store in ContextVar for downstream query filters
"""

import structlog
from fastapi import Request, Response
from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from enterprise.auth.dependencies import _load_current_user
from enterprise.auth.jwt_service import decode_enterprise_token

from .context import reset_tenant_context, set_tenant_context, tenant_context_for

LOG = structlog.get_logger()

# Routes that skip tenant context injection
_WHITELIST_PREFIXES = (
    "/api/v1/enterprise/auth/login",
    "/api/v1/enterprise/procurement/health",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
)


def _is_whitelisted(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _WHITELIST_PREFIXES)


class TenantIsolationMiddleware(BaseHTTPMiddleware):
    """Injects multi-dimensional tenant context into each request."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if _is_whitelisted(request.url.path):
            return await call_next(request)

        authorization = request.headers.get("authorization")
        if not authorization:
            # No auth header — let downstream dependency handlers raise 401
            return await call_next(request)

        parts = authorization.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return await call_next(request)

        token = parts[1]
        try:
            user_ctx = decode_enterprise_token(token)
        except (JWTError, ValueError):
            # Invalid token — let downstream handlers deal with it
            return await call_next(request)

        # Claims identify the user only. Scope is always loaded from the database.
        trusted_user = await _load_current_user(user_ctx.user_id)
        if trusted_user is None:
            return await call_next(request)

        tenant = tenant_context_for(trusted_user)

        ctx_token = set_tenant_context(tenant)
        try:
            response = await call_next(request)
        finally:
            reset_tenant_context(ctx_token)

        return response
