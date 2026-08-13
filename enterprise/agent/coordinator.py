"""AgentCoordinator: orchestrates procurement Planner + Executor communication.

Manages the full lifecycle of a multi-step task:
1. Planner creates initial plan
2. Executor runs sub-tasks sequentially
3. On failure, Coordinator asks Planner to replan
4. Sub-task states persist for resumption
5. Audit logging at sub-task granularity
"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from enterprise.audit.models import ActionType, AuditLogModel, generate_audit_log_id
from enterprise.audit.sanitizer import sanitize_input, sanitize_payload
from enterprise.auth.models import TaskExtensionModel
from enterprise.procurement.models import (
    HumanReviewStatus,
    ProcurementCoordinationStateModel,
    ProcurementHumanReviewModel,
    generate_human_review_id,
)

from .executor import ExecutorAgent
from .planner import PlannerAgent
from .schemas import (
    CoordinationState,
    ExecutionResult,
    FailureStrategy,
    SubTask,
    SubTaskStatus,
    TaskPlan,
)

logger = logging.getLogger(__name__)


class CoordinationStateConflict(RuntimeError):
    """A stale or cross-organization coordination snapshot cannot be saved."""


class CoordinationPersistenceError(RuntimeError):
    """A coordination snapshot could not be durably stored."""


class AgentCoordinator:
    """Orchestrates Planner and Executor agents.

    Handles:
    - Initial plan creation
    - Sequential sub-task execution
    - Failure detection and replanning
    - Breakpoint resumption (skip already-completed sub-tasks)
    - Audit callback integration
    """

    def __init__(
        self,
        planner: PlannerAgent,
        executor: ExecutorAgent,
        audit_callback=None,
        max_replans: int = 3,
        session_factory=None,
    ):
        """
        Args:
            planner: PlannerAgent instance.
            executor: ExecutorAgent instance.
            audit_callback: Optional async callback(subtask, result) for audit logging.
            max_replans: Maximum number of replanning attempts.
            session_factory: Async SQLAlchemy session factory for durable production state.
        """
        self.planner = planner
        self.executor = executor
        self.audit_callback = audit_callback
        self.max_replans = max_replans
        # ponytail: no repository layer; the coordinator owns its one-row snapshot.
        self.session_factory = session_factory

    async def _load_state(self, task_id: str, org_id: str) -> CoordinationState | None:
        if self.session_factory is None:
            return None
        async with self.session_factory() as session:
            row = await session.scalar(
                select(ProcurementCoordinationStateModel).where(
                    ProcurementCoordinationStateModel.task_id == task_id,
                    ProcurementCoordinationStateModel.organization_id == org_id,
                )
            )
            if row is None:
                other_org = await session.scalar(
                    select(ProcurementCoordinationStateModel.task_id).where(
                        ProcurementCoordinationStateModel.task_id == task_id,
                    )
                )
                if other_org is not None:
                    raise CoordinationStateConflict("Coordination task belongs to another organization")
                return None
        return CoordinationState(
            task_id=row.task_id,
            org_id=row.organization_id,
            navigation_goal=row.navigation_goal,
            current_plan=TaskPlan.model_validate(row.current_plan),
            completed_subtasks=list(row.completed_subtask_ids),
            total_replans=row.total_replans,
            max_replans=row.max_replans,
            status=row.status,
            error_code=row.error_code,
            error_message=row.error_code,
            version=row.version,
        )

    async def _save_state(self, state: CoordinationState) -> None:
        if self.session_factory is None:
            return
        if state.current_plan is None:
            raise CoordinationPersistenceError("Cannot persist coordination state without a plan")
        safe_goal = sanitize_input(state.navigation_goal) or ""
        plan_data = state.current_plan.model_dump(mode="json")
        plan_data["navigation_goal"] = safe_goal
        plan_data["replan_reason"] = sanitize_input(plan_data.get("replan_reason"))
        for subtask in plan_data["subtasks"]:
            subtask["error_message"] = sanitize_input(subtask.get("error_message"))
            result = subtask.get("result_data") or {}
            subtask["result_data"] = {
                key: result[key]
                for key in ("skyvern_task_id", "status", "artifact_id", "page_url", "simulated")
                if key in result
            } or None
        values = {
            "navigation_goal": safe_goal,
            "current_plan": sanitize_payload(plan_data),
            "completed_subtask_ids": list(state.completed_subtasks),
            "total_replans": state.total_replans,
            "max_replans": state.max_replans,
            "status": state.status,
            "error_code": state.error_code,
            "modified_at": datetime.utcnow(),
        }
        try:
            async with self.session_factory() as session:
                if state.version == 0:
                    session.add(ProcurementCoordinationStateModel(
                        task_id=state.task_id,
                        organization_id=state.org_id,
                        version=1,
                        **values,
                    ))
                    await session.commit()
                    state.version = 1
                    return
                result = await session.execute(
                    update(ProcurementCoordinationStateModel)
                    .where(
                        ProcurementCoordinationStateModel.task_id == state.task_id,
                        ProcurementCoordinationStateModel.organization_id == state.org_id,
                        ProcurementCoordinationStateModel.version == state.version,
                    )
                    .values(version=state.version + 1, **values)
                )
                if result.rowcount != 1:
                    await session.rollback()
                    raise CoordinationStateConflict("Coordination state version conflict")
                await session.commit()
                state.version += 1
        except CoordinationStateConflict:
            raise
        except IntegrityError as exc:
            raise CoordinationStateConflict("Coordination state already exists") from exc
        except Exception as exc:
            raise CoordinationPersistenceError("Coordination state persistence failed") from exc

    async def _ensure_human_review(self, state: CoordinationState) -> None:
        if self.session_factory is None:
            return
        async with self.session_factory() as session:
            pending = await session.scalar(
                select(ProcurementHumanReviewModel).where(
                    ProcurementHumanReviewModel.task_id == state.task_id,
                    ProcurementHumanReviewModel.organization_id == state.org_id,
                    ProcurementHumanReviewModel.status == HumanReviewStatus.PENDING.value,
                )
            )
            if pending is not None:
                return
            context = await session.scalar(
                select(TaskExtensionModel).where(
                    TaskExtensionModel.task_id == state.task_id,
                    TaskExtensionModel.organization_id == state.org_id,
                )
            )
            if context is None or context.category_id is None:
                raise CoordinationPersistenceError("Procurement task context is required for human review")
            review_id = generate_human_review_id()
            session.add(ProcurementHumanReviewModel(
                review_id=review_id,
                task_id=state.task_id,
                organization_id=state.org_id,
                department_id=context.department_id,
                category_id=context.category_id,
                status=HumanReviewStatus.PENDING.value,
                reason_code="planner_replan_limit_exceeded",
                safe_error_summary="Planner replan limit exceeded",
                action_index=len(state.completed_subtasks),
                action_type="planner_replan",
                created_by=context.created_by,
            ))
            session.add(AuditLogModel(
                audit_log_id=generate_audit_log_id(),
                task_id=state.task_id,
                organization_id=state.org_id,
                department_id=context.department_id,
                business_object_type="procurement_human_review",
                business_object_id=review_id,
                action_index=len(state.completed_subtasks),
                action_type=ActionType.HUMAN_REVIEW_CREATED.value,
                executor=context.created_by,
                execution_result=HumanReviewStatus.PENDING.value,
                input_value='{"reason_code":"planner_replan_limit_exceeded"}',
                error_message="Planner replan limit exceeded",
            ))
            await session.commit()

    async def run(
        self,
        task_id: str,
        org_id: str,
        navigation_goal: str,
        context: dict[str, Any] | None = None,
        resume_from: list[str] | None = None,
    ) -> CoordinationState:
        """Execute a full procurement task through Planner -> Executor coordination.

        Args:
            task_id: Unique task identifier.
            org_id: Organization ID for tenant isolation.
            navigation_goal: High-level procurement goal.
            context: Shared execution context.
            resume_from: List of already-completed subtask IDs (for resumption).

        Returns:
            CoordinationState with final status and results.
        """
        state = await self._load_state(task_id, org_id)
        if state is None:
            state = CoordinationState(
                task_id=task_id,
                org_id=org_id,
                navigation_goal=navigation_goal,
                completed_subtasks=resume_from or [] if self.session_factory is None else [],
                max_replans=self.max_replans,
            )
        elif state.status in ("completed", "needs_human"):
            return state
        else:
            state.status = "running"
            state.error_code = None
            state.error_message = None

        # Step 1: Create or resume the durable plan.
        plan = state.current_plan
        if plan is None:
            try:
                plan = await self.planner.create_plan(navigation_goal, context)
            except Exception as e:
                logger.error("Coordinator: planning failed for task %s: %s", task_id, e)
                state.status = "failed"
                state.error_code = "planning_failed"
                state.error_message = "Planning failed"
                state.current_plan = TaskPlan(navigation_goal=navigation_goal)
                await self._save_state(state)
                return state

        state.current_plan = plan
        await self._save_state(state)
        logger.info(
            "Coordinator: task %s planned with %d sub-tasks",
            task_id, len(plan.subtasks),
        )

        # Step 2: Execute sub-tasks
        completed_subtasks: list[SubTask] = []

        return await self._execute_plan(
            state, plan, completed_subtasks, context,
        )

    async def _execute_plan(
        self,
        state: CoordinationState,
        plan: TaskPlan,
        completed_subtasks: list[SubTask],
        context: dict[str, Any] | None,
    ) -> CoordinationState:
        """Execute all sub-tasks in a plan."""

        for subtask in plan.subtasks:
            # Skip already-completed sub-tasks (resumption)
            if subtask.subtask_id in state.completed_subtasks:
                logger.info(
                    "Coordinator: skipping already-completed subtask %s",
                    subtask.subtask_id,
                )
                completed_subtasks.append(subtask)
                continue

            # Execute
            subtask.status = SubTaskStatus.RUNNING
            subtask.started_at = datetime.utcnow()
            await self._save_state(state)
            result = await self.executor.execute_subtask(subtask, context)
            await self._save_state(state)

            # Audit callback
            if self.audit_callback:
                try:
                    await self.audit_callback(subtask, result)
                except Exception as e:
                    logger.warning(
                        "Coordinator: audit callback failed for subtask %s: %s",
                        subtask.subtask_id, e,
                    )

            if result.success:
                state.completed_subtasks.append(subtask.subtask_id)
                completed_subtasks.append(subtask)
                await self._save_state(state)
                continue

            # Handle failure based on strategy
            outcome = await self._handle_failure(
                state, plan, subtask, result, completed_subtasks, context,
            )
            if outcome == "aborted":
                return state
            if outcome == "replanned":
                return state  # _handle_failure already recursed into new plan

        # All sub-tasks completed
        state.status = "completed"
        state.error_code = None
        await self._save_state(state)
        logger.info("Coordinator: task %s completed successfully", state.task_id)
        return state

    async def _handle_failure(
        self,
        state: CoordinationState,
        plan: TaskPlan,
        failed_subtask: SubTask,
        result: ExecutionResult,
        completed_subtasks: list[SubTask],
        context: dict[str, Any] | None,
    ) -> str:
        """Handle a sub-task failure based on its failure strategy.

        Returns:
            "continued" — skip and continue
            "aborted" — task is done (failed or needs_human)
            "replanned" — new plan generated and executed
        """
        strategy = failed_subtask.failure_strategy

        if strategy == FailureStrategy.SKIP:
            logger.info(
                "Coordinator: skipping failed subtask %s",
                failed_subtask.subtask_id,
            )
            failed_subtask.status = SubTaskStatus.SKIPPED
            state.completed_subtasks.append(failed_subtask.subtask_id)
            completed_subtasks.append(failed_subtask)
            await self._save_state(state)
            return "continued"

        if strategy == FailureStrategy.ABORT:
            logger.error(
                "Coordinator: aborting task %s at subtask %s",
                state.task_id, failed_subtask.subtask_id,
            )
            state.status = "failed"
            state.error_code = "subtask_aborted"
            state.error_message = (
                f"Sub-task {failed_subtask.index} failed: {result.error_message}"
            )
            await self._save_state(state)
            return "aborted"

        if strategy == FailureStrategy.REPLAN:
            if state.total_replans >= state.max_replans:
                logger.error(
                    "Coordinator: max replans (%d) reached for task %s",
                    state.max_replans, state.task_id,
                )
                state.status = "needs_human"
                state.error_code = "max_replans_exceeded"
                state.error_message = "Max replans exceeded"
                await self._ensure_human_review(state)
                await self._save_state(state)
                return "aborted"

            state.total_replans += 1
            await self._save_state(state)
            logger.info(
                "Coordinator: replanning task %s (attempt %d/%d)",
                state.task_id, state.total_replans, state.max_replans,
            )

            try:
                new_plan = await self.planner.replan(
                    original_goal=state.navigation_goal,
                    completed_subtasks=completed_subtasks,
                    failed_subtask=failed_subtask,
                    failure_reason=result.error_message or "Unknown error",
                    context=context,
                )
            except Exception as e:
                logger.error("Coordinator: replan failed: %s", e)
                state.status = "needs_human"
                state.error_code = "replan_failed"
                state.error_message = "Replan failed"
                await self._ensure_human_review(state)
                await self._save_state(state)
                return "aborted"

            state.current_plan = new_plan
            await self._save_state(state)

            # Execute the new plan
            await self._execute_plan(state, new_plan, completed_subtasks, context)
            return "replanned"

        # Default: RETRY strategy is handled by ExecutorAgent internally
        # If we reach here, retries were exhausted
        state.status = "failed"
        state.error_code = "subtask_retries_exhausted"
        state.error_message = (
            f"Sub-task {failed_subtask.index} failed after retries: {result.error_message}"
        )
        await self._save_state(state)
        return "aborted"
