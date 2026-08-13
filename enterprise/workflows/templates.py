"""Built-in procurement workflow templates.

The six first-stage templates cover direct materials, MRO, and services
procurement. They create intermediate Skill steps; production requests compile
them into native Skyvern task fields.
"""

import json
import re

from enterprise.skills.executor import CompiledSkillPipeline, SkillStep, compile_skill_pipeline

from .schemas import (
    IndustryType,
    ParamDefinition,
    ParamType,
    SkillStepDefinition,
    WorkflowTemplate,
)
from .validator import validate_parameters

_PLACEHOLDER_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _resolve_mapping(source: str, values: dict[str, str]) -> object:
    """Resolve a workflow parameter, literal, or JSON mapping."""
    value: object = source[1:] if source.startswith("=") else values.get(source, source)
    if not isinstance(value, str):
        return value

    value = _PLACEHOLDER_PATTERN.sub(
        lambda match: str(values.get(match.group(1), match.group(0))),
        value,
    )
    if value.startswith(("{", "[")):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
    return value


def build_skill_pipeline(
    template: WorkflowTemplate,
    parameters: dict[str, str],
) -> list[SkillStep]:
    """Convert a validated template into intermediate Skill steps."""
    values = {
        p.name: p.default
        for p in template.parameters
        if p.default is not None
    }
    values.update(parameters)

    validation = validate_parameters(template.parameters, values)
    if not validation.valid:
        details = "; ".join(f"{e.param_name}: {e.message}" for e in validation.errors)
        raise ValueError(f"Template parameter validation failed: {details}")

    return [
        SkillStep(
            skill_name=definition.skill_name,
            description=definition.description,
            params={
                name: _resolve_mapping(mapping, values)
                for name, mapping in definition.param_mapping.items()
            },
            error_strategy_override=definition.error_strategy_override,
        )
        for definition in template.skill_steps
    ]


def compile_template_pipeline(
    template: WorkflowTemplate,
    parameters: dict[str, str],
) -> CompiledSkillPipeline:
    """Compile a validated template into native Skyvern task fields."""
    return compile_skill_pipeline(build_skill_pipeline(template, parameters))


# ============================================================
# Direct materials procurement templates
# ============================================================

SUPPLIER_QUOTE_LEDGER = WorkflowTemplate(
    template_id="tpl_supplier_quote_ledger",
    name="供应商历史报价台账采集",
    industry=IndustryType.DIRECT_MATERIALS,
    risk_level="medium",
    description=(
        "登录受控供应商门户，按供应商、物料和日期范围采集历史报价台账，"
        "并下载报价附件供采购比价复核。"
    ),
    navigation_target="供应商门户 - 报价管理 - 历史报价",
    expected_result="报价台账 JSON/CSV 与报价附件下载到演示目录",
    approval_rule="medium 风险，仅记录采集事实，不提交采购订单",
    parameters=[
        ParamDefinition(
            name="supplier_portal_url", label="供应商门户地址", param_type=ParamType.URL,
            description="受控供应商门户登录地址",
        ),
        ParamDefinition(name="username", label="门户用户名", param_type=ParamType.STRING),
        ParamDefinition(
            name="password", label="门户密码", param_type=ParamType.PASSWORD,
            sensitive=True,
        ),
        ParamDefinition(name="supplier_code", label="供应商编码", param_type=ParamType.STRING),
        ParamDefinition(name="material_code", label="物料编码", param_type=ParamType.STRING),
        ParamDefinition(name="start_date", label="开始日期", param_type=ParamType.DATE),
        ParamDefinition(name="end_date", label="结束日期", param_type=ParamType.DATE),
        ParamDefinition(
            name="download_path", label="报价附件目录", param_type=ParamType.STRING,
            required=False, default="./downloads/quotes/",
        ),
    ],
    tags=["供应商报价", "直接物料", "台账采集"],
    skill_steps=[
        SkillStepDefinition(
            skill_name="login", description="登录供应商门户",
            param_mapping={"url": "supplier_portal_url", "username": "username", "password": "password"},
        ),
        SkillStepDefinition(
            skill_name="form_fill", description="填写历史报价查询条件",
            param_mapping={
                "field_mapping": (
                    '={"供应商编码": "${supplier_code}", "物料编码": "${material_code}", '
                    '"开始日期": "${start_date}", "结束日期": "${end_date}"}'
                ),
            },
        ),
        SkillStepDefinition(
            skill_name="table_extract", description="提取报价、交期和 MOQ",
            param_mapping={
                "headers": '=["供应商编码", "物料编码", "含税单价", "交期", "MOQ"]',
                "output_format": "=csv",
            },
        ),
        SkillStepDefinition(
            skill_name="file_download", description="下载报价附件",
            param_mapping={"download_path": "download_path", "trigger_text": "=导出报价"},
        ),
    ],
)


