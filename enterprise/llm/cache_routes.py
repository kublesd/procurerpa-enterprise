"""Persistent action-cache management API routes (admin-only)."""

from fastapi import APIRouter, Depends, HTTPException, status

from enterprise.auth.dependencies import require_admin
from enterprise.auth.schemas import UserContext

from .action_cache import get_persistent_cache_store

router = APIRouter(prefix="/enterprise/cache", tags=["cache"])


def _persistent_store():
    store = get_persistent_cache_store()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Persistent action cache is unavailable",
        )
    return store


def _unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Persistent action cache is unavailable",
    )


@router.get("/stats")
async def cache_stats(
    user: UserContext = Depends(require_admin),
) -> dict:
    """Return cache hit/miss statistics."""
    try:
        return await _persistent_store().stats(user.org_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable() from exc


@router.delete("/expired")
async def clear_expired_cache(
    user: UserContext = Depends(require_admin),
) -> dict:
    """Remove all expired cache entries."""
    prefix = f"action_cache:{user.org_id}:"
    try:
        removed = await _persistent_store().clear_expired(prefix)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable() from exc
    return {"removed": removed}


@router.delete("/all")
async def clear_all_cache(
    user: UserContext = Depends(require_admin),
) -> dict:
    """Clear the entire action cache."""
    prefix = f"action_cache:{user.org_id}:"
    try:
        removed = await _persistent_store().clear_all(prefix)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable() from exc
    return {"removed": removed}


@router.post("/reset-stats")
async def reset_cache_stats(
    user: UserContext = Depends(require_admin),
) -> dict:
    """Reset hit/miss counters."""
    try:
        await _persistent_store().reset_stats(user.org_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unavailable() from exc
    return {"status": "ok"}
