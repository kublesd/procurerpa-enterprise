"""One real, allowlisted Skyvern tracer bullet for the procurement Executor."""

import json
from typing import Any

from fastapi import BackgroundTasks

from enterprise.audit.models import ActionType, AuditLogModel, generate_audit_log_id
from enterprise.audit.sanitizer import sanitize_input
from enterprise.auth.models import TaskExtensionModel
from enterprise.llm.model_router import (
    ModelRoutingUnavailable,
    ProcurementPageKind,
    RoutingDecision,
    resolve_procurement_page,
)
from enterprise.procurement.models import ProcurementHumanReviewModel, generate_human_review_id
from enterprise.skills.executor import CompiledSkillPipeline
from skyvern.forge.sdk.artifact.models import ArtifactType
from skyvern.forge.sdk.schemas.tasks import TaskRequest, TaskStatus

EVIDENCE_TYPES = [ArtifactType.HTML_SCRAPE, ArtifactType.SCREENSHOT_FINAL, ArtifactType.SCREENSHOT_ACTION]
TRACER_GOAL = "Verify the allowlisted supplier page loaded and capture browser evidence."


class SkyvernProcurementHandler:
    """Run one procurement subtask through native Skyvern and persist its evidence."""

    def __init__(
        self,
        *,
        database: Any,
        task_runner: Any,
        organization_id: str,
        department_id: str,
        category_id: str,
        user_id: str,
        url: str,
        allowed_urls: set[str],
        compiled_pipeline: CompiledSkillPipeline | None = None,
        request: Any = None,
        page_kind: ProcurementPageKind | str = ProcurementPageKind.DYNAMIC_QUOTE_PORTAL,
    ) -> None:
        self.database = database
        self.task_runner = task_runner
        self.organization_id = organization_id
        self.department_id = department_id
        self.category_id = category_id
        self.user_id = user_id
        self.url = url
        self.allowed_urls = allowed_urls
        self.compiled_pipeline = compiled_pipeline
        self.request = request
        self.page_kind = page_kind

    async def __call__(self, _goal: str, _context: dict[str, Any]) -> dict[str, Any]:
        if self.url not in self.allowed_urls:
            return self._failure("supplier_url_not_allowlisted")
        organization = await self.database.get_organization(self.organization_id)
        if organization is None:
            return self._failure("organization_not_found")

        try:
            routing = resolve_procurement_page(self.page_kind)
        except ModelRoutingUnavailable:
            return await self._model_unavailable(organization)

        execution_tasks = BackgroundTasks()
        try:
            task_request = (
                self.compiled_pipeline.to_task_request(
                    title="ProcureRPA native Skill Pipeline",
                    url=self.url,
                    model=routing.to_task_model(),
                )
                if self.compiled_pipeline
                else TaskRequest(
                    title="ProcureRPA Executor supplier-page tracer",
                    url=self.url,
                    navigation_goal=TRACER_GOAL,
                    complete_criterion="The allowlisted supplier page loaded successfully.",
                    model=routing.to_task_model(),
                )
            )
            created = await self.task_runner(
                task=task_request,
                organization=organization,
                request=self.request,
                background_tasks=execution_tasks,
                defer_execution=False,
            )
            await self._attach_context(created.task_id)
            await self._audit_routing(created.task_id, routing)
            await execution_tasks()
            task = await self.database.get_task(created.task_id, organization_id=self.organization_id)
        except Exception:
            return self._failure("skyvern_execution_error")

        if task is None:
            return self._failure("skyvern_task_not_found", created.task_id)

        try:
            artifact = await self.database.get_latest_artifact(
                task_id=task.task_id,
                organization_id=self.organization_id,
                artifact_types=EVIDENCE_TYPES,
            )
        except Exception:
            return self._failure("skyvern_artifact_lookup_failed", task.task_id, task.status.value, task.url)
        if task.status != TaskStatus.completed:
            code = "skyvern_task_timed_out" if task.status == TaskStatus.timed_out else "skyvern_task_failed"
            await self._create_review(task.task_id, code, artifact.artifact_id if artifact else None)
            return self._failure(code, task.task_id, task.status.value, task.url)
        if artifact is None or artifact.task_id != task.task_id or artifact.organization_id != self.organization_id:
            await self._create_review(task.task_id, "skyvern_artifact_missing")
            return self._failure("skyvern_artifact_missing", task.task_id, task.status.value, task.url)

        extracted_information = None
        if self.compiled_pipeline and self.compiled_pipeline.extracted_information_schema:
            try:
                extracted_information = self.compiled_pipeline.validate_extracted_information(
                    task.extracted_information,
                )
            except ValueError:
                await self._create_review(task.task_id, "skill_table_schema_invalid", artifact.artifact_id)
                return self._failure("skill_table_schema_invalid", task.task_id, task.status.value, task.url)

        data = {
            "skyvern_task_id": task.task_id,
            "status": task.status.value,
            "artifact_id": artifact.artifact_id,
            "page_url": task.url,
            "simulated": False,
            "model_tier": routing.model_tier.value,
            "model_alias": routing.model_alias,
            "routing_reason_code": routing.reason_code,
        }
        if extracted_information is not None:
            data["extracted_information"] = extracted_information
        await self._audit(task.task_id, artifact.artifact_id, task.url)
        return {"success": True, "data": data, **data}

    async def _model_unavailable(self, organization: Any) -> dict[str, Any]:
        """Persist a stopped native Task so the S1 review has a valid Task foreign key."""
        execution_tasks = BackgroundTasks()
        try:
            request = TaskRequest(title="ProcureRPA model routing review", url=self.url, navigation_goal=TRACER_GOAL)
            created = await self.task_runner(
                task=request,
                organization=organization,
                request=self.request,
                background_tasks=execution_tasks,
                defer_execution=True,
            )
            await self._attach_context(created.task_id)
            await self._create_review(created.task_id, "procurement_model_unavailable")
            try:
                await self.database.update_task(
                    task_id=created.task_id,
                    organization_id=self.organization_id,
                    status=TaskStatus.canceled,
                )
            except Exception:
                pass
            return self._failure("procurement_model_unavailable", created.task_id, TaskStatus.canceled.value, self.url)
        except Exception:
            return self._failure("procurement_model_unavailable")

    async def _audit_routing(self, task_id: str, routing: RoutingDecision) -> None:
        async with self.database.Session() as session:
            row = self._audit_row(task_id, None, self.url, "success")
            row.action_type = "model_route"
            row.input_value = json.dumps({
                "model_tier": routing.model_tier.value,
                "resolved_model_key": routing.resolved_model_key,
                "reason_code": routing.reason_code,
                "step_id": None,
            })
            session.add(row)
            await session.commit()

    async def _attach_context(self, task_id: str) -> None:
        async with self.database.Session() as session:
            session.add(TaskExtensionModel(
                task_id=task_id,
                organization_id=self.organization_id,
                department_id=self.department_id,
                category_id=self.category_id,
                risk_level="low",
                risk_reason="Allowlisted supplier-page tracer bullet",
                risk_result={"risk_level": "low", "source": "deterministic_s3_handler"},
                created_by=self.user_id,
            ))
            await session.commit()

    async def _create_review(self, task_id: str, reason_code: str, artifact_id: str | None = None) -> None:
        async with self.database.Session() as session:
            review_id = generate_human_review_id()
            session.add(ProcurementHumanReviewModel(
                review_id=review_id,
                task_id=task_id,
                organization_id=self.organization_id,
                department_id=self.department_id,
                category_id=self.category_id,
                reason_code=reason_code,
                safe_error_summary=reason_code.replace("_", " "),
                artifact_id=artifact_id,
                action_index=0,
                action_type="skyvern_executor",
                created_by=self.user_id,
            ))
            session.add(self._audit_row(
                task_id,
                artifact_id,
                None,
                "needs_human",
                reason_code,
                business_object_type="procurement_human_review",
                business_object_id=review_id,
                action_type=ActionType.HUMAN_REVIEW_CREATED.value,
            ))
            await session.commit()

    async def _audit(self, task_id: str, artifact_id: str, page_url: str) -> None:
        async with self.database.Session() as session:
            session.add(self._audit_row(task_id, artifact_id, page_url, "success"))
            await session.commit()

    def _audit_row(
        self,
        task_id: str,
        artifact_id: str | None,
        page_url: str | None,
        result: str,
        error: str | None = None,
        business_object_type: str = "skyvern_task",
        business_object_id: str | None = None,
        action_type: str = ActionType.CUSTOM.value,
    ) -> AuditLogModel:
        return AuditLogModel(
            audit_log_id=generate_audit_log_id(),
            task_id=task_id,
            organization_id=self.organization_id,
            department_id=self.department_id,
            business_object_type=business_object_type,
            business_object_id=business_object_id or task_id,
            action_index=0,
            action_type=action_type,
            input_value=json.dumps({"skyvern_task_id": task_id, "artifact_id": artifact_id}),
            page_url=sanitize_input(page_url),
            executor=self.user_id,
            execution_result=result,
            error_message=sanitize_input(error),
        )

    @staticmethod
    def _failure(
        code: str,
        task_id: str | None = None,
        status: str | None = None,
        page_url: str | None = None,
    ) -> dict[str, Any]:
        return {
            "success": False,
            "error": code,
            "skyvern_task_id": task_id,
            "status": status,
            "artifact_id": None,
            "page_url": page_url,
            "simulated": False,
        }
