"""Tests for procurement LLM resilience, task states, and model routing.

Covers:
- Extended task state machine (transitions, terminal states)
- Prompt building with schema enforcement
- Markdown cleanup from LLM responses
- Pydantic validation of LLM output
- Exponential backoff retry (success on 2nd attempt, all fail -> NEEDS_HUMAN)
- Model routing based on page complexity
- Human intervention resolution
"""

import json
import unittest
from unittest.mock import AsyncMock

from pydantic import BaseModel

from enterprise.llm.task_states import (
    EnterpriseTaskStatus,
    TERMINAL_STATES,
    HUMAN_ATTENTION_STATES,
    InvalidTransitionError,
    validate_transition,
)
from enterprise.llm.resilient_caller import (
    build_structured_prompt,
    clean_llm_response,
    parse_and_validate,
    call_llm_with_retry,
)
from enterprise.llm.model_router import (
    ComplexityLevel,
    ModelTier,
    PageFeatures,
    estimate_complexity,
    route_model,
)
from enterprise.llm.human_intervention import (
    ResolutionAction,
    StuckTaskInfo,
    HumanResolution,
    resolve_stuck_task,
)


# ============================================================
# Task State Machine tests
# ============================================================

class TestEnterpriseTaskStatus(unittest.TestCase):
    def test_base_states_exist(self):
        base = {"created", "queued", "running", "completed", "failed",
                "terminated", "timed_out", "canceled"}
        actual = {s.value for s in EnterpriseTaskStatus}
        assert base.issubset(actual)

    def test_enterprise_extensions(self):
        assert EnterpriseTaskStatus.PENDING_APPROVAL.value == "pending_approval"
        assert EnterpriseTaskStatus.NEEDS_HUMAN.value == "needs_human"
        assert EnterpriseTaskStatus.PAUSED.value == "paused"

    def test_is_str_subclass(self):
        assert isinstance(EnterpriseTaskStatus.RUNNING, str)


class TestStateTransitions(unittest.TestCase):
    def test_running_to_pending_approval(self):
        assert validate_transition("running", "pending_approval") is True

    def test_running_to_needs_human(self):
        assert validate_transition("running", "needs_human") is True

    def test_running_to_paused(self):
        assert validate_transition("running", "paused") is True

    def test_pending_approval_to_running(self):
        assert validate_transition("pending_approval", "running") is True

    def test_pending_approval_to_terminated(self):
        assert validate_transition("pending_approval", "terminated") is True

    def test_needs_human_to_running(self):
        assert validate_transition("needs_human", "running") is True

    def test_needs_human_to_terminated(self):
        assert validate_transition("needs_human", "terminated") is True

    def test_paused_to_running(self):
        assert validate_transition("paused", "running") is True

    def test_completed_is_terminal(self):
        with self.assertRaises(InvalidTransitionError):
            validate_transition("completed", "running")

    def test_failed_is_terminal(self):
        with self.assertRaises(InvalidTransitionError):
            validate_transition("failed", "running")

    def test_invalid_transition_raises(self):
        with self.assertRaises(InvalidTransitionError):
            validate_transition("created", "completed")

    def test_terminal_states(self):
        assert "completed" in TERMINAL_STATES
        assert "failed" in TERMINAL_STATES
        assert "terminated" in TERMINAL_STATES
        assert "running" not in TERMINAL_STATES

    def test_human_attention_states(self):
        assert "pending_approval" in HUMAN_ATTENTION_STATES
        assert "needs_human" in HUMAN_ATTENTION_STATES
        assert "paused" in HUMAN_ATTENTION_STATES
        assert "running" not in HUMAN_ATTENTION_STATES


class TestInvalidTransitionError(unittest.TestCase):
    def test_error_message(self):
        err = InvalidTransitionError("running", "created")
        assert "running" in str(err)
        assert "created" in str(err)

    def test_attributes(self):
        err = InvalidTransitionError("a", "b")
        assert err.current_state == "a"
        assert err.target_state == "b"


# ============================================================
# Resilient Caller tests
# ============================================================

class ProcurementPageAction(BaseModel):
    action: str
    target: str
    supplier_name: str
    confidence: float


