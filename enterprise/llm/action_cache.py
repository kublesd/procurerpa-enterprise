"""In-memory procurement action cache for first-phase LLM decision reuse.

Caches LLM decisions (which element to interact with, action plan) keyed
by a hash of the page's DOM structure (with dynamic content stripped) and
the navigation goal.  On cache hit the LLM call is skipped entirely.

Cache invalidation:
- TTL expiry (default 24 hours)
- Manual clear via admin API
- DOM structure hash mismatch (page changed)
"""

import hashlib
import json
import logging
import re
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Default time-to-live for cached action decisions (seconds)
DEFAULT_CACHE_TTL = 86400  # 24 hours
ACTION_CACHE_SCHEMA_VERSION = "extract-actions-v1"


# ── DOM hashing ──────────────────────────────────────────────

# Patterns considered "dynamic" – stripped before hashing
_DYNAMIC_PATTERNS = [
    re.compile(r'\bid="[^"]*\d{6,}[^"]*"'),          # IDs with long numbers
    re.compile(r'\bdata-reactid="[^"]*"'),             # React internal IDs
    re.compile(r'\bdata-testid="[^"]*"'),              # Test IDs
    re.compile(r'\bstyle="[^"]*"'),                    # Inline styles
    re.compile(r'\bclass="[^"]*"'),                    # Class names (order varies)
    re.compile(r"<!--[\s\S]*?-->"),                     # HTML comments
    re.compile(r"\s+"),                                 # Collapse whitespace
]


_COMMENT_PATTERN = re.compile(r"<!--[\s\S]*?-->")


def _strip_dynamic_content(dom_html: str) -> str:
    """Remove dynamic / non-structural content from DOM HTML."""
    # Remove HTML comments first (replace with nothing)
    text = _COMMENT_PATTERN.sub("", dom_html)
    # Remove dynamic attributes
    for pat in _DYNAMIC_PATTERNS:
        text = pat.sub(" ", text)
    # Normalize all whitespace to single spaces and strip
    return re.sub(r"\s+", " ", text).strip()


def compute_dom_hash(dom_html: str) -> str:
    """Compute a stable SHA-256 hash of the structural DOM."""
    stripped = _strip_dynamic_content(dom_html)
    return hashlib.sha256(stripped.encode("utf-8")).hexdigest()


def compute_goal_hash(navigation_goal: str) -> str:
    """Compute a SHA-256 hash of the navigation goal text."""
    return hashlib.sha256(navigation_goal.encode("utf-8")).hexdigest()


def build_cache_key(
    org_id: str,
    dom_hash: str,
    goal_hash: str,
    model_key: str = "demo",
    schema_version: str = ACTION_CACHE_SCHEMA_VERSION,
) -> str:
    """Construct the Redis cache key for an action decision."""
    variant = hashlib.sha256(f"{dom_hash}:{goal_hash}:{model_key}:{schema_version}".encode()).hexdigest()
    return f"action_cache:{org_id}:{variant}"


def sanitize_action_response(value: dict[str, Any]) -> dict[str, Any] | None:
    """Return the safe subset of a validated extract-action response."""
    actions = value.get("actions")
    if not isinstance(actions, list) or not actions:
        return None

    safe_actions: list[dict[str, Any]] = []
    allowed_fields = {
        "CLICK": {"action_type", "id", "element_id", "download"},
        "WAIT": {"action_type"},
        "COMPLETE": {"action_type"},
        "SCROLL": {"action_type", "id", "element_id", "direction"},
        "KEYPRESS": {"action_type", "key"},
        "CLOSE_PAGE": {"action_type"},
    }
    for action in actions:
        if not isinstance(action, dict) or not isinstance(action.get("action_type"), str):
            return None
        action_type = action["action_type"].upper()
        fields = allowed_fields.get(action_type)
        if fields is None or action.get("file_url"):
            # ponytail: cache only non-personalized actions; widen after a secrets-safe value schema exists.
            return None
        safe_actions.append({key: item for key, item in action.items() if key in fields})
    return {"schema_version": ACTION_CACHE_SCHEMA_VERSION, "actions": safe_actions}


