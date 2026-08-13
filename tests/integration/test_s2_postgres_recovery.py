"""Opt-in S2 recovery check against a migrated PostgreSQL task."""

import os

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from enterprise.agent.coordinator import AgentCoordinator
from enterprise.agent.executor import ExecutorAgent
from enterprise.agent.planner import PlannerAgent
from enterprise.audit.models import AuditLogModel
from enterprise.auth.models import TaskExtensionModel
from enterprise.procurement.models import (
    HumanReviewStatus,
    ProcurementCoordinationStateModel,
    ProcurementHumanReviewModel,
)
from skyvern.forge.sdk.db.models import TaskModel

TASK_ID = os.getenv("S2_POSTGRES_TASK_ID")
pytestmark = pytest.mark.skipif(not TASK_ID, reason="set S2_POSTGRES_TASK_ID to an existing local task")


@pytest.mark.asyncio
async def test_new_coordinator_recovers_from_postgres() -> None:
    engine = create_async_engine(os.environ["DATABASE_STRING"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        task = await session.scalar(select(TaskModel).where(TaskModel.task_id == TASK_ID))
        assert task is not None
        await session.execute(
            delete(ProcurementCoordinationStateModel).where(
                ProcurementCoordinationStateModel.task_id == TASK_ID,
            )
        )
        await session.commit()

    async def planner_llm(_prompt):
        return '{"steps": [' \
            '{"goal": "Checkpoint A", "completion_condition": "done", "failure_strategy": "abort", "max_retries": 0},' \
            '{"goal": "Checkpoint B", "completion_condition": "done", "failure_strategy": "abort", "max_retries": 0}]}'

    async def first_handler(goal, _context):
        return {"success": goal == "Checkpoint A", "error": "intentional checkpoint"}

    try:
        first = await AgentCoordinator(
            PlannerAgent(planner_llm),
            ExecutorAgent(first_handler),
            session_factory=sessions,
        ).run(TASK_ID, task.organization_id, "Synthetic S2 recovery check")
        assert first.status == "failed"

        calls = []

        async def resumed_handler(goal, _context):
            calls.append(goal)
            return {"success": True, "data": {}}

        second = await AgentCoordinator(
            PlannerAgent(planner_llm),
            ExecutorAgent(resumed_handler),
            session_factory=sessions,
        ).run(TASK_ID, task.organization_id, "ignored")

        assert second.status == "completed"
        assert calls == ["Checkpoint B"]
    finally:
        async with sessions() as session:
            await session.execute(
                delete(ProcurementCoordinationStateModel).where(
                    ProcurementCoordinationStateModel.task_id == TASK_ID,
                )
            )
            await session.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_replan_limit_creates_s1_review() -> None:
    engine = create_async_engine(os.environ["DATABASE_STRING"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    review_id = None
    async with sessions() as session:
        context = await session.scalar(
            select(TaskExtensionModel).where(TaskExtensionModel.task_id == TASK_ID)
        )
        if context is None or context.category_id is None:
            pytest.skip("selected task has no procurement category context")
        existing = await session.scalar(
            select(ProcurementHumanReviewModel).where(
                ProcurementHumanReviewModel.task_id == TASK_ID,
                ProcurementHumanReviewModel.status == HumanReviewStatus.PENDING.value,
            )
        )
        if existing is not None:
            pytest.skip("selected task already has a pending review")

    async def planner_llm(_prompt):
        return '{"steps": [{"goal": "Blocked step", "completion_condition": "done", "failure_strategy": "replan", "max_retries": 0}]}'

    async def handler(_goal, _context):
        return {"success": False, "error": "synthetic failure"}

    try:
        state = await AgentCoordinator(
            PlannerAgent(planner_llm),
            ExecutorAgent(handler),
            max_replans=0,
            session_factory=sessions,
        ).run(TASK_ID, context.organization_id, "Synthetic S2 review check")
        assert state.status == "needs_human"

        async with sessions() as session:
            review = await session.scalar(
                select(ProcurementHumanReviewModel).where(
                    ProcurementHumanReviewModel.task_id == TASK_ID,
                    ProcurementHumanReviewModel.reason_code == "planner_replan_limit_exceeded",
                )
            )
            assert review is not None
            review_id = review.review_id
            audit = await session.scalar(
                select(AuditLogModel).where(AuditLogModel.business_object_id == review_id)
            )
            assert audit is not None
    finally:
        async with sessions() as session:
            if review_id is not None:
                await session.execute(
                    delete(AuditLogModel).where(AuditLogModel.business_object_id == review_id)
                )
                await session.execute(
                    delete(ProcurementHumanReviewModel).where(
                        ProcurementHumanReviewModel.review_id == review_id,
                    )
                )
            await session.execute(
                delete(ProcurementCoordinationStateModel).where(
                    ProcurementCoordinationStateModel.task_id == TASK_ID,
                )
            )
            await session.commit()
        await engine.dispose()