MATERIAL_BENCHMARK_COLLECTION = WorkflowTemplate(
    template_id="tpl_material_benchmark",
    name="物料历史基准价采集",
    industry=IndustryType.DIRECT_MATERIALS,
    risk_level="low",
    description=(
        "按物料编码和日期范围采集受控采购平台中的历史市场价，"
        "形成可复核的采购基准价数据。"
    ),
    navigation_target="采购平台 - 物料价格 - 历史基准价",
    expected_result="物料历史基准价 CSV，包含物料、供应商、价格和日期",
    approval_rule="low 风险，无需审批",
    parameters=[
        ParamDefinition(name="pricing_portal_url", label="价格平台地址", param_type=ParamType.URL),
        ParamDefinition(name="username", label="门户用户名", param_type=ParamType.STRING),
        ParamDefinition(
            name="password", label="门户密码", param_type=ParamType.PASSWORD,
            sensitive=True,
        ),
        ParamDefinition(
            name="material_codes", label="物料编码列表", param_type=ParamType.STRING,
            description="多个物料编码以逗号分隔",
        ),
        ParamDefinition(name="start_date", label="开始日期", param_type=ParamType.DATE),
        ParamDefinition(name="end_date", label="结束日期", param_type=ParamType.DATE),
        ParamDefinition(
            name="output_path", label="输出目录", param_type=ParamType.STRING,
            required=False, default="./downloads/benchmarks/",
        ),
    ],
    tags=["基准价", "直接物料", "价格采集"],
    skill_steps=[
        SkillStepDefinition(
            skill_name="login", description="登录采购价格平台",
            param_mapping={"url": "pricing_portal_url", "username": "username", "password": "password"},
        ),
        SkillStepDefinition(
            skill_name="form_fill", description="填写物料和日期条件",
            param_mapping={
                "field_mapping": (
                    '={"物料编码": "${material_codes}", "开始日期": "${start_date}", '
                    '"结束日期": "${end_date}"}'
                ),
            },
        ),
        SkillStepDefinition(
            skill_name="table_extract", description="提取历史基准价",
            param_mapping={
                "headers": '=["物料编码", "供应商", "含税单价", "报价日期"]',
                "output_format": "=csv",
            },
        ),
    ],
)


# ============================================================
# MRO procurement templates
# ============================================================

