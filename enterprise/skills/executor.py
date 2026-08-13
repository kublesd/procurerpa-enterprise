"""Skill execution engine.

Runs a sequence of skills (a skill pipeline) with error handling,
retry logic, and audit logging integration.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from skyvern.forge.sdk.schemas.tasks import TaskRequest

from .base import (
    BaseSkill,
    ErrorStrategy,
    SkillResult,
    SkillStatus,
    get_skill,
)

logger = logging.getLogger(__name__)


@dataclass
class SkillStep:
    """A single step in a skill pipeline."""

    skill_name: str
    params: dict[str, Any]
    description: str = ""
    error_strategy_override: str | None = None  # override skill default


class CompiledSkillPipeline(BaseModel):
    """Safe native Skyvern fields compiled from first-stage Skill steps."""

    navigation_goal: str
    navigation_payload: dict[str, Any] = Field(default_factory=dict)
    data_extraction_goal: str | None = None
    extracted_information_schema: dict[str, Any] | None = None
    complete_criterion: str
    requires_download: bool = Field(default=False, exclude=True)
    expected_headers: list[str] = Field(default_factory=list, exclude=True)

    def to_task_request(self, *, title: str, url: str, model: dict[str, str] | None = None) -> TaskRequest:
        return TaskRequest(
            title=title,
            url=url,
            navigation_goal=self.navigation_goal,
            navigation_payload=self.navigation_payload or None,
            data_extraction_goal=self.data_extraction_goal,
            extracted_information_schema=self.extracted_information_schema,
            complete_criterion=self.complete_criterion,
            model=model,
        )

    def validate_extracted_information(self, value: Any) -> dict[str, Any]:
        if self.extracted_information_schema is None:
            return {}
        try:
            extracted = _ExtractedTable.model_validate(value)
        except ValidationError as exc:
            raise ValueError("table extraction did not match the compiled schema") from exc
        missing = [
            header
            for row in extracted.rows
            for header in self.expected_headers
            if header not in row
        ]
        if missing:
            raise ValueError("table extraction did not match the compiled schema")
        return extracted.model_dump(mode="json")


class _ExtractedTable(BaseModel):
    rows: list[dict[str, str | int | float | None]]


_SKILL_GOALS = {
    "login": "Authenticate if a login form is present using server-managed credentials.",
    "form_fill": "Fill the procurement form using the structured navigation payload.",
    "table_extract": "Extract the visible procurement table using the requested schema.",
    "file_download": "Download the requested procurement attachment and retain native evidence.",
    "search_and_select": "Search for and select the requested procurement record.",
    "pagination": "Traverse the requested result pages within the configured limit.",
    "session_keep_alive": "Keep the current Skyvern browser session active for this task.",
}
_SECRET_KEY = re.compile(r"password|secret|token|username|credential", re.IGNORECASE)
_URL_VALUE = re.compile(r"^https?://", re.IGNORECASE)


def _safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: safe
            for key, item in value.items()
            if not _SECRET_KEY.search(key)
            and (safe := _safe_value(item)) is not None
        }
    if isinstance(value, list):
        return [safe for item in value if (safe := _safe_value(item)) is not None]
    if isinstance(value, str) and _URL_VALUE.match(value.strip()):
        return None
    return value


def compile_skill_pipeline(steps: list[SkillStep]) -> CompiledSkillPipeline:
    """Compile registered Skills into one native Skyvern task without credentials or URLs."""
    goals: list[str] = []
    payload: dict[str, Any] = {}
    headers: list[str] = []
    requires_download = False

    for index, step in enumerate(steps):
        skill_cls = get_skill(step.skill_name)
        if skill_cls is None or step.skill_name not in _SKILL_GOALS:
            raise ValueError(f"Unsupported production skill: {step.skill_name}")
        params = skill_cls().validate_params(step.params).model_dump(mode="json")
        goals.append(f"{index + 1}. {_SKILL_GOALS[step.skill_name]}")

        if step.skill_name == "form_fill":
            payload["form_fields"] = _safe_value(params.get("field_mapping", {}))
        elif step.skill_name == "search_and_select":
            payload["search"] = _safe_value({
                "search_text": params.get("search_text"),
                "target_text": params.get("target_text"),
            })
        elif step.skill_name == "pagination":
            payload["pagination"] = _safe_value({
                "max_pages": params.get("max_pages"),
                "next_button_text": params.get("next_button_text"),
            })
        elif step.skill_name == "table_extract":
            headers.extend(params.get("headers") or [])
        elif step.skill_name == "file_download":
            requires_download = True
            payload["download"] = _safe_value({"trigger_text": params.get("trigger_text")})

    schema = None
    extraction_goal = None
    if any(step.skill_name == "table_extract" for step in steps):
        item_schema: dict[str, Any] = {"type": "object"}
        if headers:
            item_schema.update({
                "properties": {header: {"type": ["string", "number", "integer", "null"]} for header in headers},
                "required": headers,
            })
        schema = {
            "type": "object",
            "properties": {"rows": {"type": "array", "items": item_schema}},
            "required": ["rows"],
        }
        extraction_goal = "Extract the visible procurement table as rows matching the provided JSON schema."

    return CompiledSkillPipeline(
        navigation_goal="Execute in order: " + " ".join(goals),
        navigation_payload=payload,
        data_extraction_goal=extraction_goal,
        extracted_information_schema=schema,
        complete_criterion=(
            "The requested file is downloaded and native task evidence is recorded."
            if requires_download
            else "The procurement steps finish and native task evidence is recorded."
        ),
        requires_download=requires_download,
        expected_headers=list(dict.fromkeys(headers)),
    )


@dataclass
class PipelineResult:
    """Result of executing a full skill pipeline."""

    success: bool = True
    steps_completed: int = 0
    steps_total: int = 0
    step_results: list[dict[str, Any]] = field(default_factory=list)
    total_duration_ms: int = 0
    aborted_at_step: int | None = None
    error_message: str | None = None
    execution_mode: str = "simulated"  # first-stage pipeline is not connected to Skyvern


async def execute_pipeline(
    steps: list[SkillStep],
    context: dict[str, Any] | None = None,
    audit_callback=None,
) -> PipelineResult:
    """Execute a sequence of skill steps.

    Args:
        steps: Ordered list of SkillSteps to execute.
        context: Shared execution context (browser page, session, etc.).
        audit_callback: Optional async callback(step_index, skill_name, params_dict, result)
                        for audit logging.

    Returns:
        PipelineResult with per-step results and overall status.
    """
    pipeline_start = time.monotonic()
    result = PipelineResult(steps_total=len(steps))

    for i, step in enumerate(steps):
        skill_cls = get_skill(step.skill_name)
        if skill_cls is None:
            logger.error("Unknown skill: %s (step %d)", step.skill_name, i)
            result.step_results.append({
                "step": i,
                "skill": step.skill_name,
                "status": "failed",
                "error": f"Unknown skill: {step.skill_name}",
            })
            result.success = False
            result.aborted_at_step = i
            result.error_message = f"Unknown skill: {step.skill_name}"
            break

        skill: BaseSkill = skill_cls()
        error_strategy = (
            ErrorStrategy(step.error_strategy_override)
            if step.error_strategy_override
            else skill.error_strategy
        )

        # Validate params
        try:
            validated_params = skill.validate_params(step.params)
        except Exception as e:
            logger.error("Param validation failed for %s: %s", step.skill_name, e)
            result.step_results.append({
                "step": i,
                "skill": step.skill_name,
                "status": "failed",
                "error": f"Invalid params: {e}",
            })
            if error_strategy == ErrorStrategy.ABORT:
                result.success = False
                result.aborted_at_step = i
                result.error_message = f"Param validation failed at step {i}"
                break
            continue

        # Execute with retry
        max_attempts = skill.max_retries + 1 if error_strategy == ErrorStrategy.RETRY else 1
        skill_result: SkillResult | None = None

        for attempt in range(max_attempts):
            skill_result = await skill.execute(validated_params, context)

            if skill_result.status == SkillStatus.COMPLETED:
                break

            if attempt < max_attempts - 1:
                logger.info(
                    "Retrying %s (attempt %d/%d)",
                    step.skill_name, attempt + 2, max_attempts,
                )

        assert skill_result is not None

        # Record step result
        step_record = {
            "step": i,
            "skill": step.skill_name,
            "status": skill_result.status.value,
            "duration_ms": skill_result.duration_ms,
            "data": skill_result.data,
        }
        if skill_result.error_message:
            step_record["error"] = skill_result.error_message
        result.step_results.append(step_record)

        # Audit callback
        if audit_callback:
            try:
                audit_dict = skill.to_audit_dict(validated_params)
                await audit_callback(i, step.skill_name, audit_dict, skill_result)
            except Exception as e:
                logger.warning("Audit callback failed for step %d: %s", i, e)

        # Handle failure based on error strategy
        if skill_result.status in (SkillStatus.FAILED, SkillStatus.SKIPPED):
            if skill_result.status == SkillStatus.FAILED:
                if error_strategy == ErrorStrategy.ABORT:
                    result.success = False
                    result.aborted_at_step = i
                    result.error_message = (
                        f"Step {i} ({step.skill_name}) failed: {skill_result.error_message}"
                    )
                    break
                elif error_strategy == ErrorStrategy.SKIP:
                    logger.info("Skipping failed step %d (%s)", i, step.skill_name)
                    continue
            # RETRY exhausted falls through here
            if error_strategy == ErrorStrategy.RETRY and skill_result.status == SkillStatus.FAILED:
                result.success = False
                result.aborted_at_step = i
                result.error_message = (
                    f"Step {i} ({step.skill_name}) failed after retries: "
                    f"{skill_result.error_message}"
                )
                break

        result.steps_completed += 1

    result.total_duration_ms = int((time.monotonic() - pipeline_start) * 1000)
    return result
