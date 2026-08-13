"""Tests for action result cache and cache management API.

Covers:
- DOM hashing stability (same structure → same hash)
- Dynamic content stripping (IDs/styles/comments removed)
- Cache set/get/miss/expiry lifecycle
- Cache statistics (hit rate, counts)
- Cache invalidation (by prefix, expired, all)
- Cache management API endpoints (admin-only)
- Goal hash determinism
- High-level helpers (cache_action_decision, lookup_cached_decision)
"""

import asyncio
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI
from fastapi.testclient import TestClient

from enterprise.llm.action_cache import (
    ActionCacheStore,
    RedisActionCacheStore,
    build_cache_key,
    cache_action_decision,
    compute_dom_hash,
    compute_goal_hash,
    configure_cache_store,
    configure_persistent_cache_store,
    lookup_cached_decision,
)
from enterprise.llm.cache_routes import router

# ============================================================
# DOM Hashing
# ============================================================

class TestDomHash(unittest.TestCase):
    def test_same_structure_same_hash(self):
        html = "<div><input type='text'/><button>Submit</button></div>"
        h1 = compute_dom_hash(html)
        h2 = compute_dom_hash(html)
        assert h1 == h2

    def test_different_structure_different_hash(self):
        h1 = compute_dom_hash("<div><input/></div>")
        h2 = compute_dom_hash("<div><textarea/></div>")
        assert h1 != h2

    def test_strips_react_ids(self):
        html1 = '<div data-reactid="abc123"><span>Hello</span></div>'
        html2 = '<div data-reactid="xyz789"><span>Hello</span></div>'
        assert compute_dom_hash(html1) == compute_dom_hash(html2)

    def test_strips_inline_styles(self):
        html1 = '<div style="color: red;"><p>Text</p></div>'
        html2 = '<div style="color: blue;"><p>Text</p></div>'
        assert compute_dom_hash(html1) == compute_dom_hash(html2)

    def test_strips_class_names(self):
        html1 = '<div class="foo bar"><p>Text</p></div>'
        html2 = '<div class="baz qux"><p>Text</p></div>'
        assert compute_dom_hash(html1) == compute_dom_hash(html2)

    def test_strips_html_comments(self):
        html1 = "<div><!-- comment --><p>Text</p></div>"
        html2 = "<div><p>Text</p></div>"
        assert compute_dom_hash(html1) == compute_dom_hash(html2)

    def test_strips_numeric_ids(self):
        html1 = '<div id="node_12345678"><p>Text</p></div>'
        html2 = '<div id="node_98765432"><p>Text</p></div>'
        assert compute_dom_hash(html1) == compute_dom_hash(html2)

    def test_hash_is_sha256_hex(self):
        h = compute_dom_hash("<div>test</div>")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestGoalHash(unittest.TestCase):
    def test_deterministic(self):
        h1 = compute_goal_hash("Navigate to account page and download statement")
        h2 = compute_goal_hash("Navigate to account page and download statement")
        assert h1 == h2

    def test_different_goals_different_hash(self):
        h1 = compute_goal_hash("Login to system")
        h2 = compute_goal_hash("Download report")
        assert h1 != h2

    def test_hash_is_sha256_hex(self):
        h = compute_goal_hash("test goal")
        assert len(h) == 64


class TestCacheKey(unittest.TestCase):
    def test_key_format(self):
        key = build_cache_key("org_1", "abc123", "def456")
        assert key.startswith("action_cache:org_1:")
        assert len(key.rsplit(":", 1)[1]) == 64

    def test_different_orgs(self):
        k1 = build_cache_key("org_1", "abc", "def")
        k2 = build_cache_key("org_2", "abc", "def")
        assert k1 != k2

    def test_model_and_schema_are_part_of_key(self):
        base = build_cache_key("org_1", "abc", "def", "model-a", "v1")
        assert base != build_cache_key("org_1", "abc", "other", "model-a", "v1")
        assert base != build_cache_key("org_1", "abc", "def", "model-b", "v1")
        assert base != build_cache_key("org_1", "abc", "def", "model-a", "v2")