PURCHASE_ORDER_DUE = WorkflowTemplate(
    template_id="tpl_purchase_order_due",
    name="采购订单到期与催交清单",
    industry=IndustryType.MRO,
    risk_level="low",
    description=(
        "批量查询即将到期的采购订单和交付状态，提取逾期或临近交期的订单，"
        "生成采购催交清单。"
    ),
    navigation_target="采购平台 - 订单管理 - 交付跟踪",
    expected_result="采购订单交付到期与催交清单（JSON）",
    approval_rule="low 风险，无需审批",
    parameters=[
        ParamDefinition(name="purchase_portal_url", label="采购平台地址", param_type=ParamType.URL),
        ParamDefinition(name="username", label="门户用户名", param_type=ParamType.STRING),
        ParamDefinition(
            name="password", label="门户密码", param_type=ParamType.PASSWORD,
            sensitive=True,
        ),
        ParamDefinition(
            name="days_ahead", label="提前天数", param_type=ParamType.INTEGER,
            default="7", description="查询未来 N 天内到期的订单",
        ),
        ParamDefinition(
            name="department", label="采购部门", param_type=ParamType.STRING,
            required=False, default="",
        ),
    ],
    tags=["订单跟踪", "MRO", "催交"],
    skill_steps=[
        SkillStepDefinition(
            skill_name="login", description="登录采购平台",
            param_mapping={"url": "purchase_portal_url", "username": "username", "password": "password"},
        ),
        SkillStepDefinition(
            skill_name="form_fill", description="填写交付跟踪条件",
            param_mapping={
                "field_mapping": '={"提前天数": "${days_ahead}", "采购部门": "${department}"}',
            },
        ),
        SkillStepDefinition(
            skill_name="table_extract", description="提取订单交期与状态",
            param_mapping={"output_format": "=json"},
        ),
    ],
)


SUPPLIER_ATTACHMENT_ARCHIVE = WorkflowTemplate(
    template_id="tpl_supplier_attachment_archive",
    name="供应商资质与报价附件批量归档",
    industry=IndustryType.MRO,
    risk_level="medium",
    description=(
        "检索供应商资质、报价单和合规附件，遍历结果页面并下载到受控演示目录，"
        "供采购审查复核。"
    ),
    navigation_target="供应商门户 - 供应商中心 - 资质与报价附件",
    expected_result="供应商资质和报价附件按供应商关键词批量下载",
    approval_rule="medium 风险，仅下载和归档，不改变供应商主数据",
    parameters=[
        ParamDefinition(name="supplier_portal_url", label="供应商门户地址", param_type=ParamType.URL),
        ParamDefinition(name="username", label="门户用户名", param_type=ParamType.STRING),
        ParamDefinition(
            name="password", label="门户密码", param_type=ParamType.PASSWORD,
            sensitive=True,
        ),
        ParamDefinition(name="supplier_keyword", label="供应商关键词", param_type=ParamType.STRING),
        ParamDefinition(
            name="archive_path", label="归档目录", param_type=ParamType.STRING,
            required=False, default="./downloads/supplier-attachments/",
        ),
    ],
    tags=["供应商资质", "MRO", "附件归档"],
    skill_steps=[
        SkillStepDefinition(
            skill_name="login", description="登录供应商门户",
            param_mapping={"url": "supplier_portal_url", "username": "username", "password": "password"},
        ),
        SkillStepDefinition(
            skill_name="search_and_select", description="检索供应商附件",
            param_mapping={"search_text": "supplier_keyword", "target_text": "supplier_keyword"},
        ),
        SkillStepDefinition(
            skill_name="pagination", description="遍历资质和报价附件列表",
            param_mapping={"max_pages": "=20"},
        ),
        SkillStepDefinition(
            skill_name="file_download", description="下载附件并归档",
            param_mapping={"download_path": "archive_path", "trigger_text": "=下载附件"},
        ),
    ],
)


# ============================================================
# Services procurement templates
# ============================================================

