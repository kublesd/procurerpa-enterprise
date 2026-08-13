"""Workflow template API routes.

Provides endpoints for:
- GET  /enterprise/workflows/templates         — list all templates
- GET  /enterprise/workflows/templates/{id}    — template detail
- POST /enterprise/workflows/instantiate/{id}  — create task from template
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from enterprise.agent.schemas import SubTask, TaskPlan
from enterprise.audit.logger import record_audit_event
from enterprise.auth.dependencies import CurrentUser, require_any_operator
from enterprise.auth.models import DepartmentModel, TaskExtensionModel
from enterprise.auth.schemas import UserContext
from enterprise.llm.model_router import ModelRoutingUnavailable, ProcurementPageKind, resolve_procurement_page
from enterprise.procurement.models import (
    ProcurementCategoryModel,
    ProcurementCoordinationStateModel,
)
from skyvern.config import settings
from skyvern.forge import app as forge_app
from skyvern.forge.sdk.schemas.tasks import TaskStatus
from skyvern.services import task_v1_service

from .crypto import mask_value
from .schemas import ParamType
from .templates import TEMPLATE_REGISTRY, compile_template_pipeline, get_template, get_templates_by_industry
from .validator import validate_parameters

router = APIRouter(prefix="/enterprise/workflows", tags=["workflows"])


# --- Pydantic response schemas ---

class ParamDefResponse(BaseModel):
    name: str
    label: str
    param_type: str
    required: bool
    sensitive: bool
    description: str
    default: str | None


class TemplateListItem(BaseModel):
    template_id: str
    name: str
    industry: str
    risk_level: str
    description: str
    tags: list[str]


class TemplateDetailResponse(BaseModel):
    template_id: str
    name: str
    industry: str
    risk_level: str
    description: str
    navigation_target: str
    expected_result: str
    approval_rule: str
    parameters: list[ParamDefResponse]
    tags: list[str]


class InstantiateRequest(BaseModel):
    department_id: str = Field(..., min_length=1, max_length=128)
    category_id: str = Field(..., min_length=1, max_length=128)
    parameters: dict[str, str] = Field(..., description="Parameter values")


class InstantiateResponse(BaseModel):
    task_id: str
    template_id: str
    template_name: str
    stored_parameters: dict[str, str]  # compatibility display only; sensitive values masked
    validation_passed: bool
    task_status: str
    sensitive_parameters_connected: bool
    message: str
    execution_mode: str = "real"
    model_tier: str
    model_alias: str
    routing_reason_code: str


# --- Routes ---

@router.get("/templates", response_model=list[TemplateListItem])
async def list_templates(
    user: CurrentUser,
    industry: str | None = None,
):
    """List all available workflow templates, optionally filtered by industry."""
    if industry:
        templates = get_templates_by_industry(industry)
    else:
        templates = list(TEMPLATE_REGISTRY.values())

    return [
        TemplateListItem(
            template_id=t.template_id,
            name=t.name,
            industry=t.industry.value,
            risk_level=t.risk_level,
            description=t.description,
            tags=t.tags,
        )
        for t in templates
    ]


@router.get("/templates/{template_id}", response_model=TemplateDetailResponse)
async def get_template_detail(
    template_id: str,
    user: CurrentUser,
):
    """Get detailed information about a specific workflow template."""
    template = get_template(template_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template {template_id} not found",
        )

    return TemplateDetailResponse(
        template_id=template.template_id,
        name=template.name,
        industry=template.industry.value,
        risk_level=template.risk_level,
        description=template.description,
        navigation_target=template.navigation_target,
        expected_result=template.expected_result,
        approval_rule=template.approval_rule,
        parameters=[
            ParamDefResponse(
                name=p.name,
                label=p.label,
                param_type=p.param_type.value,
                required=p.required,
                sensitive=p.sensitive,
                description=p.description,
                default=p.default,
            )
            for p in template.parameters
        ],
        tags=template.tags,
    )


@router.post("/instantiate/{template_id}", response_model=InstantiateResponse)
async def instantiate_template(
    template_id: str,
    body: InstantiateRequest,
    request: Request,
    user: UserContext = Depends(require_any_operator),
):
    """Create a deferred native Skyvern task from a procurement template."""
    template = get_template(template_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template {template_id} not found",
        )

    # Validate parameters
    result = validate_parameters(template.parameters, body.parameters)
    if not result.valid:
        error_details = "; ".join(f"{e.param_name}: {e.message}" for e in result.errors)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Parameter validation failed: {error_details}",
        )

    sensitive_names = {p.name for p in template.parameters if p.sensitive}
    display = {}

    for key, value in body.parameters.items():
        if key in sensitive_names:
            display[key] = mask_value(value)
        else:
            display[key] = value

    # Fill defaults for missing optional parameters
    for pdef in template.parameters:
        if pdef.name not in body.parameters and pdef.default is not None:
            display[pdef.name] = pdef.default

    url_names = [p.name for p in template.parameters if p.param_type == ParamType.URL]
    task_url = display[url_names[0]] if len(url_names) == 1 else None
    allowed_urls = {
        url.strip()
        for url in settings.PROCUREMENT_SMOKE_ALLOWED_URLS.split(",")
        if url.strip()
    }
    if task_url not in allowed_urls:
        raise HTTPException(status_code=400, detail="Template URL is not allowlisted")

    async with forge_app.DATABASE.Session() as session:
        department = await session.scalar(select(DepartmentModel.department_id).where(
            DepartmentModel.department_id == body.department_id,
            DepartmentModel.organization_id == user.org_id,
        ))
        category = await session.scalar(select(ProcurementCategoryModel.category_id).where(
            ProcurementCategoryModel.category_id == body.category_id,
            ProcurementCategoryModel.organization_id == user.org_id,
        ))
    if department is None or category is None:
        raise HTTPException(
            status_code=422,
            detail="Workflow department or category is outside the organization",
        )
    if not user.is_org_admin and (
        body.department_id not in user.department_ids or body.category_id not in user.procurement_category_ids
    ):
        raise HTTPException(status_code=403, detail="Workflow context is outside the authenticated scope")

    organization = await forge_app.DATABASE.get_organization(user.org_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization was not found")
    try:
        compiled_pipeline = compile_template_pipeline(template, body.parameters)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Workflow Skill Pipeline could not be compiled") from exc
    navigation_goal = compiled_pipeline.navigation_goal
    page_kind = (
        ProcurementPageKind.ERP_CONTRACT
        if compiled_pipeline.navigation_payload.get("form_fields") or compiled_pipeline.requires_download
        else ProcurementPageKind.DYNAMIC_QUOTE_PORTAL
        if compiled_pipeline.extracted_information_schema
        else ProcurementPageKind.SUPPLIER_CATALOG
    )
    try:
        routing = resolve_procurement_page(page_kind)
    except ModelRoutingUnavailable as exc:
        raise HTTPException(status_code=503, detail="Procurement model routing is unavailable") from exc
    plan = TaskPlan(
        navigation_goal=navigation_goal,
        subtasks=[
            SubTask(index=index, goal=step.description, completion_condition="Native Skyvern evidence is recorded")
            for index, step in enumerate(template.skill_steps)
        ],
    )
    task = None
    try:
        task = await task_v1_service.run_task(
            task=compiled_pipeline.to_task_request(
                title=template.name,
                url=task_url,
                model=routing.to_task_model(),
            ),
            organization=organization,
            request=request,
            defer_execution=True,
        )
        async with forge_app.DATABASE.Session() as session:
            session.add_all([
                TaskExtensionModel(
                    task_id=task.task_id,
                    organization_id=user.org_id,
                    department_id=body.department_id,
                    category_id=body.category_id,
                    risk_level=template.risk_level,
                    risk_reason="Static procurement workflow template risk",
                    risk_result={"risk_level": template.risk_level, "source": "workflow_template"},
                    created_by=user.user_id,
                ),
                ProcurementCoordinationStateModel(
                    task_id=task.task_id,
                    organization_id=user.org_id,
                    navigation_goal=navigation_goal,
                    current_plan=plan.model_dump(mode="json"),
                    completed_subtask_ids=[],
                    status="running",
                ),
            ])
            await session.commit()
        persisted_task = await forge_app.DATABASE.get_task(task.task_id, organization_id=user.org_id)
        if persisted_task is None:
            raise RuntimeError("native task was not queryable")
        await record_audit_event(
            task_id=task.task_id,
            org_id=user.org_id,
            department_id=body.department_id,
            action_index=0,
            action_type="model_route",
            executor=user.user_id,
            business_object_type="skyvern_task",
            business_object_id=task.task_id,
            input_value={
                "model_tier": routing.model_tier.value,
                "resolved_model_key": routing.resolved_model_key,
                "reason_code": routing.reason_code,
                "step_id": None,
            },
            page_url=task_url,
        )
    except HTTPException:
        raise
    except Exception as exc:
        if task is not None:
            try:
                await forge_app.DATABASE.update_task(
                    task_id=task.task_id,
                    organization_id=user.org_id,
                    status=TaskStatus.canceled,
                )
            except Exception:
                pass
        raise HTTPException(status_code=503, detail="Workflow task could not be created") from exc

    return InstantiateResponse(
        task_id=task.task_id,
        template_id=template_id,
        template_name=template.name,
        stored_parameters=display,
        validation_passed=True,
        task_status=task.status.value,
        sensitive_parameters_connected=False,
        message=f"Deferred Skyvern task created from procurement template '{template.name}'",
        execution_mode="real",
        model_tier=routing.model_tier.value,
        model_alias=routing.model_alias or "procurement-model",
        routing_reason_code=routing.reason_code or "tier_selected",
    )
