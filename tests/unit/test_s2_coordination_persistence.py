"""S2 durable Planner/Coordinator recovery checks."""

from types import SimpleNamespace

import pytest

from enterprise.agent.coordinator import (
    AgentCoordinator,
    CoordinationPersistenceError,
    CoordinationStateConflict,
)
from enterprise.agent.executor import ExecutorAgent
from enterprise.agent.planner import PlannerAgent


class MemorySession:
    def __init__(self, rows, fail_commit=False):
        self.rows = rows
        self.pending = None
        self.fail_commit = fail_commit

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def add(self, row):
        self.pending = row

    async def scalar(self, statement):
        params = statement.compile().params
        row = self.rows.get(params.get("task_id_1"))
        if row is None or (
            params.get("organization_id_1") is not None
            and row.organization_id != params["organization_id_1"]
        ):
            return None
        expression = statement.column_descriptions[0]["expr"]
        return row.task_id if getattr(expression, "key", None) == "task_id" else row

    async def execute(self, statement):
        params = statement.compile().params
        row = self.rows.get(params["task_id_1"])
        if row is None or row.organization_id != params["organization_id_1"] or row.version != params["version_1"]:
            return SimpleNamespace(rowcount=0)
        for key, value in params.items():
            if not key.endswith("_1") and hasattr(row, key):
                setattr(row, key, value)
        return SimpleNamespace(rowcount=1)

    async def commit(self):
        if self.fail_commit:
            raise RuntimeError("database unavailable")
        if self.pending is not None:
            self.rows[self.pending.task_id] = self.pending

    async def rollback(self):
        return None


def session_factory(rows, *, fail_commit=False):
    return lambda: MemorySession(rows, fail_commit)


@pytest.mark.asyncio
async def test_new_coordinator_resumes_persisted_plan_and_skips_completed_step():
    rows = {}
    first_calls = []

    async def first_handler(goal, _context):
        first_calls.append(goal)
        return {"success": goal == "Step A", "error": "stop after checkpoint"}

    async def llm(_prompt):
        return '{"steps": [' \
            '{"goal": "Step A", "completion_condition": "done", "failure_strategy": "abort", "max_retries": 0},' \
            '{"goal": "Step B", "completion_condition": "done", "failure_strategy": "abort", "max_retries": 0}]}'

    first = AgentCoordinator(
        PlannerAgent(llm),
        ExecutorAgent(first_handler),
        session_factory=session_factory(rows),
    )
    stopped = await first.run("task_s2", "org_s2", "password=secret; source approved supplier")
    assert stopped.status == "failed"
    assert first_calls == ["Step A", "Step B"]
    assert rows["task_s2"].navigation_goal == "password=******** source approved supplier"
    assert rows["task_s2"].current_plan["navigation_goal"] == rows["task_s2"].navigation_goal

    resumed_calls = []

    async def resumed_handler(goal, _context):
        resumed_calls.append(goal)
        return {"success": True, "data": {}}

    second = AgentCoordinator(
        PlannerAgent(llm),
        ExecutorAgent(resumed_handler),
        session_factory=session_factory(rows),
    )
    completed = await second.run("task_s2", "org_s2", "ignored client goal", resume_from=["untrusted"])

    assert completed.status == "completed"
    assert resumed_calls == ["Step B"]
    assert len(completed.completed_subtasks) == 2
    assert completed.version == rows["task_s2"].version


@pytest.mark.asyncio
async def test_replan_count_and_plan_version_are_persisted():
    rows = {}

    async def llm(prompt):
        if "## Failed Step" in prompt:
            return '{"steps": [{"goal": "Alternative", "completion_condition": "done", "failure_strategy": "abort"}]}'
        return '{"steps": [{"goal": "Fails once", "completion_condition": "done", "failure_strategy": "replan", "max_retries": 0}]}'

    async def handler(goal, _context):
        return {"success": goal == "Alternative", "error": "blocked"}

    state = await AgentCoordinator(
        PlannerAgent(llm),
        ExecutorAgent(handler),
        session_factory=session_factory(rows),
    ).run("task_replan", "org_s2", "Source MRO parts")

    assert state.status == "completed"
    assert rows["task_replan"].total_replans == 1
    assert rows["task_replan"].current_plan["is_replan"] is True


@pytest.mark.asyncio
async def test_cross_org_load_and_stale_version_are_rejected():
    rows = {}

    async def handler(_goal, _context):
        return {"success": True, "data": {}}

    coordinator = AgentCoordinator(
        PlannerAgent(), ExecutorAgent(handler), session_factory=session_factory(rows)
    )
    await coordinator.run("task_conflict", "org_a", "Source office chairs")

    with pytest.raises(CoordinationStateConflict):
        await AgentCoordinator(
            PlannerAgent(), ExecutorAgent(handler), session_factory=session_factory(rows)
        ).run("task_conflict", "org_b", "Source office chairs")

    first = await coordinator._load_state("task_conflict", "org_a")
    stale = first.model_copy(deep=True)
    first.status = "running"
    stale.status = "running"
    await coordinator._save_state(first)
    with pytest.raises(CoordinationStateConflict):
        await coordinator._save_state(stale)


@pytest.mark.asyncio
async def test_database_failure_never_returns_success():
    async def handler(_goal, _context):
        return {"success": True, "data": {}}

    with pytest.raises(CoordinationPersistenceError):
        await AgentCoordinator(
            PlannerAgent(),
            ExecutorAgent(handler),
            session_factory=session_factory({}, fail_commit=True),
        ).run("task_db_down", "org_s2", "Source office chairs")


@pytest.mark.asyncio
async def test_real_skyvern_ids_are_kept_in_durable_snapshot():
    rows = {}

    async def llm(_prompt):
        return '{"steps": [{"goal": "Inspect supplier", "completion_condition": "Evidence exists", "failure_strategy": "abort"}]}'

    async def handler(_goal, _context):
        data = {
            "skyvern_task_id": "tsk_child",
            "status": "completed",
            "artifact_id": "art_child",
            "page_url": "https://supplier.example/quote",
            "simulated": False,
        }
        return {"success": True, "data": data, **data}

    await AgentCoordinator(
        PlannerAgent(llm),
        ExecutorAgent(handler),
        session_factory=session_factory(rows),
    ).run("task_parent", "org_s2", "Inspect allowlisted supplier")

    assert rows["task_parent"].current_plan["subtasks"][0]["result_data"] == {
        "skyvern_task_id": "tsk_child",
        "status": "completed",
        "artifact_id": "art_child",
        "page_url": "https://supplier.example/quote",
        "simulated": False,
    }