RFQ_STATUS_QUERY = WorkflowTemplate(
    template_id="tpl_rfq_status",
    name="询价单与采购任务批量状态查询",
    industry=IndustryType.SERVICES,
    risk_level="low",
    description=(
        "批量检索询价单或采购任务，提取待报价、比价中、审批中和已完成状态，"
        "生成采购运营状态清单。"
    ),
    navigation_target="采购平台 - 询价管理 - 询价单查询",
    expected_result="询价单/采购任务状态汇总表（JSON）",
    approval_rule="low 风险，无需审批",
    parameters=[
        ParamDefinition(name="procurement_portal_url", label="采购平台地址", param_type=ParamType.URL),
        ParamDefinition(name="username", label="门户用户名", param_type=ParamType.STRING),
        ParamDefinition(
            name="password", label="门户密码", param_type=ParamType.PASSWORD,
            sensitive=True,
        ),
        ParamDefinition(
            name="request_ids", label="询价单/任务编号", param_type=ParamType.STRING,
            description="多个编号以逗号分隔",
        ),
        ParamDefinition(
            name="status_filter", label="状态筛选", param_type=ParamType.STRING,
            required=False, default="",
        ),
    ],
    tags=["询价状态", "服务采购", "运营查询"],
    skill_steps=[
        SkillStepDefinition(
            skill_name="login", description="登录采购平台",
            param_mapping={"url": "procurement_portal_url", "username": "username", "password": "password"},
        ),
        SkillStepDefinition(
            skill_name="search_and_select", description="检索询价单或采购任务",
            param_mapping={"search_text": "request_ids", "target_text": "request_ids"},
        ),
        SkillStepDefinition(
            skill_name="table_extract", description="提取任务状态",
            param_mapping={"output_format": "=json"},
        ),
    ],
)


SUPPLIER_CONTRACT_RENEWAL = WorkflowTemplate(
    template_id="tpl_supplier_contract_renewal",
    name="供应商合同到期与续签核查",
    industry=IndustryType.SERVICES,
    risk_level="medium",
    description=(
        "查询即将到期的供应商合同和服务协议，提取合同状态与到期日期，"
        "生成续签核查清单。"
    ),
    navigation_target="合同管理平台 - 供应商合同 - 到期核查",
    expected_result="供应商合同到期与续签核查清单（JSON）",
    approval_rule="medium 风险，仅生成核查清单，不自动续签合同",
    parameters=[
        ParamDefinition(name="contract_portal_url", label="合同平台地址", param_type=ParamType.URL),
        ParamDefinition(name="username", label="门户用户名", param_type=ParamType.STRING),
        ParamDefinition(
            name="password", label="门户密码", param_type=ParamType.PASSWORD,
            sensitive=True,
        ),
        ParamDefinition(
            name="days_ahead", label="到期天数", param_type=ParamType.INTEGER,
            default="90", description="查询未来 N 天内到期的合同",
        ),
        ParamDefinition(
            name="supplier_code", label="供应商编码", param_type=ParamType.STRING,
            required=False, default="",
        ),
    ],
    tags=["合同核查", "服务采购", "续签"],
    skill_steps=[
        SkillStepDefinition(
            skill_name="login", description="登录合同管理平台",
            param_mapping={"url": "contract_portal_url", "username": "username", "password": "password"},
        ),
        SkillStepDefinition(
            skill_name="form_fill", description="填写合同到期条件",
            param_mapping={
                "field_mapping": '={"到期天数": "${days_ahead}", "供应商编码": "${supplier_code}"}',
            },
        ),
        SkillStepDefinition(
            skill_name="table_extract", description="提取合同状态与到期日",
            param_mapping={"output_format": "=json"},
        ),
    ],
)


# Template registry
TEMPLATE_REGISTRY: dict[str, WorkflowTemplate] = {
    template.template_id: template
    for template in [
        SUPPLIER_QUOTE_LEDGER,
        PURCHASE_ORDER_DUE,
        RFQ_STATUS_QUERY,
        SUPPLIER_CONTRACT_RENEWAL,
        SUPPLIER_ATTACHMENT_ARCHIVE,
        MATERIAL_BENCHMARK_COLLECTION,
    ]
}


def get_templates_by_industry(industry: str) -> list[WorkflowTemplate]:
    """Filter templates by procurement scenario category."""
    return [template for template in TEMPLATE_REGISTRY.values() if template.industry.value == industry]


def get_template(template_id: str) -> WorkflowTemplate | None:
    """Get a procurement template by ID."""
    return TEMPLATE_REGISTRY.get(template_id)