class RedisActionCacheStore:
    """Minimal persistent store for production Skyvern action decisions."""

    def __init__(self, redis_client: Any) -> None:
        self.redis = redis_client

    @staticmethod
    def _org_id(key: str) -> str:
        return key.split(":", 2)[1]

    def _stats_key(self, org_id: str) -> str:
        return f"action_cache_stats:{org_id}"

    async def _increment(self, org_id: str, field: str) -> None:
        await self.redis.hincrby(self._stats_key(org_id), field, 1)

    async def get(self, key: str) -> dict[str, Any] | None:
        org_id = self._org_id(key)
        raw = await self.redis.get(key)
        if raw is None:
            await self._increment(org_id, "misses")
            return None
        try:
            value = json.loads(raw)
            if (
                not isinstance(value, dict)
                or value.get("schema_version") != ACTION_CACHE_SCHEMA_VERSION
                or not isinstance(value.get("actions"), list)
            ):
                raise ValueError("invalid action cache schema")
        except (TypeError, ValueError, json.JSONDecodeError):
            await self.redis.delete(key)
            await self._increment(org_id, "invalid")
            return None
        await self._increment(org_id, "hits")
        return value

    async def set(self, key: str, value: dict[str, Any], ttl: int = DEFAULT_CACHE_TTL) -> None:
        await self.redis.setex(key, ttl, json.dumps(value, separators=(",", ":"), sort_keys=True))
        await self._increment(self._org_id(key), "sets")

    async def delete(self, key: str) -> bool:
        return bool(await self.redis.delete(key))

    async def invalidate(self, key: str) -> None:
        await self.redis.delete(key)
        await self._increment(self._org_id(key), "invalid")

    async def clear_by_prefix(self, prefix: str) -> int:
        keys = [key async for key in self.redis.scan_iter(match=f"{prefix}*")]
        return await self.redis.delete(*keys) if keys else 0

    async def clear_expired(self, prefix: str) -> int:
        # Redis removes expired keys itself.
        return 0

    async def clear_all(self, prefix: str) -> int:
        return await self.clear_by_prefix(prefix)

    async def stats(self, org_id: str) -> dict[str, Any]:
        raw = await self.redis.hgetall(self._stats_key(org_id))
        counters = {
            (key.decode() if isinstance(key, bytes) else key): int(value)
            for key, value in raw.items()
        }
        hits = counters.get("hits", 0)
        misses = counters.get("misses", 0)
        total = hits + misses
        entries = 0
        async for _ in self.redis.scan_iter(match=f"action_cache:{org_id}:*"):
            entries += 1
        return {
            "total_entries": entries,
            "hits": hits,
            "misses": misses,
            "invalid": counters.get("invalid", 0),
            "expired": counters.get("expired", 0),
            "hit_rate": round(hits / total * 100, 1) if total else 0.0,
            "sets": counters.get("sets", 0),
            "data_source": "redis_persistent",
            "execution_mode": "real",
            "connection_status": "connected",
        }

    async def reset_stats(self, org_id: str) -> None:
        await self.redis.delete(self._stats_key(org_id))


# ── In-memory demo cache store (Redis is a second-phase debt) ──