class TestRedisActionCacheStore(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.redis = FakeRedis(decode_responses=True)
        self.store = RedisActionCacheStore(self.redis)

    async def asyncTearDown(self):
        configure_persistent_cache_store(None)
        await self.redis.aclose()

    async def test_persists_and_isolates_variants(self):
        key = build_cache_key("org_1", "dom", "goal", "model-a", "v1")
        value = {"schema_version": "extract-actions-v1", "actions": [{"action_type": "WAIT"}]}
        await self.store.set(key, value)
        assert 0 < await self.redis.ttl(key) <= 86400
        assert await RedisActionCacheStore(self.redis).get(key) == value
        assert await self.store.get(build_cache_key("org_2", "dom", "goal", "model-a", "v1")) is None
        assert await self.store.get(build_cache_key("org_1", "other", "goal", "model-a", "v1")) is None

    async def test_invalid_schema_is_deleted(self):
        key = build_cache_key("org_1", "dom", "goal", "model", "v1")
        await self.redis.set(key, '{"actions":"unsafe"}')
        assert await self.store.get(key) is None
        assert await self.redis.get(key) is None

    async def test_real_action_call_hits_after_agent_rebuild(self):
        from skyvern.forge.agent import ForgeAgent

        task = SimpleNamespace(
            organization_id="org_1",
            task_id="task_1",
            workflow_run_id=None,
            navigation_goal="Click submit",
            data_extraction_goal=None,
            llm_key="model-a",
        )
        step = SimpleNamespace(step_id="step_1", order=0)
        page = MagicMock(
            screenshots=[],
            id_to_element_hash={"1": "element-hash"},
            id_to_element_dict={"1": {"tagName": "BUTTON"}},
        )
        page.build_element_tree.return_value = '<button id="1">Submit</button>'
        llm = AsyncMock(return_value={"actions": [{"action_type": "CLICK", "id": "1"}]})
        llm.llm_key = "model-a"

        first = ForgeAgent(action_cache=self.store)
        second = ForgeAgent(action_cache=RedisActionCacheStore(self.redis))
        kwargs = {
            "task": task,
            "step": step,
            "scraped_page": page,
            "llm_api_handler": llm,
            "prompt": "safe synthetic prompt",
            "prompt_name": "extract-actions",
        }
        with patch("skyvern.forge.agent.parse_actions", return_value=[object()]):
            await first._resolve_action_response(**kwargs)
            await second._resolve_action_response(**kwargs)
        assert llm.await_count == 1

    async def test_redis_failure_falls_back_to_llm(self):
        from skyvern.forge.agent import ForgeAgent

        broken_store = MagicMock()
        broken_store.get = AsyncMock(side_effect=ConnectionError("redis unavailable"))
        broken_store.set = AsyncMock(side_effect=ConnectionError("redis unavailable"))
        llm = AsyncMock(return_value={"actions": [{"action_type": "WAIT"}]})
        llm.llm_key = "model-a"
        task = SimpleNamespace(
            organization_id="org_1",
            task_id="task_1",
            workflow_run_id=None,
            navigation_goal="Wait",
            data_extraction_goal=None,
            llm_key="model-a",
        )
        step = SimpleNamespace(step_id="step_1", order=0)
        page = MagicMock(screenshots=[], id_to_element_hash={}, id_to_element_dict={})
        page.build_element_tree.return_value = "<div>Loading</div>"
        with patch("skyvern.forge.agent.parse_actions", return_value=[object()]):
            result = await ForgeAgent(action_cache=broken_store)._resolve_action_response(
                task=task,
                step=step,
                scraped_page=page,
                llm_api_handler=llm,
                prompt="safe synthetic prompt",
                prompt_name="extract-actions",
            )
        assert result["actions"][0]["action_type"] == "WAIT"
        assert llm.await_count == 1


# ============================================================
# ActionCacheStore
# ============================================================

class TestActionCacheStore(unittest.TestCase):
    def setUp(self):
        self.store = ActionCacheStore()

    def test_get_miss(self):
        result = self.store.get("nonexistent")
        assert result is None

    def test_set_and_get(self):
        self.store.set("key1", {"action": "click", "target": "#btn"})
        result = self.store.get("key1")
        assert result is not None
        assert result["action"] == "click"

    def test_ttl_expiry(self):
        self.store.set("key1", {"a": 1}, ttl=1)
        # Value should be available immediately
        assert self.store.get("key1") is not None
        # Simulate expiry
        with patch("enterprise.llm.action_cache.datetime") as mock_dt:
            mock_dt.utcnow.return_value = datetime(2099, 1, 1)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = self.store.get("key1")
            assert result is None

    def test_delete_existing(self):
        self.store.set("key1", {"a": 1})
        assert self.store.delete("key1") is True
        assert self.store.get("key1") is None

    def test_delete_nonexistent(self):
        assert self.store.delete("nonexistent") is False

    def test_clear_by_prefix(self):
        self.store.set("action_cache:org_1:aaa:bbb", {"a": 1})
        self.store.set("action_cache:org_1:ccc:ddd", {"b": 2})
        self.store.set("action_cache:org_2:eee:fff", {"c": 3})
        removed = self.store.clear_by_prefix("action_cache:org_1:")
        assert removed == 2
        assert self.store.get("action_cache:org_2:eee:fff") is not None

    def test_clear_expired(self):
        self.store.set("key1", {"a": 1}, ttl=1)
        self.store.set("key2", {"b": 2}, ttl=999999)
        with patch("enterprise.llm.action_cache.datetime") as mock_dt:
            mock_dt.utcnow.return_value = datetime(2099, 1, 1)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            removed = self.store.clear_expired()
            assert removed == 2  # both expired by 2099

    def test_clear_all(self):
        self.store.set("a", {"x": 1})
        self.store.set("b", {"y": 2})
        removed = self.store.clear_all()
        assert removed == 2
        assert self.store.get("a") is None

    def test_stats_initial(self):
        stats = self.store.stats
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["hit_rate"] == 0.0

    def test_stats_tracking(self):
        self.store.set("key1", {"a": 1})
        self.store.get("key1")  # hit
        self.store.get("key1")  # hit
        self.store.get("missing")  # miss
        stats = self.store.stats
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 66.7
        assert stats["sets"] == 1

    def test_reset_stats(self):
        self.store.set("k", {"v": 1})
        self.store.get("k")
        self.store.reset_stats()
        stats = self.store.stats
        assert stats["hits"] == 0
        assert stats["misses"] == 0


# ============================================================
# High-level helpers
# ============================================================

class TestHighLevelHelpers(unittest.TestCase):
    def setUp(self):
        self.store = ActionCacheStore()
        configure_cache_store(self.store)

    def test_cache_and_lookup(self):
        dom = "<div><button>Submit</button></div>"
        goal = "Click the submit button"
        decision = {"element": "button", "action": "click"}

        key = cache_action_decision("org_1", dom, goal, decision)
        assert key.startswith("action_cache:org_1:")

        result = lookup_cached_decision("org_1", dom, goal)
        assert result is not None
        assert result["element"] == "button"

    def test_lookup_miss(self):
        result = lookup_cached_decision("org_1", "<div>new</div>", "new goal")
        assert result is None

    def test_same_page_different_goal(self):
        dom = "<div><form><input/></form></div>"
        cache_action_decision("org_1", dom, "Fill form", {"action": "fill"})

        result = lookup_cached_decision("org_1", dom, "Submit form")
        assert result is None  # different goal → miss

    def test_same_goal_different_page(self):
        goal = "Login to banking portal"
        cache_action_decision("org_1", "<div id='v1'><input/></div>", goal, {"step": 1})

        # Different structural DOM (textarea instead of input)
        result = lookup_cached_decision("org_1", "<div><textarea/></div>", goal)
        assert result is None

    def test_org_isolation(self):
        dom = "<div>page</div>"
        goal = "Do something"
        cache_action_decision("org_1", dom, goal, {"data": "org1"})

        result = lookup_cached_decision("org_2", dom, goal)
        assert result is None  # different org → miss

    def test_second_execution_hits_cache(self):
        """Simulates same page executed twice — second call should hit cache."""
        dom = "<div><table><tr><td>Balance</td></tr></table></div>"
        goal = "Extract balance from table"
        decision = {"element": "td", "value": "Balance", "action": "extract"}

        # First execution: cache miss, store decision
        result1 = lookup_cached_decision("org_1", dom, goal)
        assert result1 is None

        cache_action_decision("org_1", dom, goal, decision)

        # Second execution: cache hit
        result2 = lookup_cached_decision("org_1", dom, goal)
        assert result2 is not None
        assert result2["action"] == "extract"


# ============================================================
# Cache Management API
# ============================================================

class TestCacheManagementAPI(unittest.TestCase):
    def setUp(self):
        from enterprise.auth.dependencies import get_current_user, require_admin
        from enterprise.auth.schemas import DepartmentRole, UserContext

        self.app = FastAPI()
        self.app.include_router(router)

        self.user = UserContext(
            user_id="eu_1",
            org_id="org_1",
            department_roles=[
                DepartmentRole(department_id="dept_a", department_name="IT", role="org_admin"),
            ],
            business_line_ids=[],
        )
        self.app.dependency_overrides[get_current_user] = lambda: self.user
        self.app.dependency_overrides[require_admin] = lambda: self.user

        self.redis = FakeRedis(decode_responses=True)
        self.store = RedisActionCacheStore(self.redis)
        configure_persistent_cache_store(self.store)
        self.client = TestClient(self.app)

    def tearDown(self):
        configure_persistent_cache_store(None)
        asyncio.run(self.redis.aclose())

    def _set(self, key: str) -> None:
        asyncio.run(self.store.set(
            key,
            {"schema_version": "extract-actions-v1", "actions": [{"action_type": "WAIT"}]},
        ))

    def test_get_stats(self):
        key = build_cache_key("org_1", "dom", "goal")
        self._set(key)
        asyncio.run(self.store.get(key))
        resp = self.client.get("/enterprise/cache/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "hits" in data
        assert "hit_rate" in data
        assert data["hits"] == 1

    def test_management_api_fails_closed_without_persistent_store(self):
        configure_persistent_cache_store(None)
        resp = self.client.get("/enterprise/cache/stats")
        assert resp.status_code == 503

    def test_clear_expired(self):
        resp = self.client.delete("/enterprise/cache/expired")
        assert resp.status_code == 200
        assert "removed" in resp.json()

    def test_clear_all(self):
        self._set(build_cache_key("org_1", "a", "b"))
        self._set(build_cache_key("org_1", "b", "c"))
        other_org_key = build_cache_key("org_2", "c", "d")
        self._set(other_org_key)
        resp = self.client.delete("/enterprise/cache/all")
        assert resp.status_code == 200
        assert resp.json()["removed"] == 2
        assert asyncio.run(self.store.get(other_org_key)) is not None

    def test_task_scoped_clear_is_not_exposed(self):
        key = build_cache_key("org_1", "abc", "def")
        self._set(key)
        resp = self.client.delete("/enterprise/cache/task/task_101")
        assert resp.status_code == 404
        assert asyncio.run(self.store.get(key)) is not None

    def test_reset_stats(self):
        key = build_cache_key("org_1", "dom", "goal")
        self._set(key)
        asyncio.run(self.store.get(key))
        resp = self.client.post("/enterprise/cache/reset-stats")
        assert resp.status_code == 200
        stats = asyncio.run(self.store.stats("org_1"))
        assert stats["hits"] == 0


if __name__ == "__main__":
    unittest.main()
