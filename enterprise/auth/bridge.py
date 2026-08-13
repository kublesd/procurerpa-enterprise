"""Bridge enterprise JWT authentication to Skyvern's native org auth.

Skyvern's native endpoints (e.g. /workflows/create-from-prompt) use
``app.authentication_function`` to resolve a Bearer token into an
Organization. Enterprise JWTs are accepted by native Skyvern routes only for
users with full organization visibility. Restricted operators use procurement APIs.
"""

from jose import JWTError

from skyvern.forge import app as forge_app
from skyvern.forge.sdk.schemas.organizations import Organization

from .dependencies import _load_current_user
from .jwt_service import decode_enterprise_token


async def authenticate_enterprise_token(token: str) -> Organization | None:
    """Return the trusted organization for a full-organization administrator.

    Called by ``org_auth_service._authenticate_helper`` when a request
    carries an ``Authorization: Bearer <token>`` header but no API key.
    """
    try:
        token_user = decode_enterprise_token(token)
    except (JWTError, ValueError):
        return None

    user_ctx = await _load_current_user(token_user.user_id)
    if user_ctx is None or not user_ctx.is_org_admin:
        return None

    org = await forge_app.DATABASE.get_organization(
        organization_id=user_ctx.org_id,
    )
    return org


async def authenticate_enterprise_user(token: str) -> str | None:
    """Return a full-organization administrator's trusted user ID.

    Called by ``org_auth_service.get_current_user_id`` when a request
    carries an ``Authorization`` header.
    """
    try:
        token_user = decode_enterprise_token(token)
    except (JWTError, ValueError):
        return None

    user_ctx = await _load_current_user(token_user.user_id)
    if user_ctx is None or not user_ctx.is_org_admin:
        return None

    return user_ctx.user_id
