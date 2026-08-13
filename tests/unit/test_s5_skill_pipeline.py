"""S5 native Skill Pipeline compilation and execution checks."""

import json
from types import SimpleNamespace

import pytest

from enterprise.agent.skyvern_handler import SkyvernProcurementHandler
from enterprise.audit.models import AuditLogModel
from enterprise.auth.models import TaskExtensionModel
from enterprise.procurement.models import ProcurementHumanReviewModel
from enterprise.skills.executor import SkillStep, compile_skill_pipeline
from enterprise.workflows.templates import SUPPLIER_QUOTE_LEDGER, compile_template_pipeline
from skyvern.forge.sdk.artifact.models import ArtifactType
from skyvern.forge.sdk.schemas.tasks import TaskStatus

URL = "https://supplier.example/quotes"
PARAMETERS = {
    "supplier_portal_url": URL,
    "username": "buyer-demo",
    "password": "Secret123!",
    "supplier_code": "SUP-001",
    "material_code": "MAT-001",
    "start_date": "2026-01-01",
    "end_date": "2026-03-01",
}


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
    def __init__(self, extracted_information):
        self.rows = []
        self.task = SimpleNamespace(
            task_id="tsk_pipeline",
            status=TaskStatus.completed,
            url=URL,
            extracted_information=extracted_information,
        )
        self.artifact = SimpleNamespace(
            artifact_id="art_pipeline",
            artifact_type=ArtifactType.SCREENSHOT_FINAL,
            task_id=self.task.task_id,
            organization_id="org_a",
        )

    def Session(self):
        return Session(self)

    async def get_organization(self, organization_id):
        return SimpleNamespace(organization_id=organization_id)

    async def get_task(self, task_id, organization_id):
        if task_id == self.task.task_id and organization_id == "org_a":
            return self.task
        return None

    async def get_latest_artifact(self, **_kwargs):
        return self.artifact


def make_handler(database, calls):
    async def run_task(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(task_id=database.task.task_id)

    return SkyvernProcurementHandler(
        database=database,
        task_runner=run_task,
        organization_id="org_a",
        department_id="dept_a",
        category_id="cat_a",
        user_id="user_a",
        url=URL,
        allowed_urls={URL},
        compiled_pipeline=compile_template_pipeline(SUPPLIER_QUOTE_LEDGER, PARAMETERS),
    )


def valid_rows():
    return {
        "rows": [{
            "供应商编码": "SUP-001",
            "物料编码": "MAT-001",
            "含税单价": 12.34,
            "交期": "2026-03-10",
            "MOQ": 10,
        }],
    }


def test_compiler_emits_safe_native_fields_for_login_form_and_extract():
    compiled = compile_template_pipeline(SUPPLIER_QUOTE_LEDGER, PARAMETERS)
    serialized = json.dumps(compiled.model_dump(mode="json"), ensure_ascii=False)

    assert "Secret123" not in serialized
    assert "buyer-demo" not in serialized
    assert "https://" not in serialized
    assert compiled.data_extraction_goal
    assert compiled.extracted_information_schema["properties"]["rows"]["type"] == "array"
    assert compiled.requires_download is True
    request = compiled.to_task_request(title="Supplier quote", url=URL)
    assert request.url == URL
    assert request.navigation_payload["form_fields"]["供应商编码"] == "SUP-001"


def test_all_seven_registered_skills_compile_without_a_second_browser_runtime():
    compiled = compile_skill_pipeline([
        SkillStep(skill_name="login", params={"url": URL, "username": "buyer", "password": "secret"}),
        SkillStep(skill_name="form_fill", params={"field_mapping": {"物料": "MAT-001"}}),
        SkillStep(skill_name="table_extract", params={"headers": ["物料"]}),
        SkillStep(skill_name="file_download", params={"trigger_text": "下载"}),
        SkillStep(skill_name="search_and_select", params={"search_text": "MAT-001", "target_text": "MAT-001"}),
        SkillStep(skill_name="pagination", params={"max_pages": 2}),
        SkillStep(skill_name="session_keep_alive", params={}),
    ])

    assert "Keep the current Skyvern browser session" in compiled.navigation_goal
    assert "Traverse the requested result pages" in compiled.navigation_goal
    assert compiled.requires_download is True


@pytest.mark.asyncio
async def test_native_handler_runs_compiled_task_and_binds_structured_result_to_artifact():
    database, calls = Database(valid_rows()), []

    result = await make_handler(database, calls)("ignored", {})

    request = calls[0]["task"]
    assert request.data_extraction_goal
    assert request.extracted_information_schema
    assert calls[0]["defer_execution"] is False
    assert result["success"] is True
    assert result["artifact_id"] == "art_pipeline"
    assert result["data"]["extracted_information"] == valid_rows()
    assert any(isinstance(row, TaskExtensionModel) for row in database.rows)
    assert any(isinstance(row, AuditLogModel) for row in database.rows)


@pytest.mark.asyncio
async def test_invalid_table_result_fails_closed_into_human_review():
    database, calls = Database({"rows": [{"供应商编码": "SUP-001"}]}), []

    result = await make_handler(database, calls)("ignored", {})

    assert result["success"] is False
    assert result["error"] == "skill_table_schema_invalid"
    assert any(
        isinstance(row, ProcurementHumanReviewModel)
        and row.reason_code == "skill_table_schema_invalid"
        and row.artifact_id == "art_pipeline"
        for row in database.rows
    )
