"""S3 native Skyvern Executor tracer-bullet checks."""

from types import SimpleNamespace

import pytest

from enterprise.agent.executor import ExecutorAgent
from enterprise.agent.schemas import SubTask
from enterprise.agent.skyvern_handler import TRACER_GOAL, SkyvernProcurementHandler
from enterprise.audit.models import AuditLogModel
from enterprise.auth.models import TaskExtensionModel
from enterprise.procurement.models import ProcurementHumanReviewModel
from skyvern.forge.sdk.artifact.models import ArtifactType
from skyvern.forge.sdk.schemas.tasks import TaskStatus

URL = "https://supplier.example/quote"


class Session:
    def __init__(self, database):
        self.database = database

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def add(self, row):
        self.database.rows.append(row)

    async def commit(self):
        return None


class Database:
    def __init__(self, status=TaskStatus.completed, artifact_org="org_a", with_artifact=True):
        self.rows = []
        self.task = SimpleNamespace(task_id="tsk_native", status=status, url=URL)
        self.artifact = SimpleNamespace(
            artifact_id="art_native",
            artifact_type=ArtifactType.SCREENSHOT_FINAL,
            task_id="tsk_native",
            organization_id=artifact_org,
        ) if with_artifact else None

    def Session(self):
        return Session(self)

    async def get_organization(self, organization_id):
        return SimpleNamespace(organization_id=organization_id)

    async def get_task(self, task_id, organization_id):
        return self.task if task_id == "tsk_native" and organization_id == "org_a" else None

    async def get_latest_artifact(self, **_kwargs):
        return self.artifact


def make_handler(database, calls):
    async def run_task(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(task_id="tsk_native")

    return SkyvernProcurementHandler(
        database=database,
        task_runner=run_task,
        organization_id="org_a",
        department_id="dept_a",
        category_id="cat_a",
        user_id="user_a",
        url=URL,
        allowed_urls={URL},
    )


@pytest.mark.asyncio
async def test_completed_task_returns_real_ids_and_persists_context_and_audit():
    database, calls = Database(), []
    result = await ExecutorAgent(make_handler(database, calls)).execute_subtask(
        SubTask(index=0, goal="Inspect password=secret quote", completion_condition="Evidence exists"),
        {"execution_mode": "real"},
    )

    request = calls[0]["task"]
    assert request.url == URL
    assert request.navigation_goal == TRACER_GOAL
    assert calls[0]["defer_execution"] is False
    assert calls[0]["organization"].organization_id == "org_a"
    assert result.model_dump(include={"success", "simulated", "skyvern_task_id", "status", "artifact_id", "page_url"}) == {
        "success": True,
        "simulated": False,
        "skyvern_task_id": "tsk_native",
        "status": "completed",
        "artifact_id": "art_native",
        "page_url": URL,
    }
    assert any(isinstance(row, TaskExtensionModel) for row in database.rows)
    assert any(isinstance(row, AuditLogModel) and row.execution_result == "success" for row in database.rows)


@pytest.mark.asyncio
@pytest.mark.parametrize("status, code", [
    (TaskStatus.failed, "skyvern_task_failed"),
    (TaskStatus.timed_out, "skyvern_task_timed_out"),
])
async def test_failed_or_timed_out_task_creates_review(status, code):
    database = Database(status=status)
    result = await ExecutorAgent(make_handler(database, [])).execute_subtask(
        SubTask(index=0, goal="Inspect quote", completion_condition="Evidence exists", max_retries=0),
        {"execution_mode": "real"},
    )

    assert result.success is False
    assert result.error_message == code
    assert result.skyvern_task_id == "tsk_native"
    assert any(isinstance(row, ProcurementHumanReviewModel) and row.reason_code == code for row in database.rows)


@pytest.mark.asyncio
@pytest.mark.parametrize("with_artifact, artifact_org", [(False, "org_a"), (True, "org_b")])
async def test_missing_or_cross_org_artifact_is_rejected(with_artifact, artifact_org):
    database = Database(with_artifact=with_artifact, artifact_org=artifact_org)
    result = await ExecutorAgent(make_handler(database, [])).execute_subtask(
        SubTask(index=0, goal="Inspect quote", completion_condition="Evidence exists", max_retries=0),
        {"execution_mode": "real"},
    )

    assert result.success is False
    assert result.error_message == "skyvern_artifact_missing"
    assert any(isinstance(row, ProcurementHumanReviewModel) for row in database.rows)


@pytest.mark.asyncio
async def test_non_allowlisted_url_never_calls_skyvern():
    database, calls = Database(), []
    handler = make_handler(database, calls)
    handler.url = "https://evil.example/"

    result = await ExecutorAgent(handler).execute_subtask(
        SubTask(index=0, goal="Inspect quote", completion_condition="Evidence exists", max_retries=0),
        {"execution_mode": "real"},
    )

    assert result.success is False
    assert result.error_message == "supplier_url_not_allowlisted"
    assert calls == []