class TestBuildStructuredPrompt(unittest.TestCase):
    def test_contains_schema(self):
        prompt = build_structured_prompt("Open the supplier quote page", ProcurementPageAction)
        assert "action" in prompt
        assert "target" in prompt
        assert "confidence" in prompt

    def test_contains_task(self):
        prompt = build_structured_prompt("Open the supplier quote page", ProcurementPageAction)
        assert "Open the supplier quote page" in prompt

    def test_contains_json_instruction(self):
        prompt = build_structured_prompt("test", ProcurementPageAction)
        assert "JSON" in prompt
        assert "procurement" in prompt.lower()
        assert "supplier quotes" in prompt
        assert "credentials" in prompt

    def test_additional_context(self):
        prompt = build_structured_prompt(
            "test", ProcurementPageAction, additional_context="Supplier quote page has 3 actions"
        )
        assert "Supplier quote page has 3 actions" in prompt


class TestCleanLLMResponse(unittest.TestCase):
    def test_plain_json(self):
        raw = '{"action": "open_quote", "target": "quote-link", "confidence": 0.9}'
        assert clean_llm_response(raw) == raw.strip()

    def test_markdown_json_fence(self):
        raw = '```json\n{"action": "open_quote"}\n```'
        assert clean_llm_response(raw) == '{"action": "open_quote"}'

    def test_markdown_plain_fence(self):
        raw = '```\n{"action": "open_quote"}\n```'
        assert clean_llm_response(raw) == '{"action": "open_quote"}'

    def test_whitespace_stripped(self):
        raw = '\n\n  {"action": "open_quote"}  \n\n'
        assert clean_llm_response(raw) == '{"action": "open_quote"}'

    def test_no_fence_preserved(self):
        raw = '{"quote_reference": "quote-demo-001"}'
        assert clean_llm_response(raw) == raw