class ActionCacheStore:
    """In-memory action cache with TTL support.

    It only caches synthetic or sanitized procurement page decisions in the
    first phase; real Skyvern action calls are not connected here.
    """

    def __init__(self) -> None:
        # key -> (value_dict, expires_at_timestamp)
        self._store: dict[str, tuple[dict[str, Any], float]] = {}
        # Statistics
        self._hits = 0
        self._misses = 0
        self._sets = 0

    # ── read / write ─────────────────────────────────────────

    def get(self, key: str) -> dict[str, Any] | None:
        """Return cached value or None on miss / expiry."""
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None

        value, expires_at = entry
        if datetime.utcnow().timestamp() > expires_at:
            del self._store[key]
            self._misses += 1
            logger.debug("Cache expired: %s", key)
            return None

        self._hits += 1
        logger.info("Cache hit: %s", key)
        return value

    def set(
        self,
        key: str,
        value: dict[str, Any],
        ttl: int = DEFAULT_CACHE_TTL,
    ) -> None:
        """Store a value with TTL (seconds)."""
        expires_at = datetime.utcnow().timestamp() + ttl
        self._store[key] = (value, expires_at)
        self._sets += 1
        logger.info("Cache set: %s (ttl=%ds)", key, ttl)

    # ── management ───────────────────────────────────────────

    def delete(self, key: str) -> bool:
        """Delete a single cache entry.  Returns True if existed."""
        if key in self._store:
            del self._store[key]
            return True
        return False

    def clear_by_prefix(self, prefix: str) -> int:
        """Delete all entries whose key starts with *prefix*.

        Returns the number of deleted entries.
        """
        keys_to_delete = [k for k in self._store if k.startswith(prefix)]
        for k in keys_to_delete:
            del self._store[k]
        return len(keys_to_delete)

    def clear_expired(self, prefix: str | None = None) -> int:
        """Remove expired entries, optionally restricted to a tenant prefix."""
        now = datetime.utcnow().timestamp()
        expired_keys = [
            k for k, (_, exp) in self._store.items()
            if now > exp and (prefix is None or k.startswith(prefix))
        ]
        for k in expired_keys:
            del self._store[k]
        return len(expired_keys)

    def clear_all(self, prefix: str | None = None) -> int:
        """Remove every entry, optionally restricted to a tenant prefix."""
        if prefix is None:
            count = len(self._store)
            self._store.clear()
            return count
        return self.clear_by_prefix(prefix)

    # ── statistics ───────────────────────────────────────────

    @property
    def stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        total = self._hits + self._misses
        hit_rate = round(self._hits / total * 100, 1) if total > 0 else 0.0
        return {
            "total_entries": len(self._store),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "sets": self._sets,
            "data_source": "memory_demo",
            "execution_mode": "simulated",
            "connection_status": "not_connected",
        }

    def reset_stats(self) -> None:
        """Reset hit/miss counters."""
        self._hits = 0
        self._misses = 0
        self._sets = 0


# ── High-level helpers ───────────────────────────────────────

# Module-level singleton (can be replaced via configure_cache_store)
_cache_store = ActionCacheStore()
_persistent_cache_store: RedisActionCacheStore | None = None


def get_cache_store() -> ActionCacheStore:
    """Return the module-level cache store singleton."""
    return _cache_store


def configure_cache_store(store: ActionCacheStore) -> None:
    """Replace the module-level demo cache store (for testing)."""
    global _cache_store
    _cache_store = store


def configure_persistent_cache_store(store: RedisActionCacheStore | None) -> None:
    """Inject the production Redis store used by Skyvern and management routes."""
    global _persistent_cache_store
    _persistent_cache_store = store


def get_persistent_cache_store() -> RedisActionCacheStore | None:
    return _persistent_cache_store


def cache_action_decision(
    org_id: str,
    dom_html: str,
    navigation_goal: str,
    decision: dict[str, Any],
    ttl: int = DEFAULT_CACHE_TTL,
) -> str:
    """Cache an LLM action decision.  Returns the cache key."""
    dom_hash = compute_dom_hash(dom_html)
    goal_hash = compute_goal_hash(navigation_goal)
    key = build_cache_key(org_id, dom_hash, goal_hash)
    _cache_store.set(key, decision, ttl)
    return key


def lookup_cached_decision(
    org_id: str,
    dom_html: str,
    navigation_goal: str,
) -> dict[str, Any] | None:
    """Look up a cached action decision.  Returns None on miss."""
    dom_hash = compute_dom_hash(dom_html)
    goal_hash = compute_goal_hash(navigation_goal)
    key = build_cache_key(org_id, dom_hash, goal_hash)
    return _cache_store.get(key)