class TestParseAndValidate(unittest.TestCase):
    def test_valid_json(self):
        raw = '{"action": "open_quote", "target": "quote-link", "supplier_name": "Acme Industrial", "confidence": 0.95}'
        result = parse_and_validate(raw, ProcurementPageAction)
        assert result.action == "open_quote"
        assert result.target == "quote-link"
        assert result.supplier_name == "Acme Industrial"
        assert result.confidence == 0.95

    def test_invalid_json(self):
        with self.assertRaises(json.JSONDecodeError):
            parse_and_validate("not json at all", ProcurementPageAction)

    def test_schema_mismatch(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            parse_and_validate('{"action": "open_quote"}', ProcurementPageAction)

    def test_markdown_wrapped(self):
        raw = '```json\n{"action": "open_quote", "target": "quote-link", "supplier_name": "Acme Industrial", "confidence": 0.8}\n```'
        result = parse_and_validate(raw, ProcurementPageAction)
        assert result.action == "open_quote"


class TestCallLLMWithRetry(unittest.IsolatedAsyncioTestCase):
    async def test_success_first_attempt(self):
        mock_llm = AsyncMock(return_value='```json\n{"action": "open_quote", "target": "quote-link", "supplier_name": "Acme Industrial", "confidence": 0.9}\n```')
        prompt = build_structured_prompt("Extract the supplier quote", ProcurementPageAction)

        result = await call_llm_with_retry(
            mock_llm, prompt, ProcurementPageAction,
            max_retries=3, retry_delays=[0, 0, 0],
        )

        assert result.success is True
        assert result.data.action == "open_quote"
        assert result.attempts == 1
        assert result.needs_human is False

    async def test_success_second_attempt(self):
        responses = iter([
            "not valid json",
            '{"action": "open_quote", "target": "quote-link", "supplier_name": "Acme Industrial", "confidence": 0.9}',
        ])
        mock_llm = AsyncMock(side_effect=lambda p: next(responses))

        result = await call_llm_with_retry(
            mock_llm, "test", ProcurementPageAction,
            max_retries=3, retry_delays=[0, 0, 0],
        )

        assert result.success is True
        assert result.attempts == 2
        assert len(result.errors) == 1

    async def test_all_fail_needs_human(self):
        mock_llm = AsyncMock(return_value="garbage output")

        result = await call_llm_with_retry(
            mock_llm, "test", ProcurementPageAction,
            max_retries=3, retry_delays=[0, 0, 0],
        )

        assert result.success is False
        assert result.needs_human is True
        assert result.attempts == 3
        assert len(result.errors) == 3

    async def test_llm_exception_retried(self):
        call_count = 0

        async def flaky_llm(prompt):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("LLM service unavailable")
            return '{"action": "open_quote", "target": "quote-link", "supplier_name": "Acme Industrial", "confidence": 0.8}'

        result = await call_llm_with_retry(
            flaky_llm, "test", ProcurementPageAction,
            max_retries=3, retry_delays=[0, 0, 0],
        )

        assert result.success is True
        assert result.attempts == 3
        assert len(result.errors) == 2

    async def test_all_exceptions_needs_human(self):
        mock_llm = AsyncMock(side_effect=ConnectionError("down"))

        result = await call_llm_with_retry(
            mock_llm, "test", ProcurementPageAction,
            max_retries=3, retry_delays=[0, 0, 0],
        )

        assert result.success is False
        assert result.needs_human is True
        assert "ConnectionError" in result.errors[0]

    async def test_error_output_does_not_echo_credentials(self):
        sensitive_marker = "sensitive-demo-value"
        mock_llm = AsyncMock(
            side_effect=RuntimeError(f"provider detail={sensitive_marker}")
        )

        with self.assertLogs("enterprise.llm.resilient_caller", level="WARNING") as logs:
            result = await call_llm_with_retry(
                mock_llm, "Extract the supplier quote", ProcurementPageAction,
                max_retries=1, retry_delays=[0],
            )

        output = "\n".join(result.errors + logs.output)
        assert sensitive_marker not in output
        assert "RuntimeError" in output

    async def test_validation_error_retried(self):
        responses = iter([
            '{"action": "open_quote"}',  # missing procurement fields
            '{"action": "open_quote", "target": "quote-link", "supplier_name": "Acme Industrial", "confidence": 0.9}',
        ])
        mock_llm = AsyncMock(side_effect=lambda p: next(responses))

        result = await call_llm_with_retry(
            mock_llm, "test", ProcurementPageAction,
            max_retries=3, retry_delays=[0, 0, 0],
        )

        assert result.success is True
        assert result.attempts == 2


# ============================================================
# Model Router tests
# ============================================================

class TestEstimateComplexity(unittest.TestCase):
    def test_simple_page(self):
        features = PageFeatures(element_count=50)
        assert estimate_complexity(features) == ComplexityLevel.SIMPLE

    def test_moderate_element_count(self):
        features = PageFeatures(element_count=200)
        assert estimate_complexity(features) == ComplexityLevel.MODERATE

    def test_complex_element_count(self):
        features = PageFeatures(element_count=600)
        assert estimate_complexity(features) == ComplexityLevel.COMPLEX

    def test_iframe_moderate(self):
        features = PageFeatures(has_iframe=True, iframe_depth=1, element_count=50)
        assert estimate_complexity(features) == ComplexityLevel.MODERATE

    def test_deep_iframe_complex(self):
        features = PageFeatures(has_iframe=True, iframe_depth=2, element_count=50)
        assert estimate_complexity(features) == ComplexityLevel.COMPLEX

    def test_shadow_dom_complex(self):
        features = PageFeatures(has_shadow_dom=True, element_count=50)
        assert estimate_complexity(features) == ComplexityLevel.COMPLEX

    def test_dynamic_content_moderate(self):
        features = PageFeatures(has_dynamic_content=True, element_count=50)
        assert estimate_complexity(features) == ComplexityLevel.MODERATE

    def test_many_form_fields_complex(self):
        features = PageFeatures(form_field_count=25, element_count=50)
        assert estimate_complexity(features) == ComplexityLevel.COMPLEX

    def test_minimal_page(self):
        features = PageFeatures()
        assert estimate_complexity(features) == ComplexityLevel.SIMPLE


class TestRouteModel(unittest.TestCase):
    def test_simple_routes_to_light(self):
        features = PageFeatures(element_count=30)
        decision = route_model(features)
        assert decision.model_tier == ModelTier.LIGHT
        assert decision.complexity == ComplexityLevel.SIMPLE

    def test_moderate_routes_to_standard(self):
        features = PageFeatures(element_count=200, has_dynamic_content=True)
        decision = route_model(features)
        assert decision.model_tier == ModelTier.STANDARD

    def test_complex_routes_to_heavy(self):
        features = PageFeatures(element_count=600, has_iframe=True, iframe_depth=3)
        decision = route_model(features)
        assert decision.model_tier == ModelTier.HEAVY

    def test_decision_has_reason(self):
        features = PageFeatures(element_count=200)
        decision = route_model(features)
        assert "elements=200" in decision.reason

    def test_decision_preserves_features(self):
        features = PageFeatures(element_count=100, has_shadow_dom=True)
        decision = route_model(features)
        assert decision.features is features


# ============================================================
# Human Intervention tests
# ============================================================

def _make_stuck_task(**overrides):
    defaults = {
        "task_id": "task_1",
        "org_id": "org_1",
        "department_id": "dept_a",
        "stuck_action_index": 2,
        "stuck_action_type": "extract_supplier_quote",
        "page_url": "https://supplier.example.test/quotes",
        "screenshot_key": "audit/org_1/task_1/2_after_abc.png",
        "llm_errors": ["Attempt 1: JSON error", "Attempt 2: timeout", "Attempt 3: timeout"],
        "llm_raw_response": '{"invalid": true}',
        "stuck_since": "2026-03-07T10:00:00",
        "total_actions": 5,
        "completed_actions": 2,
    }
    defaults.update(overrides)
    return StuckTaskInfo(**defaults)


class TestResolutionAction(unittest.TestCase):
    def test_skip_step(self):
        assert ResolutionAction.SKIP_STEP.value == "skip_step"

    def test_manual_complete(self):
        assert ResolutionAction.MANUAL_COMPLETE.value == "manual_complete"

    def test_terminate(self):
        assert ResolutionAction.TERMINATE.value == "terminate"


class TestResolveStuckTask(unittest.TestCase):
    def test_skip_step(self):
        task = _make_stuck_task()
        resolution = HumanResolution(
            task_id="task_1",
            action=ResolutionAction.SKIP_STEP,
            resolved_by="eu_1",
            note="Optional quote field, skip",
        )
        result = resolve_stuck_task(task, resolution)
        assert result["new_status"] == "running"
        assert result["resume_from_action"] == 3  # stuck at 2, resume from 3
        assert result["resolution"] == "skip_step"

    def test_manual_complete(self):
        task = _make_stuck_task()
        resolution = HumanResolution(
            task_id="task_1",
            action=ResolutionAction.MANUAL_COMPLETE,
            resolved_by="eu_1",
            manual_result={"quote_reference": "quote-demo-001"},
        )
        result = resolve_stuck_task(task, resolution)
        assert result["new_status"] == "running"
        assert result["resume_from_action"] == 3
        assert result["manual_result"] == {"quote_reference": "quote-demo-001"}

    def test_terminate(self):
        task = _make_stuck_task()
        resolution = HumanResolution(
            task_id="task_1",
            action=ResolutionAction.TERMINATE,
            resolved_by="eu_1",
            note="Supplier page unavailable",
        )
        result = resolve_stuck_task(task, resolution)
        assert result["new_status"] == "terminated"
        assert result["resolution"] == "terminate"

    def test_invalid_action_raises(self):
        task = _make_stuck_task()
        resolution = HumanResolution(
            task_id="task_1",
            action="invalid_action",
            resolved_by="eu_1",
        )
        with self.assertRaises(ValueError):
            resolve_stuck_task(task, resolution)


class TestHumanResolution(unittest.TestCase):
    def test_auto_timestamp(self):
        r = HumanResolution(
            task_id="t", action=ResolutionAction.SKIP_STEP, resolved_by="u"
        )
        assert r.resolved_at != ""
        assert "T" in r.resolved_at


class TestStuckTaskInfo(unittest.TestCase):
    def test_fields(self):
        task = _make_stuck_task()
        assert task.stuck_action_index == 2
        assert task.completed_actions == 2
        assert task.total_actions == 5
        assert len(task.llm_errors) == 3


if __name__ == "__main__":
    unittest.main()
