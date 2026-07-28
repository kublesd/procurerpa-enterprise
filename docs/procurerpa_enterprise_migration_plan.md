# ProcureRPA Enterprise：基于 Skyvern 的企业级采购与供应商管理 RPA 改造方案

> 文档性质：仓库实证分析、迁移设计与 16 阶段开发路线  
> 分析基线：当前主分支，以及 `origin/day-1/project-setup` 至 `origin/day-16/demo-data-integration`  
> 目标定位：完成度与 FinRPA Enterprise 相近、可运行、可演示、适合求职展示的企业级原型  
> 标记约定：**[本轮实现]**、**[演示级]**、**[仅设计说明]**、**[生产升级]**

## 0. 执行摘要

结论先行：该仓库适合作为 ProcureRPA Enterprise 的技术底座，但采购版不应建设一个完整 SRM/采购中台。Skyvern 核心的浏览器任务、步骤、工作流、动作、制品和浏览器会话是真实实现；`enterprise/` 中的大量能力则是与核心并列的企业原型，风险、审批、审计、通知、Agent、Skill、Action Cache 尚未进入真实执行主链。采购版应参考这种完成度：保留企业架构意识，真正实现少量关键能力和三条演示主流程，不把未来设计全部落成代码。

最小且正确的迁移路线是：

1. 保留模块化单体，不拆微服务，不引入 Kafka、规则平台或复杂权限平台。
2. 复用 Skyvern 原生 `Task`、`Step`、`Workflow`、`Action`、`Artifact` 和 `Credential`，不实现第二套执行器。
3. 实际权限只做到组织、部门、采购品类和角色；采购项目作为业务字段，不作为首版安全维度。
4. 实际实现 5 个角色、5 类风险、约 7 张新增/改造表、7 个 Skill 和 18 个核心 API。
5. 保留 6 个工作流模板名称，只要求 3 条核心流程可演示；其他模板属于设计说明。
6. 第一条优先跑通“供应商报价采集 → 标准化 → 比价”，再接采购申请审批和订单跟踪。

预计整体代码复用率约为 **50%～60%**：通过沿用现有模型、路由和演示级实现，避免新增规则版本、审批阶段、通知 Outbox、权限授权平台等非必要模块。

### 0.1 本轮实现边界

| 层级 | 含义 | 示例 |
| --- | --- | --- |
| **[本轮实现]** | 必须有代码、测试或演示调用链 | 报价标准化、简单风险、单级审批、三条核心流程 |
| **[演示级]** | 可使用模拟站点、固定阈值、内存数据或单机部署 | 通知、Dashboard、订单跟踪调度 |
| **[仅设计说明]** | 文档中体现扩展意识，但不要求建表、API 或页面 | 财务/合规独立角色、多级审批、完整规则目录 |
| **[生产升级]** | 不纳入 16 阶段原型验收 | SSO、RLS、Outbox、WORM、HA、规则发布平台 |

原型不能简化掉的安全底线只有：组织隔离、发起人与审批人分离、金额使用 Decimal、提交幂等、敏感信息不进入 LLM、关键动作留审计。除此之外，优先复用现有实现。

---

## 1. 分析范围与证据方法

### 1.1 已检查内容

- 主分支目录、`README.md`、部署文件、`enterprise/`、`skyvern/`、`skyvern-frontend/`、`alembic/`、`tests/`。
- 16 个远端阶段分支：

| Day | Git 分支 | 关键实现提交 |
| --- | --- | --- |
| 1 | `origin/day-1/project-setup` | `c3d8e38` |
| 2 | `origin/day-2/permission-data-model` | `515d1fe` |
| 3 | `origin/day-3/auth-and-permission` | `2ad2207` |
| 4 | `origin/day-4/tenant-isolation-middleware` | `72ee56a` |
| 5 | `origin/day-5/financial-risk-detector` | `895df43` |
| 6 | `origin/day-6/approval-engine` | `4bac4e8` |
| 7 | `origin/day-7/notification` | `f5e4e99` |
| 8 | `origin/day-8/audit-compliance` | `72d5d8c` |
| 9 | `origin/day-9/llm-resilience` | `8ce2c5e`、补充 `915e1e3` |
| 10 | `origin/day-10/financial-workflow-templates` | `561a094`、补充 `15046d8` |
| 11 | `origin/day-11/dashboard-api` | `878bc23` |
| 12 | `origin/day-12/ui-redesign` | `c8f1487` |
| 13 | `origin/day-13/performance-optimization` | `dd7875b` |
| 14 | `origin/day-14/production-ready` | `2f25993` |
| 15 | `origin/day-15/enterprise-frontend-integration` | `59a9926` |
| 16 | `origin/day-16/demo-data-integration` | `61e97a5` |

- 每个分支中的 `summaries/day_N_summary.md` 与 `summaries/day_N_code_list.md`。这些日志位于对应分支，当前主分支并未保留完整 `summaries/` 目录。
- FastAPI 路由注册、Skyvern 原生任务/工作流执行链、企业 JWT 桥接、数据库模型、Pydantic 模型、迁移、测试和前后端接口对应。

### 1.2 可信度规则

- “已实现”：能找到入口、调用方、持久化或执行路径，以及相应测试。
- “独立原型”：代码存在且单元测试覆盖，但没有进入运行时主调用链。
- “演示数据”：由内存 store、固定随机种子或前端 fallback 提供。
- “需要进一步验证”：静态代码不足以确认，且当前环境无法运行依赖或外部服务。

本次没有修改业务代码。测试环境缺少 `pytest`，执行 `python -m pytest` 得到 `No module named pytest`，因此 README 中“601 tests passing / 85% coverage”只能视为历史声明：静态计数确有 561 个单元测试方法和 `tests/integration/test_e2e_flow.py` 中 40 个测试，共 601 个，但本次不能复现通过率和覆盖率。

---

## 2. 原项目整体架构分析

### 2.1 Skyvern 核心层

核心代码位于 `skyvern/`。真实任务入口是 `skyvern/forge/sdk/routes/agent_protocol.py` 的 `run_task()`，主链如下：

```text
POST /v1/run/tasks
→ agent_protocol.run_task()
→ skyvern/services/task_v1_service.py:run_task()
→ app.agent.create_task()
→ app.DATABASE.create_task_run()
→ AsyncExecutorFactory.get_executor().execute_task()
→ BackgroundTaskExecutor.execute_task()
→ ForgeAgent.execute_step()
→ ForgeAgent.agent_step()
→ 页面抓取 / 构造提示 / LLMAPIHandlerFactory
→ parse_actions()
→ ActionHandler.handle_action()
→ 记录 Action、Artifact、Step，并继续执行
```

工作流入口是 `POST /v1/run/workflows`，由 `workflow_service.run_workflow()` 进入 `WorkflowService.execute_workflow()`，执行原生 block；任务型 block 最终复用 `app.agent.execute_step()`。因此采购版应把供应商采集、下载、表格提取、人工审批等编排到原生工作流，而不是保留一套独立 pipeline。

核心数据库模型在 `skyvern/forge/sdk/db/models.py`，包括：

- `TaskModel`、`StepModel`、`ActionModel`、`ArtifactModel`
- `OrganizationModel`
- `WorkflowModel`、`WorkflowRunModel`、`TaskRunModel`
- `CredentialModel` 等

核心 Pydantic 模型包括：

- `skyvern/forge/sdk/schemas/tasks.py`：`TaskRequest`、`TaskStatus`、`Task`、`TaskResponse`
- `skyvern/forge/sdk/workflow/models/workflow.py`：`WorkflowDefinition`、`Workflow`、`WorkflowRun`

**结论：** 浏览器 Agent 和工作流运行时是本项目最值得直接复用的资产。

### 2.2 企业扩展层

`enterprise/` 采用按领域拆分的模块化单体：

```text
enterprise/
├── auth/
├── tenant/
├── risk/
├── approval/
├── notification/
├── audit/
├── agents/
├── llm/
├── skills/
├── workflows/
├── dashboard/
├── cache/
└── demo_seed.py
```

企业路由在 `skyvern/forge/api_app.py:create_api_app()` 中导入，并以 `/api/v1` 前缀注册。相同位置还安装 `TenantIsolationMiddleware`，并把 `forge_app.authentication_function`、`authenticate_user_function` 替换为 `enterprise/auth/bridge.py` 的企业 JWT 桥接函数。

这是“接入”而非“闭环集成”：

- **已接通：** 路由挂载、Bearer Token 解析、企业用户查询核心数据库、映射核心 `Organization`。
- **未接通：** `enterprise/approval/risk_detector.py`、审批、通知、审计、`enterprise/agent/`、Skill 与 `enterprise/llm/action_cache.py` 没有被 `ForgeAgent`、`WorkflowService` 或 `ActionHandler` 调用。
- **演示级：** `enterprise/demo_seed.py` 在应用创建时同步调用 `populate_all_stores()`，给审批、审计、Dashboard、缓存注入内存数据。

### 2.3 前端层

前端位于 `skyvern-frontend/`。`router.tsx` 增加 `AuthGuard` 和企业页面，`EnterpriseCredentialProvider` 为请求带上企业 Token。

实际页面对应关系：

| 页面 | 后端接口 | 实际状态 |
| --- | --- | --- |
| `routes/auth/LoginPage.tsx` | `/api/v1/enterprise/auth/login` | 已接后端；Token 由 `store/AuthStore.ts` 存 `localStorage` |
| `routes/enterprise/dashboard/DashboardPage.tsx` | `/enterprise/dashboard/*` | 接内存聚合；approval-time/cost 失败时仍 fallback |
| `routes/enterprise/approvals/ApprovalsPage.tsx` | `/enterprise/approvals/pending`、approve/reject | 接内存审批 store；不是 DB 审批引擎 |
| `routes/enterprise/audit/AuditLogsPage.tsx` | `/enterprise/audit/logs` | 接全局内存审计 store |
| `routes/enterprise/permissions/PermissionsPage.tsx` | 无完整 CRUD API | 使用 `demoDepartments`、`demoUsers` |
| `routes/enterprise/llm/LLMMonitorPage.tsx` | cost/cache 接口 | `stuckTasks` 的源数据明确为 demo |

**限制：** 缺少 Token 刷新、过期处理、统一 401 退出；权限页不是持久化管理；浏览器执行页面没有采购域上下文。

### 2.4 数据层

企业权限模型复用 Skyvern 的 `OrganizationModel`，`enterprise/auth/models.py` 实际新增：

- `DepartmentModel`
- `BusinessLineModel`
- `EnterpriseUserModel`
- `UserDepartmentRoleModel`
- `UserBusinessLineModel`
- `SpecialPermissionModel`
- `TaskExtensionModel`

阶段日志把 Organization 计入“7 张企业表”，但实现上 Organization 是核心表，上述文件实际定义 7 张新增表。

目前只有一份企业迁移：`alembic/versions/2026_03_07_0001-enterprise_permission_tables.py`。其 `down_revision=None` 并带有待设置注释；`alembic/env.py` 只导入 `enterprise.auth.models`，没有导入审批和审计模型。`scripts/ensure_enterprise_schema.py` 又绕过 Alembic 直接建权限表，仍不创建审批/审计表。数据库 schema 来源不唯一，是采购改造前必须消除的根问题。

### 2.5 Agent 层

`enterprise/agent/` 有 `PlannerAgent`、`ExecutorAgent`、`AgentCoordinator` 和 Pydantic schema；`enterprise/llm/` 有模型路由、容错调用、人机接管状态。这些代码有独立测试，但：

- 没有运行时调用方。
- Planner 使用自己的 JSON 解析，没有复用 `resilient_caller.py`。
- Executor 未注入 handler 时会模拟成功。
- “断点”是对象状态，不是数据库持久化。
- `enterprise/llm/task_states.py` 的状态没有映射核心 `TaskStatus`。

因此采购版应保留“Planner/Executor/Coordinator 分工”的思路，但主要实现必须落到 Skyvern 原生任务与工作流状态上。

### 2.6 工作流与 Skill 层

`enterprise/skills/` 有 `BaseSkill`、注册表、`execute_pipeline()` 和 7 个 Skill。它们直接操作 Playwright 风格的 `page`，不是 Skyvern 原生 workflow block。`enterprise/workflows/templates.py` 有 6 个金融模板；`routes.py:instantiate_template()` 只校验参数、生成形如 `task_<id>` 的字符串，没有创建核心 `TaskModel`、持久化工作流、执行 skill pipeline 或调用 Skyvern。

更严重的是：

- `LoginSkill` 把用户名和密码拼入 LLM prompt。
- `FormFillSkill` 把字段值逐项放入 LLM prompt。
- `FileDownloadSkill` 只写本地路径，未接 `Artifact` 或 MinIO。
- `.env.example` 没有 `FINRPA_PARAM_KEY`，带敏感参数实例化时可能直接失败。

采购版必须重写这部分：凭据只通过 `CredentialModel`/vault 引用传给浏览器动作，LLM 只看到字段标签、脱敏 DOM 和结构化 schema。

### 2.7 审批、通知与审计层

- `enterprise/approval/models.py:ApprovalRequestModel` 存在，但没有迁移。
- `enterprise/approval/pubsub.py:create_approval_and_wait()` 有 DB + Redis 等待逻辑，但无业务调用方。
- 审批路由操作 `_approval_store` 字典；应用启动没有给路由注入 Redis，因此 approve/reject 不会唤醒上述等待逻辑。
- `enterprise/notification/channels.py` 实现企业微信、钉钉 HTTP 调用，`dispatcher.py` 有重试与 fallback，但无实际业务调用方、持久化队列或接收人目录。
- `enterprise/audit/models.py:AuditLogModel`、`write_audit_log()`、脱敏器和 MinIO helper 存在，但没有迁移、客户端装配或核心调用方；审计路由读 `_audit_store` 列表。

这三层是可演示的独立模块，不是完整事务闭环。

---

## 3. 当前真实调用链与接通状态

### 3.1 FastAPI 注册链

```text
skyvern/forge/api_app.py:create_api_app()
├── 注册 Skyvern /v1、/api/v1、/api/v2 路由
├── 安装 TenantIsolationMiddleware
├── 注册 enterprise auth/tenant/approval/audit/workflows/dashboard/cache
├── 同步执行 demo_seed.populate_all_stores()
└── 替换 Skyvern authentication_function 为 enterprise JWT bridge
```

当前企业路由装饰器静态计数为 24 个，Day 15 SIT/日志中“23 个接口”的描述已经过时。

### 3.2 企业认证链

```text
POST /api/v1/enterprise/auth/login
→ enterprise/auth/routes.py
→ 查询 EnterpriseUserModel 与部门角色
→ enterprise/auth/jwt_service.py 创建 JWT
→ 前端 localStorage
→ enterprise/auth/bridge.py 验证 Token
→ 返回 Skyvern Organization
→ 可访问原生 Skyvern 路由
```

关键问题：桥接函数只要企业 JWT 有效就映射核心 Organization；原生 Skyvern 创建/运行接口只看到组织身份，看不到部门、采购品类、采购项目、角色或金额权限。因此 `viewer`、`business_requester` 等如果直接调用原生运行接口，可能绕过企业权限。采购版必须提供受控采购入口，并限制或关闭普通企业 Token 对敏感原生写接口的直接访问。

### 3.3 已接通、独立实现与模拟实现

| 模块 | 路由可用 | 持久化 | 进入 Skyvern 主链 | 判定 |
| --- | ---: | ---: | ---: | --- |
| 核心 Task/Workflow | 是 | 是 | 是 | 真实核心 |
| 企业 JWT / Organization 桥 | 是 | DB | 部分 | 可复用但授权不足 |
| 部门/业务线权限解析 | 部分 | DB | 否 | 独立原型 |
| TenantIsolationMiddleware | 是 | ContextVar | 否 | 只传上下文 |
| `query_filter.py` | 否 | — | 否 | helper；未注册 SQLAlchemy event |
| 金融风险 | 无公开业务入口 | 否 | 否 | 纯函数原型 |
| 审批 | 是 | 内存；另有未接 DB 模型 | 否 | 演示级 |
| 通知 | 否 | 否 | 否 | 渠道适配器原型 |
| 审计 | 是 | 内存；DB 模型未迁移 | 否 | 演示级 |
| Agent/LLM 容错 | 否 | 否 | 否 | 独立原型 |
| Skill pipeline | 否 | 否 | 否 | 测试原型，且有泄密风险 |
| 工作流模板实例化 | 是 | 否 | 否 | 返回伪任务 ID |
| Dashboard | 是 | 内存聚合 | 否 | 演示级 |
| Action Cache | 是 | 内存 | 否 | 管理演示，不是执行缓存 |

### 3.4 README 与代码不一致清单

| README/日志描述 | 代码实证 | 结论 |
| --- | --- | --- |
| 全链路企业审批 | DB+Redis 等待函数没有调用方，路由只改内存 store | 未接通 |
| 完整审计、截图 MinIO | 审计列表为内存，MinIO helper 未装配 | 演示级 |
| 自动租户隔离 | `query_filter.py` 没有注册事件；核心查询未统一过滤 | 未实现全局自动隔离 |
| 6 个金融工作流可运行 | `instantiate_template()` 生成伪 task ID，不创建核心任务 | 模板目录而非可执行工作流 |
| Agent 断点恢复 | 状态没有 DB 映射或恢复入口 | 独立内存模型 |
| 生产部署 | 镜像使用 latest、运行时 pip install、TLS 注释、Nginx 上游指向可疑 | 不能据此宣称生产就绪 |
| 601 tests / 85% | 601 静态数量可核对；当前缺 pytest，覆盖率不可复现 | 需要 CI 产物验证 |
| Skyvern 原版无组织隔离 | 核心已有 `OrganizationModel` 和组织过滤 | 描述过度；缺的是采购细粒度 RBAC |
| Action Cache 提升执行 | 缓存没有被核心执行器调用 | 仅管理演示 |

其他配置不一致：

- `.env.example` 使用 `JWT_SECRET_KEY`、`JWT_ALGORITHM`、`JWT_ACCESS_TOKEN_EXPIRE_MINUTES`，代码读取 `SECRET_KEY`、`SIGNATURE_ALGORITHM`、`ACCESS_TOKEN_EXPIRE_MINUTES`；默认 `SECRET_KEY="PLACEHOLDER"`。
- `docker-compose.yml` 实际端口为 18000/18080/15432 等，`Makefile` 文案仍指向 8000/8080/5432/9000。
- `docker-compose.prod.yml` 的 Nginx 前端 upstream 指向 `skyvern:8080`，而 UI 服务名为 `skyvern-ui`；需要实机验证并修正。
- 审批、审计模型没有纳入 Alembic；运行时建表脚本只覆盖权限表。

---

## 4. 模块迁移矩阵

| 原模块 | 采购模块 | 复用程度 | 改造难度 | 主要变化 |
| --- | --- | ---: | ---: | --- |
| Skyvern Task/Step/Action | ProcurementTask/TaskStep 扩展 | 90% | 低 | 复用核心表，增加采购上下文扩展 |
| Skyvern Workflow | 采购工作流定义/实例 | 85% | 中 | 把模板转换为原生 block |
| Organization | Organization | 95% | 低 | 继续复用核心组织 |
| Department | Department | 95% | 低 | 直接复用，只调整展示文案 |
| BusinessLine | ProcurementCategory | 80% | 低 | 改名并调整少量字段 |
| TaskExtension | ProcurementTaskExtension | 75% | 低 | 加品类、供应商和业务对象 ID |
| RoleType | 采购角色 | 85% | 低 | 5 个角色直接改名，保留自批限制 |
| SpecialPermission | 采购特殊范围 | 70% | 低 | 改成跨部门/品类演示权限 |
| 金融风险规则 | 采购风险规则 | 20% | 高 | 规则、证据和阈值全面重写 |
| ApprovalRequest | 采购 ApprovalRequest | 75% | 中 | 改字段、单级审批、显式 continue |
| WeCom/DingTalk | 采购通知 | 90% | 低 | 复用渠道，只改模板和调用点 |
| AuditLog/Sanitizer | 采购 AuditLog | 85% | 低 | 增加业务对象字段和采购调用点 |
| Planner/Executor/Coordinator | Procurement Planner/Executor/Coordinator | 75% | 中 | 保留类、schema 与职责分工；替换金融语义，接入采购 Skill，并把执行状态映射到 Skyvern Task/Workflow；禁止无 handler 时模拟成功 |
| 7 个通用 Skill | 7 个采购 Skill | 55% | 中 | 保留契约，去除敏感值进入 LLM |
| 6 个金融模板 | 6 个采购模板元数据 | 60% | 中 | 3 个实现、3 个仅说明 |
| Dashboard stats | Procurement Dashboard | 80% | 低 | 改 5 个指标，可继续使用 demo store |
| Action Cache | 演示级 Action Cache | 95% | 低 | 原样保留，增加敏感动作 bypass 说明 |
| 企业前端壳 | 采购前端 | 65% | 中 | 页面/表格可复用，领域页面重做 |
| Docker/Nginx | 采购演示部署 | 60% | 中 | 固定版本、统一端口/环境变量、健康检查 |
| Demo seed | 采购演示数据 | 80% | 低 | 替换字段、模板和固定案例 |

---

## 5. ProcureRPA Enterprise 目标架构

### 5.1 架构原则

采用“Skyvern 核心 + 采购模块化单体 + React 前端 + PostgreSQL/Redis/MinIO”的结构：

```text
采购前端
  ↓ /api/v1/enterprise/procurement/*
FastAPI 采购 API（认证、范围校验、幂等）
  ├── 采购领域服务（供应商、报价、采购申请、订单）
  ├── 简单风险函数与单级审批
  ├── 复用现有审计 / 通知模块
  └── 采购 Agent 编排层
        ├── PlannerAgent：生成受模板和 Skill 白名单约束的采购计划
        ├── ExecutorAgent：分发 Skill/handler，不直接重写浏览器执行
        └── AgentCoordinator：状态协调、暂停、审批后恢复和人工接管
              ↓
      SkyvernIntegrationService
        ↓
Skyvern WorkflowService / TaskService / ForgeAgent
        ↓
浏览器会话、Action、Artifact、Credential
```

保留 `enterprise/agent/` 中 Planner、Executor、Coordinator 的企业编排层，并将其改造成采购语义。该层负责计划、Skill 分发和状态协调；实际页面理解、浏览器动作、Artifact 与会话仍交给 Skyvern 原生 Task/Workflow/ForgeAgent。`SkyvernIntegrationService` 作为二者之间的薄适配层，避免采购 Executor 演变成另一套浏览器执行引擎。

### 5.2 演示级与生产级边界

| 能力 | 演示级首版 | 生产升级 |
| --- | --- | --- |
| 供应商站点 | 2～3 个受控模拟站点 | 正式站点授权、变更监测、合规评审 |
| 采购系统 | 模拟采购门户 | ERP/SRM API 优先，浏览器作为补充 |
| 调度 | APScheduler/已有后台任务 | 分布式 scheduler、租约、故障转移 |
| 审批 | 单级 `ApprovalRequest`，API 审批后继续 | 多阶段、Outbox、SLA、委托/加签 |
| 文件 | MinIO 单桶分前缀 | KMS、病毒扫描、保留策略、法律留存 |
| 认证 | JWT + 服务端权限查询 | OIDC/SSO、MFA、撤销、密钥轮换 |
| 报价标准化 | 确定性规则 + 受限 LLM | MDM、单位/币种主数据、人工校准 |
| 监控 | 结构化日志与 Dashboard | OTel、集中告警、SLO |

### 5.3 推荐集成点

1. **启动前：** 采购 API 校验组织、部门、品类和角色。
2. **创建时：** 写 `ProcurementTaskExtension`，关联核心 `task_id`。
3. **提交前：** 调用一个确定性风险函数；high/critical 创建单级 `ApprovalRequest`。
4. **审批后：** 演示版可通过显式 continue API 或 HumanInteraction block 继续，不另建第二套任务。
5. **动作后：** 复用现有审计 logger；文件引用核心 `ArtifactModel` 或 MinIO 对象键。

---

## 6. 采购权限模型

### 6.1 本轮权限范围

授权结果必须同时满足：

```text
same organization
AND department scope
AND procurement category scope
AND role permits action
AND separation-of-duties constraints
```

采购项目是业务过滤字段，不作为首版权限维度。金额控制由角色上的固定阈值或一个 `approval_limit` 字段表达，不新增 `ScopeGrant`、`AmountPermission` 和权限版本平台。

### 6.2 角色职责

| 角色 | 允许 | 禁止/约束 |
| --- | --- | --- |
| `platform_admin` | 用户、组织和演示配置 | 不批准自己发起的请求 |
| `procurement_manager` | 管理本部门/品类、查看 Dashboard | 可作为审批人，但不能自批 |
| `procurement_operator` | 采集报价、创建申请、运行工作流 | 不能审批自己的任务 |
| `procurement_approver` | 审批 high/critical 任务 | 不执行最终浏览器操作 |
| `viewer` | 范围内只读 | 无执行和审批权限 |

`finance_approver`、`compliance_auditor`、`business_requester` 只在“生产扩展角色”说明中保留，不进入首版枚举和页面。上述 5 个角色可直接映射现有 `super_admin/org_admin/operator/approver/viewer`。

### 6.3 职责分离

- `initiator_user_id != approver_user_id`。
- 一个任务只有一个有效审批结果。
- high 和 critical 都进入同一审批队列；critical 可要求管理员或直接阻止。
- 复用 `UserDepartmentRoleModel`，不新增角色分配平台。

### 6.4 金额控制

首版只支持单一演示币种 CNY。金额使用 `Decimal/Numeric`，并通过固定配置或角色字段 `approval_limit` 判断是否需要审批。多币种换算、有效期、项目级金额授权和独立 `AmountPermission` 表均属于生产升级。

---

## 7. 采购风险规则

### 7.1 风险等级与处理

| 等级 | 处理 |
| --- | --- |
| `low` | 自动继续；记录规则、输入摘要和证据 |
| `medium` | 可继续或要求操作者二次确认；审计并通知负责人 |
| `high` | 工作流暂停，进入单级审批 |
| `critical` | 工作流暂停，由管理员/审批人决定，或规则直接禁止 |

最终风险为 `max(deterministic_rule_level, llm_suggested_level)`。LLM 可以提高等级和解释异常，不允许降低规则等级；金额、提交、删除、银行账户和敏感文件决策完全由确定性规则控制。

### 7.2 本轮实现的 5 类规则

| 规则 | 典型等级 | 确定性证据 | 动作 |
| --- | --- | --- | --- |
| 高金额采购 | high/critical | CNY 金额超过固定阈值 | 暂停审批 |
| 非白名单供应商 | high | `Supplier.is_whitelisted` | 暂停审批 |
| 供应商资质过期 | critical | `qualification_expire_at` | 阻止或审批 |
| 报价明显偏离 | medium/high | 同批次供应商均价或固定比例 | 标记并复核 |
| 高风险操作 | high/critical | submit/delete/bank-change/sensitive-upload | 统一进入审批或禁止 |

重复采购、数量异常、历史均价、银行账户专项流程、文件 DLP 等仍列入设计目录，但不要求首版分别建规则。规则使用 Python 函数和常量配置，不新增 `risk_rule_sets/risk_rules/risk_assessments/risk_findings` 表。LLM 只补充解释，不参与金额和提交决定。

---

## 8. 核心采购数据模型

### 8.1 本轮实际模型

| 实体 | 职责 | 主要关系 |
| --- | --- | --- |
| Organization | 企业租户 | 复用核心 `OrganizationModel` |
| Department | 采购需求和预算归属 | N:1 Organization；N:M User |
| User / Role | 发起、执行、审批主体 | 复用企业用户和部门角色 |
| ProcurementCategory | 采购品类 | 由 `BusinessLineModel` 改名或改字段 |
| Material | 标准物料主数据 | 1:N QuotationItem；PR/PO 通过 JSON items 引用 |
| Supplier | 供应商、白名单、资质状态和到期时间 | 凭据使用核心 Credential 引用 |
| Quotation | 一次供应商报价单 | N:1 Supplier；1:N QuotationItem |
| QuotationItem | 标准化报价行与原始证据 | N:1 Quotation/Material |
| PurchaseRequest | 采购申请，首版可用 JSON items | 关联推荐报价和 ApprovalRequest |
| PurchaseOrder | 订单及最近一次跟踪状态 | N:1 Supplier |
| ProcurementTaskExtension | 采购任务上下文 | 1:1 核心 Task；关联 category/supplier/business_id |
| ApprovalRequest / AuditLog | 审批和审计 | 复用现有模型并修改字段 |

首版新增约 7 张采购表，不实现独立的 Project、SupplierCredential、Qualification、PR/PO Item、StatusSnapshot、WorkflowInstance、ApprovalDecision、Notification 表。这些实体只保留在生产扩展说明中。

### 8.2 状态模型

- PurchaseRequest：`draft → pending_approval → approved → submitted/rejected/failed`
- PurchaseOrder：`placed → shipped → delivered`，异常为 `delayed/out_of_stock/price_changed`
- ApprovalRequest：`pending → approved/rejected`
- RPA 运行状态直接读取 Skyvern Task/Workflow，不复制状态机。

---

## 9. 报价标准化设计

### 9.1 标准化输出

```json
{
  "supplier_id": "supplier_001",
  "material_code": "MAT-001",
  "product_name": "工业交换机",
  "brand": "Example",
  "model": "S5735",
  "specification": "24GE+4SFP",
  "unit": "台",
  "package_specification": "1台/箱",
  "unit_price": 1200.00,
  "currency": "CNY",
  "tax_included": true,
  "tax_rate": 0.13,
  "minimum_order_quantity": 10,
  "stock": 32,
  "shipping_fee": 0.00,
  "delivery_days": 7,
  "payment_terms": "月结30天",
  "source_url": "https://supplier.example/items/001",
  "captured_at": "2026-07-28T10:00:00Z",
  "valid_until": "2026-08-04T23:59:59Z",
  "evidence_artifact_id": "artifact_001"
}
```

### 9.2 处理原则

1. 原始字段和页面/文件证据永不覆盖，存 `raw_payload` 与 Artifact 引用。
2. 首版只演示 CNY；税率和包装换算使用确定性 Decimal 计算。
3. 物料映射以 `material_code` 为主，LLM 只在字段缺失时提供候选。
4. 比价必须对齐相同物料、规格、数量基准、税口径和币种；无法对齐则标记 `not_comparable`。
5. 首版不单独建设报价缓存；需要时复用现有 Action Cache。
6. 密码、银行账户、合同全文和敏感附件不得进入 LLM。

---

## 10. 采购 Skill 设计

首版只实现 7 个采购 Skill；分页、表单、表格和下载直接使用 Skyvern 原生 action/block，不再各建一个 Skill。

| Skill | 输入 | 输出 | 调用 Skyvern | 失败处理 | 敏感 | 审计 | 缓存 |
| --- | --- | --- | --- | --- | ---: | ---: | --- |
| LoginSkill | `credential_id, login_url` | 登录状态 | Credential + Task block | 失败转人工，不处理验证码绕过 | 是 | 只记引用和结果 | 否 |
| SupplierSearchSkill | material、supplier | 商品候选 | 原生搜索 action | 单站失败返回错误 | 否 | 是 | 否 |
| QuotationExtractSkill | 页面/文件 Artifact、schema | 原始报价候选 | Extract block + 受限 LLM | Pydantic/schema 校验；保留原始证据 | 价格敏感 | 是 | 否 |
| QuotationNormalizeSkill | raw quotation、material | 标准化 QuotationItem | 确定性 Python 函数 | 不可比则返回原因 | 是 | 记录差异 | 否 |
| QuotationCompareSkill | 标准化报价、需求 | 排名、异常、推荐理由 | 领域服务，不需浏览器 | 缺样本/口径不一致明确返回 | 是 | 是 | 否 |
| PurchaseRequestSkill | PR 草稿、目标系统、approval_id | 草稿/提交回执 | FormFill + submit action | 提交前检查审批和幂等键 | 高 | 脱敏审计 | 否 |
| OrderStatusCheckSkill | PO、portal | 当前状态和异常 | Login/Search/Extract blocks | 返回失败状态，下一次重试 | 中 | 是 | 否 |

---

## 11. 核心采购工作流

### 11.1 六个模板

1. **[本轮实现]** `supplier_quotation_collection`：供应商登录、搜索、提取、标准化和比价。
2. **[本轮实现]** `purchase_request_submission`：选择报价、填申请、风险判断、审批和提交。
3. **[本轮实现]** `purchase_order_tracking`：查询订单并检测延期、缺货和价格变化。
4. **[仅设计说明]** `multi_supplier_comparison`：首版合并到报价采集流程，不单独运行。
5. **[仅设计说明]** `supplier_onboarding_collection`：只保留模板元数据。
6. **[仅设计说明]** `exception_order_handling`：首版由订单跟踪直接通知，不单独编排。

### 11.2 工作流一：供应商报价采集与比价

**输入：** organization、department、category、material、quantity、supplier list、credential IDs。  
**步骤：**

```text
创建 Skyvern Task/Workflow
→ 依次访问两个模拟供应商
→ LoginSkill（凭据引用）
→ SupplierSearchSkill
→ QuotationExtractSkill
→ QuotationNormalizeSkill
→ QuotationCompareSkill
→ 写报价、证据和审计
```

**输出：** 标准化报价、供应商排名、异常和证据 Artifact。  
**风险节点：** 非白名单、资质过期、报价明显偏离。  
**审批节点：** 只读采集不审批。  
**端到端演示：** 两个模拟供应商站点对同一工业交换机返回不同含税口径、MOQ 和交期，系统转换后输出到岸总价排名。

### 11.3 工作流二：采购申请与审批

**输入：** comparison_id、selected_quotation_item_ids、requester、department、delivery address、采购理由。  
**步骤：**

```text
读取比价结果
→ 校验推荐供应商及资质
→ 创建 PurchaseRequest 草稿
→ 在模拟采购系统填表但不提交
→ 确定性风险检测
→ low/medium 继续或确认
→ high/critical 创建单级 ApprovalRequest 并暂停
→ 审批人批准或拒绝
→ 批准后重新检查页面状态
→ 幂等提交
→ 保存回执和审计
```

**输出：** PurchaseRequest、审批结果、外部系统申请号和回执。  
**风险节点：** 金额、供应商状态、资质和报价偏离。  
**审批节点：** high/critical 均进入同一审批队列；发起人不得审批。  
**恢复要求：** 首版允许显式 continue；提交前必须检查幂等键，避免重复申请。

### 11.4 工作流三：订单状态跟踪

**输入：** active POs、supplier credentials、schedule、异常阈值。  
**步骤：**

```text
调度到期
→ 按供应商复用/创建安全浏览器会话
→ 查询订单
→ 提取订单与物流状态
→ 更新 PurchaseOrder 最近状态
→ 与前次状态和订单基线比较
→ 检测延期、缺货、数量/价格变化
→ 写审计并直接通知采购负责人
```

**输出：** 最新状态、差异、异常和通知结果。  
**风险节点：** 页面价格与订单价变化、缺货、预计到货超过承诺日。  
**审批节点：** 单纯查询不审批；接受涨价、替代物料或取消订单必须人工批准。  
**幂等：** 状态未变化时不重复通知；首版不单独建设状态快照表。

---

## 12. 16 阶段完整采购开发路线

迁移分类：A＝基本直接复用；B＝保留架构、修改领域模型；C＝保留思路、重写主要实现；D＝采购项目新增能力。

### Day 1：Skyvern 基线、脚手架、Docker 与企业扩展层（A）

#### 1. 阶段目标

建立可启动的 Skyvern 基线、模块化 `enterprise/` 扩展层和本地 Docker 环境；固定上游版本，验证一个最小浏览器任务能从 API 进入真实 `ForgeAgent`。

#### 2. 原项目实现

- 分支：`origin/day-1/project-setup`；实现提交 `c3d8e38`。
- 主要文件：`skyvern/`、`skyvern-frontend/`、`enterprise/__init__.py`、`docker-compose.yml`、`Dockerfile`、`Dockerfile.ui`、`.env.example`、`Makefile`。
- 路由入口：`skyvern/forge/api_app.py:create_api_app()`；核心 `POST /v1/run/tasks`。
- 日志：该分支 `summaries/day_1_summary.md`、`summaries/day_1_code_list.md`。
- 该分支只有 `tests/conftest.py` 与空的 unit/integration 包骨架，没有 Day 1 专属自动化测试；日志中的环境验证不等于真实浏览器 E2E。

#### 3. 原设计解决的问题

以已有 Skyvern 为浏览器自动化底座，避免从零实现 DOM 解析、LLM 动作生成、浏览器会话、任务/步骤/制品模型，并为后续企业模块留出同仓扩展位置。

#### 4. 原设计方案

复制 Skyvern 核心与前端，在根目录增加 Docker Compose、企业包和项目级文档；通过后续修改 `create_api_app()` 把企业能力挂载到同一 FastAPI 应用。

#### 5. 原设计的优点和限制

优点是核心能力真实、单仓易演示。限制是镜像标签偏动态，容器启动时安装依赖，端口文档与 Compose 不一致；复制上游后未来合并 Skyvern 更新成本较高。README 将此称为“企业级基线”，但 TLS、固定供应链和恢复验证尚不完整。

#### 6. 采购场景改造方案

保留仓库结构和原生运行时；将产品名、环境变量前缀和演示说明改为 ProcureRPA。首日只加入空的采购模块边界和配置，不提前生成所有领域代码。建立上游 Skyvern 版本/commit 记录。

#### 7. 建议目录结构

```text
enterprise/
├── procurement/
│   └── __init__.py
├── integrations/
│   └── skyvern.py
└── config.py
docs/
└── architecture/
```

#### 8. 数据模型变化

本阶段不新增业务表。只确认核心 `OrganizationModel`、`TaskModel`、`StepModel`、`WorkflowModel` 可复用，并确定采购模型使用同一 SQLAlchemy `Base` 与统一 Alembic。

#### 9. API 设计

| 方法 | 路径 | 请求/响应 | 权限 |
| --- | --- | --- | --- |
| GET | `/api/v1/enterprise/procurement/health` | `HealthResponse` | 无敏感信息，可匿名 |
| POST | `/api/v1/enterprise/procurement/smoke-task`（仅 dev） | `SmokeTaskRequest` / core task ID | `platform_admin` |

生产构建禁用 smoke 路由。

#### 10. 核心实现步骤

1. 固定 Python/Node、Skyvern 镜像或 commit。
2. 统一 Compose、Makefile、README 端口。
3. 加采购配置前缀与安全启动检查，拒绝 placeholder secret。
4. 用现有 `create_api_app()` 注册最小采购 router。
5. 启动 PostgreSQL、Redis、MinIO、API、UI。
6. 调用原生任务 API 验证 Task/Step 真实落库。

#### 11. 测试方案

- 正常：健康检查与最小任务成功。
- 权限/参数：非管理员不能启动 smoke，非法 URL 拒绝。
- 外部失败：浏览器、DB、Redis、MinIO 分别不可用时健康状态可诊断。
- 多租户：smoke 任务带正确 organization。
- 幂等：相同 smoke idempotency key 不创建双任务。
- LLM 错误：返回失败状态，不伪造成功。

#### 12. 验收标准

`docker compose up` 后 API/UI/DB/Redis/MinIO 健康；一个受控页面任务经过 `TaskModel → StepModel → ActionModel`；固定版本可重复构建；没有默认弱密钥。

#### 13. 当前阶段总结文档

`day_1_summary.md` 建议包含：目标、版本基线、服务拓扑、真实 smoke 调用链、启动命令、已知限制、Day 2 输入。

#### 14. 代码清单文档

`day_1_code_list.md` 建议按“新增/修改/复用/配置/测试”列出路径、职责、关键入口和验证命令，明确没有业务模型。

#### 15. 风险与待办

- **简化：** 单仓模块化单体和模拟站点。
- **生产升级：** 镜像签名、SBOM、TLS、secrets manager。
- **依赖：** Day 2 依赖统一 Base/Alembic；Day 14 再做部署硬化。

### Day 2：采购组织、部门、品类、项目与角色模型（B）

#### 1. 阶段目标

复用原项目的组织、部门、业务线和角色模型，把业务线改为采购品类，并补充最小采购任务上下文。

#### 2. 原项目实现

- 分支：`origin/day-2/permission-data-model`；提交 `515d1fe`。
- `enterprise/auth/models.py`：`DepartmentModel`、`BusinessLineModel`、`EnterpriseUserModel`、`UserDepartmentRoleModel`、`UserBusinessLineModel`、`SpecialPermissionModel`、`TaskExtensionModel`。
- `enterprise/auth/enums.py`、`constraints.py`、`tests/fixtures/seed_demo_data.sql`。
- 测试：`tests/unit/test_auth_models.py`。
- 迁移：`alembic/versions/2026_03_07_0001-enterprise_permission_tables.py`。
- 原 Organization 复用 `skyvern/forge/sdk/db/models.py:OrganizationModel`。

#### 3. 原设计解决的问题

在 Skyvern 组织隔离之上增加部门、业务线、角色和任务上下文，使金融任务可按企业组织结构授权。

#### 4. 原设计方案

企业模型与核心共享 SQLAlchemy `Base`；用户通过部门角色与业务线关联获得权限；特殊权限提供额外范围；任务扩展表关联组织、部门和业务线。

#### 5. 原设计的优点和限制

共享 Base、复用 Organization 是正确方向。限制包括：

- `UserDepartmentRoleModel` 主键 `(user_id, department_id)` 使一名用户在同部门只能有一个角色，约束比文档描述更严格。
- 操作员/审批人互斥 trigger 与上述主键部分重复。
- `TaskExtensionModel.task_id` 没有核心 Task 外键。
- 迁移 `down_revision=None` 且未接已有迁移链。
- `alembic/env.py` 未导入后续企业模型。

#### 6. 采购场景改造方案

`BusinessLine` 转换为 `ProcurementCategory`；项目先作为任务/采购申请字段。沿用现有 5 类角色结构并改名，不新增角色、范围和金额权限平台。

#### 7. 建议目录结构

```text
enterprise/procurement/
├── models.py
├── enums.py
└── seed.py
alembic/versions/
└── *_procurement_access_domain.py
```

#### 8. 数据模型变化

新增/调整：

- 将 `business_lines` 语义调整为采购品类，或新增一张轻量 `procurement_categories`。
- 扩展 `TaskExtensionModel`：`category_id`、`project_name`、`supplier_id`、`business_object_id`。
- 将 5 个角色名称映射为采购角色。
- 金额阈值使用配置或部门角色上的 `approval_limit`，不新建金额权限表。

#### 9. API 设计

| 方法 | 路径 | 请求/响应 | 权限 |
| --- | --- | --- | --- |
| GET | `/procurement/context-options` | 当前部门/品类/角色 | 登录用户 |

所有路径实际前置 `/api/v1/enterprise`。

#### 10. 核心实现步骤

1. 先画实体约束并确定复用核心 Organization。
2. 统一 Alembic head，删除运行时“另一套建表真源”。
3. 改角色枚举和业务线/品类名称。
4. 扩展 TaskExtension 并补核心 task FK。
5. 写最小采购种子：一组织、两部门、三品类、五角色。

#### 11. 测试方案

- 正常 CRUD 和关系。
- 重复品类编码和无效外键。
- 跨组织 FK 和查询隔离。
- 发起人与审批角色冲突。
- 固定审批阈值边界。
- migration upgrade/downgrade/upgrade。
- 幂等种子重复运行。

#### 12. 验收标准

空数据库可通过单一 `alembic upgrade head` 建成；品类和任务上下文有真实 FK；5 个角色可分配；种子可重复运行。

#### 13. 当前阶段总结文档

大纲：领域映射、ER 关系、角色清单、范围算法、迁移版本、种子账号、约束测试、已知简化。

#### 14. 代码清单文档

大纲：模型、枚举、schema、迁移、seed、API、测试；每项列类名、表名、索引、复用来源。

#### 15. 风险与待办

- **简化：** 不建 ProcurementProject、ScopeGrant、AmountPermission 和独立角色表。
- **生产升级：** SSO 用户同步、组织树历史版本、细粒度 ABAC。
- **依赖：** Day 3 使用现有角色；Day 4 使用组织/部门/品类；Day 5 使用固定金额阈值。

### Day 3：JWT 认证与采购权限校验（B）

#### 1. 阶段目标

完成企业用户登录、服务端权限解析和受控 Skyvern 访问；杜绝企业 Token 绕过采购权限直接运行敏感原生任务。

#### 2. 原项目实现

- 分支：`origin/day-3/auth-and-permission`；提交 `2ad2207`。
- `enterprise/auth/jwt_service.py`、`permission.py:resolve_permission()`、`dependencies.py`、`routes.py`、`bridge.py`。
- 路由：`GET /enterprise/auth/organizations`、`POST /enterprise/auth/login`、`GET /enterprise/auth/me`。
- `skyvern/forge/api_app.py` 注册 router 并替换认证函数。
- 测试：`tests/unit/test_auth_jwt.py`、`test_auth_dependencies.py`、`test_permission_resolver.py`，并继续运行 `test_auth_models.py`。

#### 3. 原设计解决的问题

让企业账号能够登录 Skyvern，并依据组织、部门、角色和业务线判断是否有操作权限。

#### 4. 原设计方案

自签 JWT 包含组织和权限信息；FastAPI dependency 解析 CurrentUser；bridge 将企业 JWT 转成核心 `Organization`，从而复用原生路由。

#### 5. 原设计的优点和限制

认证桥接减少对核心的修改，dependency 易读。限制：

- JWT 是“胖 Token”，权限变化后旧 Token 仍有效。
- 缺少 refresh/revoke/session version；这是生产限制，不阻塞原型。
- `.env.example` 的 JWT 变量名与代码设置项不匹配，可能使用 `PLACEHOLDER`。
- bridge 只返回 Organization，不能表达采购 scope；原生写路由形成绕过面。
- login 为部门名称产生额外查询，可后续优化，但不是首要问题。

#### 6. 采购场景改造方案

沿用当前 JWT 和 FastAPI dependency，修正环境变量与弱密钥。采购写接口读取数据库中的组织、部门、品类和角色；不新增 session、refresh 和权限版本系统。敏感原生写操作只允许经采购 API 调用。

#### 7. 建议目录结构

```text
enterprise/auth/
├── jwt_service.py
├── dependencies.py
└── bridge.py
enterprise/procurement/access/
└── dependencies.py
```

#### 8. 数据模型变化

不新增认证表。继续使用 `EnterpriseUserModel` 和短期 access token；密码使用现有强哈希，永不进入 LLM/日志。

#### 9. API 设计

| 方法 | 路径 | 请求/响应 | 权限 |
| --- | --- | --- | --- |
| POST | `/enterprise/auth/login` | `LoginRequest` / `LoginResponse` | 匿名 |
| GET | `/enterprise/auth/me` | `CurrentUserResponse` | 登录用户 |

#### 10. 核心实现步骤

1. 对齐环境变量并在非 dev 拒绝弱 secret。
2. 沿用当前 JWT claims 和 dependency。
3. 实现一个简单 `require_procurement_role()`。
4. 采购 API 校验后内部调用 Skyvern。
5. 限制企业 Token 对原生敏感写路由。
6. 前端遇到 401 清除 token 并返回登录页。

#### 11. 测试方案

- 正常登录、过期、错误签名、禁用用户。
- viewer/operator/manager 的允许与拒绝矩阵。
- 跨组织、跨部门、跨品类拒绝。
- 固定金额阈值边界。
- 直接调用原生 run 接口不能绕过。
- 登录重试不泄露密码。

#### 12. 验收标准

弱密钥无法在非开发环境启动；采购写接口有角色依赖；viewer 无法运行任务；日志不含密码和完整 Token。

#### 13. 当前阶段总结文档

大纲：认证流、Token claims、权限计算、原生路由边界、角色矩阵、威胁模型、测试证据。

#### 14. 代码清单文档

大纲：认证文件、采购 access service、路由保护点、配置变化、前端拦截器、测试文件。

#### 15. 风险与待办

- **简化：** 只发 access token，不做 refresh、session、permission version 和设备管理。
- **生产升级：** OIDC/SSO、MFA、密钥轮换、集中撤销。
- **依赖：** Day 4 实施数据范围；Day 15 完成前端认证桥接。

### Day 4：组织、部门、采购项目与品类数据隔离（B）

#### 1. 阶段目标

让每一次列表、详情、导出、任务运行和后台作业都执行统一的采购范围约束，防止只保护企业自定义路由而遗漏 Skyvern 核心查询。

#### 2. 原项目实现

- 分支：`origin/day-4/tenant-isolation-middleware`；提交 `72ee56a`。
- `enterprise/tenant/context.py`、`middleware.py:TenantIsolationMiddleware`、`query_filter.py`、`routes.py`。
- 路由：`GET /enterprise/tasks`、`GET /enterprise/admin/visibility`。
- `TaskExtensionModel` 用于组织/部门/业务线查询。
- 测试：`tests/unit/test_tenant_context.py`、`test_tenant_middleware.py`、`test_tenant_query_filter.py`；没有独立的 tenant route 测试文件。

#### 3. 原设计解决的问题

把 JWT 中的租户信息放入 `ContextVar`，让业务查询能够按当前组织、部门和业务线过滤，并提供管理员可见性诊断。

#### 4. 原设计方案

中间件解析 Bearer Token 并设置上下文；query helper 拼接过滤条件；企业任务列表手动查询 TaskExtension；特殊权限允许额外部门/业务线。

#### 5. 原设计的优点和限制

ContextVar 适合异步请求传递，但不是授权边界。`query_filter.py` 注释称“自动”，实际没有注册 SQLAlchemy event，导入的 `event` 未使用；原生 Task/Workflow 查询不受过滤。`diagnose_visibility` 查询目标 admin 时缺少 organization 条件，存在猜 ID 查看他组织用户信息的风险。`resolve_permission()` 的 `cross_org` 在不同组织时先返回 NONE，实际只是跨部门。

#### 6. 采购场景改造方案

复用现有 ContextVar 和 query helper，在采购列表/详情中显式过滤 organization、department、category。对核心任务通过 `ProcurementTaskExtension` 查询；不建设通用 Repository 层。

#### 7. 建议目录结构

```text
enterprise/procurement/access/
└── dependencies.py
enterprise/procurement/tasks.py
```

#### 8. 数据模型变化

- 每个顶层采购实体增加非空 `organization_id`。
- `ProcurementTaskExtension` 增加 `department_id/category_id/supplier_id` 和核心 task FK。
- 高频隔离索引以 `organization_id` 为首列。
- 详情查询检查 organization，列表按 department/category 过滤。

#### 9. API 设计

| 方法 | 路径 | 请求/响应 | 权限 |
| --- | --- | --- | --- |
| GET | `/procurement/tasks` | filter / paged tasks | 按 scope |
| GET | `/procurement/tasks/{id}` | task detail | 同组织且命中范围 |

#### 10. 核心实现步骤

1. 扩展现有 tenant context 的 category。
2. 在任务列表和详情中显式增加过滤条件。
3. 对核心 Task 查询 join 采购扩展。
4. 修复 visibility 目标组织条件。

#### 11. 测试方案

- 同组织同部门/品类正常。
- 同组织不同部门/品类拒绝。
- 不同组织即使资源 ID 相同也拒绝。
- admin 只看本组织；platform admin 用专门平台接口。
- Dashboard 和订单跟踪不能越权。
- 缺 task context 默认拒绝，不“放行兼容”。
- 幂等写仍受同一 scope。

#### 12. 验收标准

任务、报价、申请和订单的跨组织测试通过；viewer 不能通过原生入口运行任务；visibility 不泄露他组织用户。

#### 13. 当前阶段总结文档

大纲：scope 算法、保护资源清单、核心 Task join、后台任务策略、漏洞修复、隔离测试矩阵。

#### 14. 代码清单文档

大纲：context、repository、dependency、model/index、受保护路由、跨租户测试和 SQL 证据。

#### 15. 风险与待办

- **简化：** 不做通用 Repository、透明 ORM 过滤或项目级隔离。
- **生产升级：** 可增加 PostgreSQL RLS 作为纵深防御。
- **依赖：** 后续每个 Day 的服务必须接受 scope；Day 11/13 特别注意聚合与缓存隔离。

### Day 5：采购风险识别（C）

#### 1. 阶段目标

实现一个可解释的采购风险函数，覆盖 5 类演示规则。

#### 2. 原项目实现

- 分支：`origin/day-5/financial-risk-detector`；提交 `895df43`。
- `enterprise/approval/risk_keywords.py`：金融中英文关键词与金额正则。
- `enterprise/approval/risk_detector.py:detect_risk()`：规则初筛和可注入 LLM 补充。
- `enterprise/approval/routing.py:route_approval()`：按风险等级路由。
- 测试：`tests/unit/test_risk_detector.py`，覆盖关键词、金额、LLM 返回和路由。

#### 3. 原设计解决的问题

在 RPA 执行前识别高风险金融操作，决定是否需要人工审批，并允许 LLM 捕捉关键词规则遗漏的语义风险。

#### 4. 原设计方案

第一阶段通过关键词和金额正则得到风险等级，第二阶段可调用 LLM，最后产生 level/reason/approval route。high、critical 路由到固定部门。

#### 5. 原设计的优点和限制

两阶段思路可复用，规则输出易解释。但当前 LLM 结果可把确定性 high/critical 降到 medium；金额阈值与审批部门硬编码；没有组织级规则版本、证据快照、采购对象或运行时调用方。金融关键词不能通过改名转成采购规则。

#### 6. 采购场景改造方案

重写规则常量和输入模型。确定性函数根据金额、供应商、资质、报价偏离和操作类型返回等级；LLM 只基于脱敏描述补充说明，不能降低等级。结果直接写任务扩展或审计 JSON。

#### 7. 建议目录结构

```text
enterprise/procurement/risk/
├── rules.py
└── detector.py
```

#### 8. 数据模型变化

不新增风险表。为 `ProcurementTaskExtension` 或 `PurchaseRequest` 增加 `risk_level`、`risk_reason`、`risk_result JSON`。

#### 9. API 设计

风险函数由采购申请提交接口内部调用，不新增公开 API。

#### 10. 核心实现步骤

1. 定义结构化 `RiskContext`，禁止只解析自然语言金额。
2. 实现 5 类确定性规则。
3. 使用 Decimal 和固定 CNY 阈值。
4. 可选接入脱敏 LLM 说明，并保证“只升不降”。
5. 在采购申请预提交前调用并把结果写入任务。

#### 11. 测试方案

- 5 类规则的正常、边界和缺数据。
- 阈值相等、负数和异常税率。
- LLM 非 JSON、超时、恶意降级、提示注入。
- 同输入结果确定。

#### 12. 验收标准

5 类风险有可运行测试；LLM 永远不能降低确定性等级；预提交路径调用风险函数；敏感字段不进入 prompt。

#### 13. 当前阶段总结文档

大纲：5 类实现规则、扩展规则目录、等级策略、确定性/LLM 边界、调用点和测试结果。

#### 14. 代码清单文档

大纲：schema、规则函数、可选 LLM adapter、API、集成点和测试。

#### 15. 风险与待办

- **简化：** 固定 CNY 阈值和同批次均价，不建风险表或规则管理页面。
- **生产升级：** 规则审批发布、回测、模型治理、主数据质量监控。
- **依赖：** Day 6 消费风险结果；Day 10 报价标准化提供可靠输入。

### Day 6：采购分级审批引擎（C）

#### 1. 阶段目标

复用 `ApprovalRequestModel` 实现单级审批，表达高风险暂停、审批和继续执行。

#### 2. 原项目实现

- 分支：`origin/day-6/approval-engine`；提交 `4bac4e8`。
- `enterprise/approval/models.py:ApprovalRequestModel`。
- `enterprise/approval/pubsub.py:create_approval_and_wait()`。
- `enterprise/approval/routes.py` 的 pending/approve/reject。
- 测试：`tests/unit/test_approval_model.py`、`test_approval_pubsub.py`、`test_approval_routes.py`；pub/sub 测试使用 `FakeRedis`。
- 路由在 `skyvern/forge/api_app.py` 注册。

#### 3. 原设计解决的问题

高风险任务在执行前停住，通知审批人，审批决定通过 Redis 到达等待者，任务再继续或终止。

#### 4. 原设计方案

审批记录模型 + Redis pub/sub + 超时；API 读取和修改审批。设计意图是数据库记录事实，Redis 只负责唤醒。

#### 5. 原设计的优点和限制

DB 为事实源、Redis 为信号的方向正确。但当前运行应用的审批路由只操作 `_approval_store`；没有给路由设置 Redis，`create_approval_and_wait()` 也没有业务调用方；模型未迁移。因此页面点“批准”不会恢复真实 Skyvern 任务。模型也不足以表达多阶段、决定历史、职责分离和幂等。

#### 6. 采购场景改造方案

扩展现有 `ApprovalRequestModel`，保存 requester、approver、risk、status、comment。high/critical 创建 pending 记录；批准后由显式 continue API 或简单 HumanInteraction block 继续。首版不要求 Redis pub/sub 真正闭环。

#### 7. 建议目录结构

```text
enterprise/procurement/approval/
├── models.py
├── schemas.py
└── routes.py
```

#### 8. 数据模型变化

- 复用 `approval_requests`，增加 `requester_id`、`approver_id`、`risk_level`、`comment`、`decided_at`。
- 状态仅 `pending/approved/rejected`。
- 不新增 stage、decision、version 表。

#### 9. API 设计

| 方法 | 路径 | 请求/响应 | 权限 |
| --- | --- | --- | --- |
| GET | `/procurement/approvals/pending` | filters / page | 当前用户可审批范围 |
| POST | `/procurement/approvals/{id}/approve` | comment / result | procurement_approver |
| POST | `/procurement/approvals/{id}/reject` | comment / result | procurement_approver |

#### 10. 核心实现步骤

1. 将模型纳入统一 Alembic。
2. 风险 high/critical 时创建一条 pending request。
3. 审批 API 校验同组织、角色、非本人和 pending 状态。
4. 批准后通过显式 continue 或 workflow block 继续。
5. 拒绝后将采购申请/任务标为 rejected。

#### 11. 测试方案

- low/medium 无审批，high/critical 单级审批。
- 发起人自批、错误角色和跨组织拒绝。
- 重复 approve/reject 不重复改变状态。
- 批准后可继续，拒绝后不能提交。

#### 12. 验收标准

演示流程能创建 pending 审批；审批页面可批准/拒绝；批准后继续提交；发起人无法审批自己。不要求多阶段、Redis 丢消息恢复或审批 SLA。

#### 13. 当前阶段总结文档

大纲：单级状态、路由、暂停/继续方式、职责分离和演示步骤。

#### 14. 代码清单文档

大纲：模型字段、迁移、routes、continue hook、测试和演示脚本。

#### 15. 风险与待办

- **简化：** 单级审批，不做 stage、decision history、Redis pub/sub、会签、委托和 SLA。
- **生产升级：** Outbox、SLA 升级、审批代理、电子签名。
- **依赖：** Day 7 通知审批人；Day 9/10 提供真正暂停恢复执行点。

### Day 7：企业微信与钉钉通知（A）

#### 1. 阶段目标

把审批、资质到期、订单异常和任务失败转换为可追踪通知，并复用现有企业微信/钉钉渠道。

#### 2. 原项目实现

- 分支：`origin/day-7/notification`；提交 `f5e4e99`。
- `enterprise/notification/channels.py`：企业微信和钉钉 HTTP 发送。
- `enterprise/notification/dispatcher.py`：渠道选择、重试和 fallback。
- 测试：`tests/unit/test_notification.py`。
- 当前没有通知 API、接收人目录、持久化表或主链调用方。

#### 3. 原设计解决的问题

审批等待和任务异常不能只显示在系统页面，需要外部触达；多个渠道要有统一消息结构和失败降级。

#### 4. 原设计方案

通过 `httpx` 调 webhook，dispatcher 顺序尝试渠道并记录结果，失败后重试或切换。

#### 5. 原设计的优点和限制

渠道 adapter 小而清晰，采购场景可直接复用。限制是 webhook 配置和接收人不具备租户模型；无持久化/重放/去重；业务服务没有调用 dispatcher；测试主要是 mock HTTP。

#### 6. 采购场景改造方案

直接复用现有 channel 和 dispatcher。审批、订单异常发生时调用一次 dispatcher；消息只含摘要和页面链接。首版不建通知中心。

#### 7. 建议目录结构

```text
enterprise/notification/
├── channels.py
├── dispatcher.py
└── templates.py
```

#### 8. 数据模型变化

不新增表。Webhook 通过环境变量配置，发送结果写审计日志。

#### 9. API 设计

本阶段不新增公开 API。

#### 10. 核心实现步骤

1. 复用 channel adapter。
2. 新增采购审批和订单异常两个模板。
3. 在 approval/order service 中直接调用 dispatcher。
4. 发送结果和失败原因写审计。
5. 对 webhook 和消息字段脱敏。

#### 11. 测试方案

- 正常 WeCom/DingTalk。
- 4xx/5xx、超时和 fallback。
- 一个渠道失败 fallback。
- 模板参数缺失。
- 敏感值不进入 payload/log。
- 外部超时不阻塞审批事务。

#### 12. 验收标准

创建 high 审批后 mock 渠道收到脱敏摘要；通知失败不影响审批记录和任务状态。

#### 13. 当前阶段总结文档

大纲：事件清单、渠道配置、模板示例、重试/去重、敏感数据策略、测试结果。

#### 14. 代码清单文档

大纲：复用 channel、模板、业务调用点、配置和测试。

#### 15. 风险与待办

- **简化：** 直接发送，不建 Notification、endpoint、recipient、outbox 或 worker。
- **生产升级：** 独立 worker、DLQ、签名轮换、消息合规归档。
- **依赖：** Day 6 提供审批事件；Day 8 记录发送审计；Day 10/16 展示订单异常。

### Day 8：采购审计、脱敏与 MinIO 文件存储（B）

#### 1. 阶段目标

复用现有审计、脱敏和 MinIO helper，记录采购关键动作与证据。

#### 2. 原项目实现

- 分支：`origin/day-8/audit-compliance`；提交 `72d5d8c`。
- `enterprise/audit/models.py:AuditLogModel`。
- sanitizer、`write_audit_log()`、MinIO storage helper、审计 route 和测试。
- 路由：`GET /enterprise/audit/logs`。
- 测试：`tests/unit/test_audit.py`。当前路由读取 `_audit_store`；模型无迁移，storage 无客户端装配。

#### 3. 原设计解决的问题

对金融自动化的用户、动作、风险、审批和截图进行留痕；敏感字段不直接出现在日志；大文件放对象存储。

#### 4. 原设计方案

审计表保存结构化事件和截图 URL；递归 sanitizer 替换敏感字段；MinIO helper 负责上传和预签名；写审计失败时记录 warning 并让主流程继续。

#### 5. 原设计的优点和限制

脱敏和对象存储抽象可复用。限制：

- 无迁移和运行时客户端，审计只是 demo list。
- 路由只要求登录，任何用户可能看到全局日志；`risk_level` 参数未实际过滤。
- 截图 URL 来自 demo 字段，不是实时 presign。
- fail-open 对某些高风险提交不够安全。

#### 6. 采购场景改造方案

保留 `AuditLogModel` 和现有字段，补充 `business_object_type/id`。在报价、风险、审批、提交和订单异常处调用现有 logger；截图和报价文件可使用 MinIO helper。

#### 7. 建议目录结构

```text
enterprise/audit/
├── models.py
├── sanitizer.py
├── routes.py
└── storage.py
```

#### 8. 数据模型变化

- 复用 `audit_logs`，增加可选 `business_object_type`、`business_object_id`。
- 文件沿用 Artifact/MinIO object key，不新增 evidence 表。

#### 9. API 设计

| 方法 | 路径 | 请求/响应 | 权限 |
| --- | --- | --- | --- |
| GET | `/procurement/audit/logs` | scoped filters/page | manager/viewer |

#### 10. 核心实现步骤

1. 把现有 AuditLog 模型纳入迁移。
2. 定义敏感字段分类和 sanitizer 测试。
3. 在报价、风险、审批、提交和订单异常处调用 logger。
4. 审计查询增加 organization/department 过滤。
5. 报价文件使用现有 Artifact 或 MinIO helper。

#### 11. 测试方案

- 正常写/查/过滤。
- 密码、Token、银行账户、报价敏感字段脱敏。
- 跨租户查询拒绝。
- MinIO 失败、非法 MIME、超限文件。
- 提交、审批和订单异常均有审计记录。

#### 12. 验收标准

报价、审批、提交和订单异常均产生审计；跨租户测试通过；日志和 LLM prompt 搜索不到测试密码/银行账户。

#### 13. 当前阶段总结文档

大纲：审计事件字典、调用点、脱敏分类、MinIO 生命周期、失败策略、权限与测试证据。

#### 14. 代码清单文档

大纲：表/迁移、sanitizer、storage client、service、hooks、route、测试和对象存储配置。

#### 15. 风险与待办

- **简化：** 复用 AuditLog 和 storage helper，不建 AuditEvent/Evidence、hash chain、WORM 或保留策略。
- **生产升级：** WORM、KMS、病毒扫描、保留/法律冻结、审计外送 SIEM。
- **依赖：** Day 9/10 所有执行路径写审计；Day 11 基于审计计算指标。

### Day 9：Planner、Executor、Coordinator、LLM 容错与人工接管（B）

#### 1. 阶段目标

保留原项目 Planner、Executor、Coordinator 的职责分工，将其改造成采购编排层，并接入 Skyvern 的真实 Task/Workflow、采购 Skill、审批暂停恢复和人工接管状态。

#### 2. 原项目实现

- 分支：`origin/day-9/llm-resilience`；提交 `8ce2c5e`，补充提交 `915e1e3`。
- `enterprise/llm/resilient_caller.py`、`model_router.py`、`task_states.py`、`human_intervention.py`。
- `enterprise/agent/planner.py:PlannerAgent`、`executor.py:ExecutorAgent`、`coordinator.py:AgentCoordinator`、schemas。
- 测试：`tests/unit/test_llm_resilience.py`、`test_agent.py`，覆盖容错、路由、状态、planner/executor/coordinator。

#### 3. 原设计解决的问题

复杂金融任务需要规划、分步执行、失败重试、模型降级和人在关键节点接管；直接一次 LLM 调用容易因 JSON 错误或页面异常失败。

#### 4. 原设计方案

Planner 输出结构化计划，Executor 逐步调用 handler，Coordinator 管理状态；resilient caller 解析/修复 JSON 并切换模型；human intervention 记录接管信息。

#### 5. 原设计的优点和限制

职责拆分和容错思想合理。但这些类没有运行时调用方或 DB 持久化；Executor 无 handler 时模拟成功；Planner 自己解析 JSON，没有统一使用 resilient caller；企业状态枚举没有映射核心 `TaskStatus`；“断点恢复”并未真正落库。

#### 6. 采购场景改造方案

保留并改造 `PlannerAgent`、`ExecutorAgent`、`AgentCoordinator`：Planner 只生成受工作流模板和 Skill 白名单约束的采购计划；Executor 只分发已注册的采购 Skill/handler，并通过 `SkyvernIntegrationService` 创建或继续原生 Task/Workflow；Coordinator 负责计划状态、步骤状态、审批暂停、恢复和人工接管。复用现有 resilient caller 做 JSON/schema 校验，页面失败时把任务标为 `needs_human` 或返回明确错误。

这里的采购 Executor 是企业级编排器，不负责重新实现 Skyvern 的页面理解、Action 生成和浏览器执行循环，因此不会与 `ForgeAgent` 形成两套浏览器执行引擎。

#### 7. 建议目录结构

```text
enterprise/agent/
├── planner.py                 # 保留类，替换为采购计划 schema/提示词
├── executor.py                # 保留类，只分发已注册 handler
├── coordinator.py             # 保留类，接入真实状态和暂停恢复
└── schemas.py                 # 增加采购任务类型和步骤输入输出
enterprise/procurement/agent/
├── handlers.py                # Skill 与 Skyvern task/workflow handler
└── state_mapper.py            # 企业编排状态到核心状态的映射
enterprise/procurement/integration/
└── skyvern_service.py
enterprise/llm/resilient_caller.py
```

保留现有 Executor 的编排职责，但删除或禁用“未注入 handler 仍模拟成功”的路径；浏览器执行继续复用 Skyvern 核心。

#### 8. 数据模型变化

演示版不新增独立 Agent 表。核心执行状态仍以 Skyvern Task/Workflow 为准；在 `ProcurementTaskExtension` 增加或复用 `plan_snapshot`、`current_step_index`、`orchestration_status`、`last_error` 等字段，保存最小恢复信息。生产版再考虑独立执行实例、版本、锁和事件表。

#### 9. API 设计

不新增面向前端的通用 Agent DSL API。报价采集、采购提交和订单跟踪接口调用 `AgentCoordinator`，由 Coordinator 驱动 Planner/Executor；响应中返回采购编排状态以及真实 Skyvern task/workflow ID。审批通过后的 continue 接口恢复同一编排实例。

#### 10. 核心实现步骤

1. 保留三个 Agent 类及现有 schema 契约，清理金融提示词、动作名和任务类型。
2. 为 Planner 增加采购计划 schema、模板约束、Skill 白名单和 resilient caller 校验。
3. 为 Executor 注册明确的采购 handler；缺失 handler 必须失败，不得模拟成功。
4. handler 通过 `SkyvernIntegrationService` 创建/继续原生 task/workflow，禁止直接实现第二套浏览器 action loop。
5. Coordinator 映射企业编排状态与核心状态，并把最小计划快照、当前步骤和错误写入 TaskExtension。
6. 接通风险暂停、ApprovalRequest、审批后 continue 和人工接管。
7. 采购 API 同时返回编排状态与真实 task/workflow ID。

#### 11. 测试方案

- 正常执行和状态读取。
- Planner 只能输出允许的采购步骤和 Skill；未知 Skill 拒绝执行。
- Executor 缺少 handler 时明确失败，不能返回模拟成功。
- Coordinator 在步骤成功、失败、等待审批和人工接管时正确映射核心状态。
- 审批暂停后可从已保存步骤继续，重复 continue 保持幂等。
- LLM 非 JSON、空结果和超时。
- 不允许模型看到凭据/敏感附件。
- 页面变化时任务明确失败或需要人工。
- 外部 LLM 全部失败时任务明确 failed/needs_human，不模拟成功。

#### 12. 验收标准

Planner、Executor、Coordinator 被真实采购 API 或工作流调用；至少一条报价采集流程可由 Coordinator 驱动并返回真实 Skyvern Task/Workflow ID；非法 LLM 输出和缺失 handler 不会被当作成功；审批暂停后可以幂等恢复。

#### 13. 当前阶段总结文档

大纲：采购 Agent 职责、真实调用链、状态映射、模型调用点、JSON 容错、审批暂停恢复、失败/人工状态和测试。

#### 14. 代码清单文档

大纲：保留并修改的 Planner/Executor/Coordinator、采购 schema、handler、state mapper、Skyvern integration、resilient caller 接入和测试。

#### 15. 风险与待办

- **简化：** 首版模板驱动，不让 LLM 自由发明采购流程。
- **生产升级：** 独立编排实例/事件表、并发锁、模型评测、prompt 版本治理、熔断与供应商配额。
- **依赖：** Day 10 提供真实采购 Skill handler；Day 13 才优化缓存/路由。

### Day 10：采购 Skill、报价标准化与工作流模板（C + D）

#### 1. 阶段目标

实现 7 个采购 Skill、报价标准化服务和 3 条可演示工作流；另外 3 个模板只保留元数据。

#### 2. 原项目实现

- 分支：`origin/day-10/financial-workflow-templates`；提交 `561a094`，补充 `15046d8`。
- `enterprise/skills/base.py`、registry、pipeline 及 7 个 Skill。
- `enterprise/workflows/templates.py` 的 6 个金融模板。
- `enterprise/workflows/routes.py` 的 list/detail/instantiate。
- `crypto.py`、validator；测试：`tests/unit/test_skills.py`、`test_workflows.py`。
- 路由：`GET /enterprise/workflows/templates`、`GET /templates/{id}`、`POST /instantiate/{id}`。

#### 3. 原设计解决的问题

把常见网页动作封装成可复用单元，并用参数化模板快速生成金融 RPA 任务。

#### 4. 原设计方案

Skill 直接接收浏览器 page 和可选 LLM handler；pipeline 顺序执行；模板存 Python 常量，实例化时校验/加密敏感参数并返回 task ID。

#### 5. 原设计的优点和限制

Skill 输入输出契约和模板目录值得保留。主要限制：

- Skill 未使用 Skyvern 原生 block/Task。
- Login/FormFill 把真实值写进 LLM prompt，违反敏感信息边界。
- pipeline 只有测试调用方。
- instantiate 不持久化、不创建核心任务、不执行；task ID 是伪造字符串。
- 密文只在局部变量中，未保存；`FINRPA_PARAM_KEY` 未出现在 `.env.example`。
- FileDownload 未接 Artifact/MinIO。

#### 6. 采购场景改造方案

通用网页 Skill 映射为原生 block 组合；标准化/比价作为确定性 Python 服务。模板以 Skyvern `WorkflowDefinition` 表示，并通过内部 `WorkflowService` 创建真实 run。敏感参数只传 credential/artifact ID。

#### 7. 建议目录结构

```text
enterprise/procurement/
├── skills/
│   ├── supplier.py
│   ├── quotation.py
│   ├── purchase_request.py
│   └── order.py
├── quotation/
│   ├── schemas.py
│   ├── normalize.py
│   └── compare.py
└── workflows/
    ├── templates.py
    └── service.py
```

#### 8. 数据模型变化

新增 Supplier、Material、Quotation、QuotationItem、PurchaseRequest、PurchaseOrder 和 ProcurementTaskExtension。Credential、Task、Workflow、Artifact、Approval 和 Audit 复用现有模型。

#### 9. API 设计

| 方法 | 路径 | 请求/响应 | 权限 |
| --- | --- | --- | --- |
| POST | `/procurement/quotations/collect` | collection request / instance | operator |
| POST | `/procurement/quotations/compare` | normalized IDs / comparison | operator/manager |
| POST | `/procurement/orders/{id}/track` | check request / snapshot | operator/system |

#### 10. 核心实现步骤

1. 先完成 Material、Supplier、Quotation 最小表。
2. 写纯函数 normalization + comparison 和测试。
3. 实现 7 个 Skill，通用表单/分页/下载直接调用原生 actions。
4. 制作两个模拟供应商站点 fixture。
5. 建 3 条演示模板；报价采集优先真实运行。
6. 将执行结果落 Quote/Artifact/Audit。
7. 另外 3 个模板只返回元数据，不实现运行逻辑。

#### 11. 测试方案

- 含税/未税、包装、MOQ 和运费的正常标准化。
- Decimal 舍入、零/负价格、无税率、未知单位。
- LLM extraction 非法 schema/提示注入。
- 某供应商失败仍返回部分结果。
- 凭据不出现在 prompt/log。
- 跨租户 supplier/material 拒绝。
- 同采集请求幂等。
- 模板真正产生 core WorkflowRun/Task/Artifact。

#### 12. 验收标准

至少第一条报价采集与比价通过真实浏览器任务端到端运行；两个供应商数据标准化可比；失败供应商有明确状态；密码不进入 LLM；API 返回真实 task/workflow IDs。

#### 13. 当前阶段总结文档

大纲：Skill 清单、原生 block 映射、报价 schema/算法、6 模板、第一条 E2E 证据、敏感数据检查。

#### 14. 代码清单文档

大纲：模型/迁移、7 Skill、3 个实现模板、3 个说明模板、服务/API、模拟站点和测试。

#### 15. 风险与待办

- **简化：** 只支持 2～3 个受控站点和有限单位字典。
- **生产升级：** 站点版本适配、MDM、文档 OCR、供应商 API 优先。
- **依赖：** Day 5 风险、Day 6 审批、Day 8 证据、Day 9 采购 Agent 编排与 Skyvern 集成均需先接通。

### Day 11：采购运营 Dashboard API（B）

#### 1. 阶段目标

从 PostgreSQL 中的真实采购、任务、审批和审计数据计算运营指标，不再依赖 demo 内存 store。

#### 2. 原项目实现

- 分支：`origin/day-11/dashboard-api`；提交 `878bc23`。
- `enterprise/dashboard/stats.py`、`cache.py`、`routes.py`；测试：`tests/unit/test_dashboard.py`。
- 路由：overview、trend、errors、business-lines、approval-time、cost、export。
- `demo_seed.py` 注入 task/approval/model-call store；Redis client 在正常启动中没有传入 dashboard route。

#### 3. 原设计解决的问题

让管理者查看任务成功率、错误、业务线分布、审批时长和 LLM 成本，并导出报告。

#### 4. 原设计方案

对传入的内存对象做聚合，可选 Redis 缓存，FastAPI 返回 Dashboard schema。

#### 5. 原设计的优点和限制

指标分组和响应结构可复用，纯函数易测。但实际应用数据来自 deterministic demo seed，不是数据库；缓存未装配；聚合的“业务线”不等于采购品类；跨租户安全取决于传入 store。

#### 6. 采购场景改造方案

复用现有 stats 结构，只提供一个 overview：任务总数/成功率、报价数量、待审批数量、异常订单数量和估算节省。首版允许使用数据库种子或 demo store。

#### 7. 建议目录结构

```text
enterprise/procurement/dashboard/
├── schemas.py
└── routes.py
```

#### 8. 数据模型变化

不新增表。指标直接从现有采购表或 `demo_seed` 聚合。

#### 9. API 设计

| 方法 | 路径 | 请求/响应 | 权限 |
| --- | --- | --- | --- |
| GET | `/procurement/dashboard/overview` | filters / `DashboardOverview` | manager/viewer |

#### 10. 核心实现步骤

1. 定义指标公式和空数据行为。
2. 复用现有 stats 纯函数，把业务线改成采购品类。
3. 从数据库或 demo store 读取。
4. 使用固定种子验算 5 个指标。

#### 11. 测试方案

- 正常聚合和无数据。
- 跨组织/部门/品类隔离。
- 重复刷新无副作用。

#### 12. 验收标准

Dashboard 显示 5 个采购指标，数值可由固定种子复算，不同组织看不到彼此数据。

#### 13. 当前阶段总结文档

大纲：5 个指标、数据来源、权限范围、验算数据和页面截图。

#### 14. 代码清单文档

大纲：schema、stats、route、测试和前端字段合同。

#### 15. 风险与待办

- **简化：** 一个 overview API，不做趋势、供应商排行、导出、Redis 缓存或数仓。
- **生产升级：** 大数据量后增加汇总表或数仓。
- **依赖：** Day 16 提供可信演示数据；Day 12 消费接口。

### Day 12：企业采购前端页面（B）

#### 1. 阶段目标

把现有企业 UI 外壳转换为采购运营、供应商、报价、申请、审批、订单、审计页面，并明确真实接口与演示 fallback 的边界。

#### 2. 原项目实现

- 分支：`origin/day-12/ui-redesign`；提交 `c8f1487`。
- `skyvern-frontend/src/router.tsx`、企业布局、组件、样式和页面。
- 页面包括 Dashboard、Approvals、Audit、Permissions、LLMMonitor。
- 企业前端测试：`src/__tests__/GlassCard.test.tsx`、`Icon.test.tsx`、`RiskBadge.test.tsx`、`ScreenshotDiff.test.tsx`、`StatusBadge.test.tsx`、`Timeline.test.tsx`；日志称 37 个用例，当前未安装 node_modules，未复跑。

#### 3. 原设计解决的问题

将 Skyvern 技术界面包装成企业管理控制台，展示权限、审批、审计、成本和运营指标。

#### 4. 原设计方案

React Router + AuthGuard，统一企业 Layout；页面调用 `/api/v1/enterprise/*`，失败时部分页面展示 demo 数据。

#### 5. 原设计的优点和限制

布局、导航、表格、状态标签可复用。限制是 Permissions 完全硬编码；Dashboard recent tasks 和 LLM stuck tasks 有 demo；Token guard 仅检查 localStorage 是否有字符串；没有采购实体页面、scope selector 和敏感导出确认。

#### 6. 采购场景改造方案

保留 Layout/主题和通用组件，只做 Dashboard、报价/比价、采购申请/审批、订单跟踪、审计 5 个页面。供应商和物料使用简单下拉，不单独建设管理后台。

#### 7. 建议目录结构

```text
skyvern-frontend/src/enterprise/
├── procurement/
│   ├── quotations/
│   ├── requests/
│   └── orders/
├── approvals/
├── audit/
├── dashboard/
└── api/
```

#### 8. 数据模型变化

手写最小 TypeScript 类型：Quotation、Comparison、PurchaseRequest、Approval、PurchaseOrder、DashboardOverview。金额用字符串传输，首版不引入代码生成。

#### 9. API 设计

前端消费 Day 2～11 API；新增：

| 方法 | 路径 | 用途 | 权限 |
| --- | --- | --- | --- |
| GET | `/procurement/context-options` | 当前用户可选部门/品类 | 登录用户 |
| GET | `/procurement/comparisons/{id}` | 比价详情 | scoped |
| GET | `/procurement/purchase-requests/{id}` | 申请与审批状态 | scoped |
| GET | `/procurement/orders/{id}` | 当前订单状态 | scoped |

#### 10. 核心实现步骤

1. 建统一 API client、401 处理、错误结构。
2. 实现部门/品类 selector。
3. 做报价采集向导和 run 状态。
4. 做标准化比价表和证据链接。
5. 做申请、风险和审批状态。
6. 做订单异常和审计页。
7. 保留明确标记的 demo fallback。

#### 11. 测试方案

- 页面正常加载、空状态、loading/error。
- 401/403/422/409 显示正确。
- viewer 不显示执行按钮；审批人不能批自己请求。
- 金额/币种/税口径显示准确。
- API 错误有简单错误提示。
- 双击提交通过 idempotency key。
- 可访问性：键盘、label、焦点、颜色对比。

#### 12. 验收标准

三条核心演示流程可从 UI 发起或查看；按钮按角色显示且后端再次校验；敏感字段默认遮罩。Permissions 页面可继续使用 demo 数据并明确标记。

#### 13. 当前阶段总结文档

大纲：信息架构、页面/API 映射、角色视图、状态/错误设计、演示截图、测试结果。

#### 14. 代码清单文档

大纲：路由、页面、组件、API client、types、i18n keys、测试；标识复用与重写。

#### 15. 风险与待办

- **简化：** 不建设低代码拖拽工作流编辑器，使用后端模板。
- **生产升级：** 设计系统、可访问性审计、批量操作和高级检索。
- **依赖：** Day 15 处理认证/i18n/接口合同；Day 16 完成字段和演示数据。

### Day 13：Action Cache 与模型路由（A）

#### 1. 阶段目标

保留并展示现有 Action Cache 与模型路由，不要求为采购重写缓存平台。

#### 2. 原项目实现

- 分支：`origin/day-13/performance-optimization`；提交 `dd7875b`。
- `enterprise/llm/action_cache.py`、`enterprise/llm/cache_routes.py` 的 action cache、统计、路由与测试。
- 路由：stats，删除 task、expired、all，reset-stats。
- `enterprise/llm/model_router.py` 有独立特征路由；测试：`tests/unit/test_action_cache.py` 和 `test_llm_resilience.py`。
- 当前 cache 使用内存，不被 `ForgeAgent` 调用。

#### 3. 原设计解决的问题

相似网页动作复用可减少 LLM 次数、延迟和成本；简单页面用较便宜模型，复杂页面升级模型。

#### 4. 原设计方案

以内存字典保存 action 决策和 hit/miss；管理 API 清除缓存；模型 router 根据 PageFeatures 返回模型。

#### 5. 原设计的优点和限制

缓存键、TTL、统计概念可保留。但实际执行链没有 get/set；`DELETE /task/{id}` 忽略 task ID 并清整个组织前缀，`/all`、`/expired`、stats 是全局范围；没有 Redis 装配。模型路由同样无核心 caller。README 的性能收益没有运行时证据。

#### 6. 采购场景改造方案

沿用 `enterprise/llm/action_cache.py` 和 `model_router.py` 作为“性能优化意识”的演示模块。采购主流程不依赖缓存；只补充规则，确保登录、表单值、采购提交和敏感上传不进入缓存。

#### 7. 建议目录结构

```text
enterprise/llm/
├── action_cache.py
├── cache_routes.py
└── model_router.py
```

#### 8. 数据模型变化

不新增模型或 Redis 集成。继续使用现有内存 store。

#### 9. API 设计

不新增采购 API；继续保留现有 `/enterprise/cache/*` 演示接口。

#### 10. 核心实现步骤

1. 复用现有 action cache 和测试。
2. 增加敏感动作 bypass 测试。
3. 在文档中说明它没有接入 ForgeAgent，不能宣称真实提速。
4. 可选在报价标准化纯函数前加简单内容哈希缓存；没有性能问题则跳过。

#### 11. 测试方案

- 现有 hit/miss/TTL。
- 敏感动作始终 bypass。
- 敏感值不会出现在缓存内容。

#### 12. 验收标准

现有缓存测试通过，敏感动作明确 bypass；文档和页面将其标记为演示能力，不要求证明真实任务性能提升。

#### 13. 当前阶段总结文档

大纲：现有实现、允许/禁止缓存清单、未接主链的限制和测试。

#### 14. 代码清单文档

大纲：复用的 action_cache/cache_routes/model_router 和新增测试。

#### 15. 风险与待办

- **简化：** 不接 Redis、不做采购缓存 API、不接核心 hook；Day 13 可只做测试和文档。
- **生产升级：** 分布式一致性、缓存投毒防御、自动回归验证。
- **依赖：** 不阻塞 Day 14；主流程可完全绕过缓存。

### Day 14：Docker 部署、集成测试与端到端验收（B）

#### 1. 阶段目标

建立可重复的单机演示部署；报价主流程穿过 HTTP、数据库、浏览器和 Skyvern 核心，另外两条流程完成受控场景验收。

#### 2. 原项目实现

- 分支：`origin/day-14/production-ready`；提交 `2f25993`。
- `docker-compose.prod.yml`、Nginx 配置、Dockerfile、部署说明。
- `tests/integration/test_e2e_flow.py` 共 40 个测试；Day 14 没有浏览器级测试文件。
- 当前 E2E 直接调用纯函数和内存 fixture；`TestPhase10FullE2EScenario` 是顺序断言，不用 FastAPI TestClient、真实 DB/Redis、浏览器或 Skyvern action。

#### 3. 原设计解决的问题

把开发阶段模块组合成可部署栈，并用集成测试验证认证、权限、风险、审批、通知、审计和 Dashboard。

#### 4. 原设计方案

Docker Compose 启动多服务，Nginx 反向代理；pytest 测试按阶段模拟完整生命周期。

#### 5. 原设计的优点和限制

覆盖业务场景的测试清单很完整，但“E2E”命名高于实际层级。部署还有 latest 镜像、运行时 pip install、TLS 注释、Nginx upstream/端口不一致、生产 DB 变量默认问题。服务依赖没有实际验证 MinIO 审计链。

#### 6. 采购场景改造方案

保留 Compose 单机演示。新增两个本地模拟供应商站点和一个模拟采购门户；真实 E2E 通过 HTTP 启动报价工作流，等待核心任务，检查 DB/Artifact/比价，再走审批恢复。外网、验证码和反爬不在验收范围。

#### 7. 建议目录结构

```text
deploy/
├── compose.yml
├── nginx.conf
└── README.md
tests/
├── integration/
│   ├── test_api_db_flow.py
│   └── test_approval_resume.py
├── e2e/
│   ├── test_quotation_comparison.py
│   ├── test_purchase_request_approval.py
│   └── test_order_tracking.py
└── fixtures/sites/
```

#### 8. 数据模型变化

不新增表。采购申请本身保存 `idempotency_key`。

#### 9. API 设计

不新增业务 API。复用 Skyvern 现有 heartbeat/health；无需再建设完整运维 API。

| 方法 | 路径 | 响应 | 权限 |
| --- | --- | --- | --- |
| GET | `/api/v1/heartbeat` | process alive | 匿名 |

#### 10. 核心实现步骤

1. 修正端口、Nginx upstream 和环境变量名。
2. 用现有 Compose 启动 API、UI、DB、Redis、MinIO。
3. 启动两个模拟供应商和一个模拟采购门户。
4. 保留现有 integration test，并增加三条采购场景测试。
5. 至少报价采集使用真实浏览器；申请和订单流程可使用受控模拟门户。

#### 11. 测试方案

- 正常三条核心 E2E。
- 401/403/422/409。
- 跨租户数据隔离。
- LLM 非法输出/超时。
- 单供应商失败和 MinIO 失败。
- 重复点击/网络重试不重复提交。
- 凭据、Token、银行账户日志扫描。
- 页面字段变化有明确失败。

#### 12. 验收标准

一条命令启动演示栈；报价采集/比价使用真实 Skyvern 浏览器任务；采购申请能暂停、审批和继续；订单跟踪能检测异常；不要求 HA、恢复演练或完整 CI 制品链。

#### 13. 当前阶段总结文档

大纲：部署拓扑、固定版本、环境变量、测试分层、三条 E2E 结果、故障注入、已知非生产项。

#### 14. 代码清单文档

大纲：Compose/Docker/Nginx、fixture sites、integration/E2E 和验证命令。

#### 15. 风险与待办

- **简化：** 单机 Compose，无 HA、Kubernetes 和复杂容灾。
- **生产升级：** 多副本会话协调、备份恢复、SLO、漏洞扫描。
- **依赖：** Day 1～13 主链必须真实接通；Day 15 修合同，Day 16 做演示封板。

### Day 15：前后端集成、认证桥接、国际化与 LLM 监控（B）

#### 1. 阶段目标

消除前后端字段漂移和认证绕过，完成简单 API client、中文/英文界面和演示级 LLM 监控。

#### 2. 原项目实现

- 分支：`origin/day-15/enterprise-frontend-integration`；提交 `59a9926`。
- `enterprise/auth/bridge.py`，前端 AuthGuard/API 集成/i18n/LLM monitor。
- `tests/sit_test.py` 通过 `urllib` 请求运行中的 `localhost:18000`；它是独立脚本，不是前述纯函数 E2E 的替代品。
- `scripts/ensure_enterprise_schema.py`、`entrypoint-skyvern.sh`。
- 日志称 23 个接口；主分支静态路由装饰器实际 24 个。

#### 3. 原设计解决的问题

让企业 JWT 能访问 Skyvern、前端统一认证、补国际化和模型成本页面，并在部署时确保企业表存在。

#### 4. 原设计方案

bridge 将 enterprise Token 映射 Organization；前端存 localStorage；i18n key 包装页面；LLM monitor 读取 Dashboard/cache；启动脚本在 Alembic 后再执行 `ensure_enterprise_schema.py`。

#### 5. 原设计的优点和限制

认证桥和统一页面是有效集成点，SIT 也比纯函数测试更接近真实服务。限制：

- bridge 丢失细粒度权限。
- localStorage guard 不检查过期/刷新。
- 运行时建表脚本与 Alembic 双真源，只创建 auth 表，不创建 approval/audit。
- LLM monitor 的部分 stuck-task 数据仍是 demo。
- 本次没有启动栈，SIT 通过声明需要进一步验证。

#### 6. 采购场景改造方案

沿用手写 `authFetch` 和 TypeScript 类型，统一常用字段和错误处理。采购写动作经采购 API；i18n 覆盖核心采购页面。LLM Monitor 可继续使用 demo 指标，但必须标记数据来源。

#### 7. 建议目录结构

```text
skyvern-frontend/src/enterprise/
├── api.ts
├── auth/
└── i18n/
```

#### 8. 数据模型变化

不新增表。金额统一以字符串传输，状态枚举前后端对齐。

#### 9. API 设计

核对全部采购 API，不新增 capabilities、LLM metrics 或 errors API。

#### 10. 核心实现步骤

1. 删除运行时建表双真源，统一 Alembic。
2. 统一 auth header、401 和 idempotency key。
3. 手工对齐核心 TypeScript 类型。
4. 补中英文字段和风险文案。
5. LLM Monitor 标记 demo/真实来源。
6. SIT 覆盖核心路由。

#### 11. 测试方案

- login/401。
- 中英文切换、缺 key fallback。
- 金额不丢精度、枚举未知值。
- Dashboard/LLM demo 指标显示来源。
- 重复提交 header 幂等。
- 浏览器端不记录 Token/敏感 payload。

#### 12. 验收标准

核心字段前后端一致；401 能退出登录；采购写请求无法通过 bridge 绕过；迁移只有 Alembic 一条路径；demo 指标有明显标记。

#### 13. 当前阶段总结文档

大纲：字段合同、认证边界、i18n、demo 指标来源、SIT 路由表和已修复漂移。

#### 14. 代码清单文档

大纲：后端 schema、手写 API client、auth、i18n、SIT 和删除的双建表路径。

#### 15. 风险与待办

- **简化：** 中英文两种语言；不做复杂本地化工作流编辑器。
- **生产升级：** 企业 IdP、审计级 API versioning、区域数据驻留。
- **依赖：** Day 14 可运行环境；Day 16 最终字段和 demo 验收。

### Day 16：采购演示数据、字段对齐、Dashboard 与流程封板（B + D）

#### 1. 阶段目标

提供可重复、能支撑三条核心演示流程的采购数据；完成字段对齐、Dashboard 验算、演示脚本和限制声明。

#### 2. 原项目实现

- 分支：`origin/day-16/demo-data-integration`；提交 `61e97a5`。
- `enterprise/demo_seed.py` 使用固定随机种子 42，生成约 250 tasks、58 approvals（10 pending）、约 950 audit、1200 model calls、25 cache entries。
- 前后端字段对齐和 Dashboard 页面完善；沿用既有 unit/integration/SIT，没有新增采购领域测试。
- 数据通过 `create_api_app()` 启动时同步填内存 store，不是数据库 seed。

#### 3. 原设计解决的问题

在没有真实生产数据时保证页面有稳定内容，便于录屏、演示和前端联调；修复 Day 12～15 的字段差异。

#### 4. 原设计方案

确定性随机数据 + 内存注入；页面 fallback；按固定数字展示趋势和运营效果。

#### 5. 原设计的优点和限制

固定随机种子便于可重复演示，字段对齐很实用。但数据没有采购实体关系、服务重启即重建、与核心 Task/Workflow 无关联；启动函数同步副作用不适合多 worker；Dashboard 指标不是实际流程结果。

#### 6. 采购场景改造方案

沿用固定随机种子和内存 store，增加采购演示数据。准备两个场景：

- “工业交换机询比价 + 高金额审批 + 提交”
- “订单延期/缺货/价格变化跟踪”

模拟站点数据与 store/采购表字段对应。seed 只在 `DEMO_MODE=true` 时运行。

#### 7. 建议目录结构

```text
enterprise/procurement/demo/
├── seed.py
├── scenarios.py
└── README.md
tests/e2e/fixtures/
├── suppliers/
└── procurement_portal/
docs/demo/
└── walkthrough.md
```

#### 8. 数据模型变化

不新增领域类型；补充一组织、两部门、5 角色、3 品类、2 供应商、3 物料、报价、采购申请、订单、审批和审计。秘密使用测试 Credential。

#### 9. API 设计

不新增 demo API；通过 `DEMO_MODE` 和 seed 脚本控制。

#### 10. 核心实现步骤

1. 定义两个固定场景和预期指标。
2. 复用 `demo_seed.py` 模式生成固定数据。
3. 配置模拟站点与测试凭据。
4. 跑三条 E2E 并保存 Artifact。
5. 用固定期望值验算 Dashboard。
6. 完成 8～12 分钟演示脚本、失败演示和限制说明。
7. 所有 demo fallback 显示“演示数据”标记。

#### 11. 测试方案

- seed 正常、重复执行结果稳定。
- 跨组织无污染。
- 三条 E2E 正常与供应商失败。
- high/critical 审批、LLM 非法输出。
- Dashboard 指标与预期一致。
- 重复提交/轮询不重复 PR/通知。
- 秘密扫描和审计脱敏。

#### 12. 验收标准

启用 DEMO_MODE 后可按 walkthrough 完成报价、审批和订单跟踪；Dashboard 数值固定可验证；文档明确内存数据、模拟站点和未接主链能力。

#### 13. 当前阶段总结文档

大纲：场景故事、账号/角色、数据关系、三条演示步骤、预期指标、录屏截图、限制与下一步。

#### 14. 代码清单文档

大纲：seed/scenario/reset、fixture sites、demo config、E2E、walkthrough、Dashboard 验算 SQL 和前端字段改动。

#### 15. 风险与待办

- **简化：** 模拟供应商与采购门户，不处理验证码、反爬或真实付款。
- **生产升级：** ERP/SRM 连接器、真实主数据迁移、站点合规和运营支持。
- **依赖：** 依赖前 15 天所有 P0 主链；这是封板阶段，不应掩盖未接通模块。

---

## 13. 逐阶段迁移判定总表

| Day | 分类 | 可直接复用 | 改字段/语义 | 必须重写/不适用 | 采购版本核心产出 | 前后依赖 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | A | Skyvern、单仓、Compose 思路 | 品牌/配置 | 动态镜像和不一致端口 | 可重复采购基线 | 无 → Day 2 |
| 2 | B | Organization、Department、共享 Base | BusinessLine→Category、5 角色改名 | 迁移链、无 FK context | 品类和任务扩展 | Day 1 → 3/4/5/6 |
| 3 | B | JWT dependency、bridge 思路 | 采购角色依赖 | 弱密钥和原生写接口绕过 | 简单采购授权 | Day 2 → 4/15 |
| 4 | B | ContextVar、过滤 helper | 业务线→品类 | 未注册自动 filter、visibility 漏组织 | 显式组织/部门/品类过滤 | Day 3 → 全后续 |
| 5 | C | 规则+LLM 两阶段思路 | 等级枚举 | 金融关键词、LLM 可降级、硬编码路由 | 采购确定性规则 | Day 2/4 → 6/10 |
| 6 | C | ApprovalRequest 和路由 | 审批对象 | 内存路由与主链未接 | 单级审批和 continue | Day 5 → 7/9/10 |
| 7 | A | WeCom/DingTalk adapter | 两个消息模板 | 无调用方 | 直接 dispatcher 调用 | Day 6 → 8/16 |
| 8 | B | AuditLog、sanitizer、MinIO helper | 金融审计字段 | 内存 route、越权查询 | 简单采购审计 | Day 4 → 9/10/11 |
| 9 | B | Planner/Executor/Coordinator、Agent schema、resilient caller | 金融计划和动作改为采购 Skill | 内存状态、模拟成功、缺少真实调用方 | 可持久恢复的采购编排层并接入 Skyvern | Day 6/8 → 10 |
| 10 | C+D | Skill 契约、模板元数据 | 金融模板名 | 泄密 prompt、伪 task ID | 7 Skill、3 实现模板、标准化 | Day 5/6/9 → 11/12 |
| 11 | B | KPI schema/纯聚合思路 | 业务线指标 | 内存数据需标记 | 单一 Dashboard overview | Day 10 → 12/16 |
| 12 | B | Layout、表格、状态组件 | 页面领域 | 硬编码权限、demo fallback | P0 采购页面 | Day 11 → 15/16 |
| 13 | A | 现有 TTL/key/统计 | 敏感动作 bypass | 无 caller，不能宣称提速 | 演示级缓存说明与测试 | Day 10 → 14 |
| 14 | B | Compose/测试场景清单 | 服务/场景 | “纯函数 E2E”、部署漂移 | 真实浏览器 E2E | Day 1～13 → 15 |
| 15 | B | authFetch/i18n/SIT | 金融文案和字段 | auth bridge 越权、双建表真源 | 手写合同、401、i18n | Day 14 → 16 |
| 16 | B+D | 固定随机种子和内存 store | 金融 demo 字段 | 未接主链需明确标记 | 采购 demo 数据和 walkthrough | Day 1～15 |

建议顺序只做一处小调整：Day 10 的“报价标准化纯函数和最小数据模型”可在 Day 5 前先定义 schema，便于价格偏离规则使用统一口径；但可执行 Skill/工作流仍留在 Day 10。这样保持原路线，同时避免风险引擎依赖尚未定义的报价字段。

---

## 14. 推荐目标目录

```text
finrpa-enterprise/
├── skyvern/                         # [本轮复用] 核心浏览器 Agent
├── skyvern-frontend/
│   └── src/enterprise/
│       ├── auth/
│       ├── procurement/
│       │   ├── quotations/
│       │   ├── requests/
│       │   └── orders/
│       ├── approvals/
│       ├── audit/
│       ├── dashboard/
│       └── i18n/
├── enterprise/
│   ├── auth/                        # 复用企业认证
│   ├── tenant/                      # 复用租户上下文
│   ├── procurement/
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── routes.py
│   │   ├── risk/
│   │   ├── skills/
│   │   ├── workflows/
│   │   ├── dashboard.py
│   │   └── demo/
│   ├── approval/                    # 复用并改采购字段
│   ├── audit/
│   ├── notification/
│   ├── llm/
│   └── integrations/
│       └── skyvern.py
├── alembic/
│   └── versions/                    # 单一迁移链
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── fixtures/sites/
├── docs/
│   └── demo/
└── scripts/
```

不建议建立独立 `planner-service`、`approval-service`、`supplier-service` 等微服务。原型阶段同进程事务、统一迁移和直接函数调用更可靠，也更符合现有仓库规模。

---

## 15. 采购平台主要 API 清单

统一前缀：`/api/v1/enterprise`。只有采购提交和工作流启动必须携带 `Idempotency-Key`；金额使用十进制字符串。

### 15.1 本轮实现的核心 API

| 方法 | 路径 | 请求模型 | 响应模型 | 权限 |
| --- | --- | --- | --- | --- |
| POST | `/auth/login` | `LoginRequest` | `LoginResponse` | 匿名 |
| GET | `/auth/me` | — | `CurrentUserResponse` | 登录用户 |
| GET | `/procurement/context-options` | — | `ContextOptionsResponse` | 登录用户 |
| GET | `/procurement/suppliers` | filters | `SupplierList` | 范围内读取 |
| GET | `/procurement/materials` | filters | `MaterialList` | 范围内读取 |
| POST | `/procurement/quotations/collect` | `QuotationCollectionCreate` | task/workflow ID | operator |
| GET | `/procurement/quotations` | filters | `QuotationList` | 范围内读取 |
| POST | `/procurement/quotations/compare` | `ComparisonCreate` | `ComparisonResponse` | operator/manager |
| POST | `/procurement/purchase-requests` | `PurchaseRequestCreate` | `PurchaseRequestResponse` | operator |
| GET | `/procurement/purchase-requests/{id}` | — | `PurchaseRequestDetail` | 范围内读取 |
| POST | `/procurement/purchase-requests/{id}/submit` | `SubmitRequest` | task/approval/result | operator |
| GET | `/procurement/approvals/pending` | filters | `ApprovalList` | approver |
| POST | `/procurement/approvals/{id}/approve` | comment | `ApprovalResponse` | approver、非发起人 |
| POST | `/procurement/approvals/{id}/reject` | comment | `ApprovalResponse` | approver、非发起人 |
| GET | `/procurement/orders` | filters | `PurchaseOrderList` | 范围内读取 |
| POST | `/procurement/orders/{id}/track` | `TrackingRequest` | current status | operator |
| GET | `/procurement/audit/logs` | filters | `AuditLogList` | manager/viewer |
| GET | `/procurement/dashboard/overview` | filters | `DashboardOverview` | manager/viewer |

### 15.2 仅设计说明、不在本轮实现

- 角色、金额权限和规则管理 CRUD。
- 独立供应商资质、银行账户变更、通知中心、Evidence 和人工接管 API。
- Dashboard 趋势、导出、缓存管理和 LLM Metrics API。
- Refresh Token、capabilities、项目管理和复杂审批 API。

---

## 16. 测试矩阵

| 层级 | 主要对象 | 必测内容 | 真实依赖 |
| --- | --- | --- | --- |
| 单元测试 | 权限、5 类风险、标准化、比价、审批、脱敏 | 正常、边界、非法输入、LLM schema 错误 | 无 |
| 模型/迁移测试 | 最小采购模型和 Alembic | FK、唯一键、Decimal、upgrade | PostgreSQL |
| API 集成 | auth、scope、supplier、quote、PR、approval、order、audit | 2xx/401/403/404/409/422、幂等、多租户 | FastAPI + PostgreSQL |
| 浏览器/场景 E2E | 三条核心工作流 | 报价真实浏览器；申请审批和订单使用模拟门户 | 演示栈 + 模拟站点 |
| 安全测试 | 认证、授权、秘密、上传、审计 | IDOR、跨租户、Token、prompt 泄密、MIME、日志扫描 | 全栈 |

### 16.1 三条必须通过的 E2E

1. **报价采集与比价：** HTTP 创建 → 两个模拟站点的真实浏览器任务 → 标准化 → 比价。
2. **申请与审批：** 模拟采购门户填草稿 → high 风险 → pending → UI 批准 → continue → 回执。
3. **订单跟踪：** 手动触发 → 模拟供应商提取状态 → 差异 → 异常通知。

### 16.2 安全断言

- 测试凭据、完整 Token、银行账户和敏感附件正文不出现在 LLM request、应用日志、审计 payload 和缓存。
- 任意资源 ID 被另一组织用户请求均返回 404 或 403，且响应不泄露对象存在性。
- 发起人不能审批自己；viewer 不能借原生 Skyvern API 启动提交。
- 上传限制 MIME、大小、扩展名和目标域；不处理验证码或绕过站点保护。

---

## 17. 开发优先级

### P0：必须完成，影响主流程

- 统一 Alembic 和最小采购表。
- JWT 基础安全、组织/部门/品类/角色校验和原生路由绕过封口。
- Material、Supplier、Quotation、PR、Approval、PO 最小模型。
- 报价标准化与比价确定性服务。
- 两个模拟供应商站点 + 一个模拟采购门户。
- 第一条报价采集 E2E。
- 5 类风险、单级审批和显式 continue。
- AuditLog、Artifact/MinIO helper 和秘密不进 LLM。
- 订单跟踪、5 个采购页面和演示 Dashboard。

### P1：增强企业级能力

- 企业微信/钉钉直接通知。
- 供应商准入模板和资质文件采集。
- 定时订单跟踪。
- 中英文和更多演示数据。

### P2：展示和性能优化

- 更丰富 Dashboard、导出和节省分析。
- 第三个及更多供应商适配器。
- 页面定位回归、缓存调优、并行采集。
- 演示录屏、架构图、性能报告。
- 独立财务/合规角色、多级审批、权限/规则管理、Outbox、汇总表。

明确不在原型范围：微服务拆分、Kafka、Kubernetes、HA、多区域容灾、绕验证码/反爬、真实付款执行、大规模并发。

---

## 18. 可行性评估

评分均为 10 分制；“开发难度”分数越高表示越难，其余越高越有利。

| 维度 | 评分 | 原因 |
| --- | ---: | --- |
| Skyvern 适配性 | 8/10 | 核心浏览器 Task/Workflow/Artifact/Credential 齐全，采购门户天然适合浏览器自动化；页面变化和会话恢复仍有成本 |
| 代码复用率 | 7.5/10 | 复用现有 5 角色、JWT、通知、审计、Dashboard、缓存外壳和 Skyvern 核心；整体约 50%～60% |
| 后端开发难度 | 5.5/10 | 只做最小采购表、5 类风险和单级审批，不建设权限/规则平台 |
| 前端开发难度 | 5/10 | 复用布局和组件，只新增 5 个采购页面 |
| Agent 开发难度 | 7/10 | 保留三类 Agent 可减少架构重建，但必须补齐真实 handler、状态映射和暂停恢复；浏览器稳定性仍由 Skyvern 集成承担 |
| 采购业务开发难度 | 5.5/10 | 首版只支持 CNY、固定单位字典和模拟供应商 |
| 演示可行性 | 9/10 | 受控模拟供应商和采购门户可稳定展示真实浏览器主链 |
| 简历含金量 | 9/10 | 能展示 Agent、RPA、FastAPI、RBAC、审批、审计、数据建模、React 和 E2E；前提是诚实说明演示边界 |

### 18.1 人力估算

一人借助 Codex 可以完成“企业级项目原型”，条件是：

- 使用模拟供应商/采购系统。
- 先做 P0，避免同时适配多个真实站点。
- 每个 Day 留下可运行验收，不用测试数量代替主链证据。
- 不承诺生产高可用和大型企业全部采购规则。

以兼职节奏看，16 个 Day 更像 16 个里程碑而不是 16 个自然日；浏览器 E2E、审批恢复和数据口径通常需要额外迭代。

---

## 19. 最终实施建议

### 19.1 是否适合按原项目路线开发

适合按相同里程碑顺序开发，但不适合照抄实现。Day 1～4 建地基，Day 5～10 打企业主链，Day 11～16 完成展示与验收，这个节奏合理。

### 19.2 可直接参考的阶段

- Day 1 的 Skyvern 基线和模块化单体。
- Day 3 的 FastAPI dependency/JWT 接入形式，但需修授权边界。
- Day 7 的企业微信/钉钉 channel adapter。
- Day 8 的 sanitizer/MinIO helper 思路。
- Day 11 的指标响应结构。
- Day 12 的企业 UI Layout 和通用组件。
- Day 14 的单机 Compose 方向和场景清单。

### 19.3 需要重点重写的阶段

- Day 4：采购任务、报价、申请和订单必须显式按组织/部门/品类过滤。
- Day 5：金融风险规则全面转为采购确定性规则。
- Day 6：复用 ApprovalRequest，增加单级审批和显式 continue。
- Day 9：保留并采购化 Planner/Executor/Coordinator，补真实 handler、状态映射和暂停恢复；底层浏览器执行仍复用 Skyvern。
- Day 10：Skill/模板变为原生 block，解决敏感信息进入 LLM。
- Day 13：保留缓存/模型路由作为演示能力，明确没有接主链。
- Day 15：修复 bridge 绕过、配置漂移和双建表路径。

### 19.4 最容易失败的环节

第一是模拟供应商页面变化导致报价采集失败。第二是报价标准化的可比性，尤其包装、税口径、MOQ、运费和交期。第三是凭据/表单值不慎进入 LLM prompt、日志或缓存。

解决方法不是再建更多抽象，而是：

- 先用两个固定模拟站点稳定跑通报价主链。
- 审批后显式 continue，提交前重新读取页面。
- 原始证据 + 确定性换算 + 低置信度人工确认。
- 凭据只用 ID/vault，统一脱敏检查。

### 19.5 第一条优先跑通的流程

优先“供应商报价采集与比价”。它以读取为主，风险较低，能一次证明 Skyvern 浏览器执行、文件/表格提取、报价标准化、证据存储、比价、审计和 Dashboard；成功后再叠加采购申请与审批。

### 19.6 一人使用 Codex 是否可行

可行，前提是目标保持为可运行、可演示的企业原型，并严格限制范围。Codex 适合帮助追踪调用链、生成迁移/测试骨架、对齐 schema 和迭代站点任务；人仍需决定采购规则、验收页面行为、审查安全边界和验证真实 E2E。若直接追求多个真实供应商、ERP 集成、生产 SSO、HA 和合规认证，则不再是一人 16 阶段可控项目。

---

## 20. 关键仓库证据索引

### 20.1 后端入口与模型

- `skyvern/forge/api_app.py:create_api_app()`：核心/企业路由注册、中间件、demo seed、认证桥。
- `skyvern/forge/sdk/routes/agent_protocol.py:run_task()`：原生任务入口。
- `skyvern/services/task_v1_service.py:run_task()`：任务运行服务。
- `skyvern/forge/agent.py:ForgeAgent.execute_step()/agent_step()`：核心 Agent 步骤。
- `skyvern/forge/sdk/db/models.py`：Task/Step/Organization/Workflow/Action/Artifact 等。
- `skyvern/forge/sdk/schemas/tasks.py`：Task Pydantic schema。
- `skyvern/forge/sdk/workflow/models/workflow.py`：工作流 schema。

### 20.2 企业模块

- `enterprise/auth/models.py`、`jwt_service.py`、`permission.py`、`dependencies.py`、`bridge.py`。
- `enterprise/tenant/middleware.py`、`query_filter.py`、`routes.py`。
- `enterprise/approval/risk_detector.py`、`risk_keywords.py`、`routing.py`。
- `enterprise/approval/models.py`、`pubsub.py`、`routes.py`。
- `enterprise/notification/channels.py`、`dispatcher.py`。
- `enterprise/audit/models.py`、sanitizer、storage、logger、routes。
- `enterprise/agent/planner.py`、`executor.py`、`coordinator.py`。
- `enterprise/llm/resilient_caller.py`、`model_router.py`、`task_states.py`、`human_intervention.py`。
- `enterprise/skills/`、`enterprise/workflows/templates.py`、`routes.py`。
- `enterprise/dashboard/`、`enterprise/llm/action_cache.py`、`cache_routes.py`、`enterprise/demo_seed.py`。

### 20.3 迁移、部署、测试与前端

- `alembic/versions/2026_03_07_0001-enterprise_permission_tables.py`、`alembic/env.py`。
- `scripts/ensure_enterprise_schema.py`、`entrypoint-skyvern.sh`。
- `docker-compose.yml`、`docker-compose.prod.yml`、`Makefile`、`.env.example`、`nginx/`。
- `tests/integration/test_e2e_flow.py`、`tests/sit_test.py` 及各企业模块测试。
- `skyvern-frontend/src/router.tsx`、企业页面与 `src/__tests__/`。

### 20.4 尚需进一步验证

- 在安装完整依赖后复跑 601 个测试及覆盖率。
- 启动完整 Compose 后复跑 `tests/sit_test.py`。
- 验证当前 Skyvern 版本中 HumanInteraction block 的持久化/恢复细节。
- 验证生产 Nginx upstream 与 UI/API 端口。
- 对计划支持的真实供应商站点，逐站确认授权、页面稳定性、下载格式和服务条款。

---

## 21. 项目完成定义

ProcureRPA Enterprise 原型只有同时满足以下条件才能称为完成，而不是“页面和模块都存在”：

1. 报价工作流通过真实 Skyvern Task/Step/Action 运行并落库。
2. 标准化输出可追溯到页面或文件 Artifact。
3. 采购 API 在组织、部门、品类和角色四个维度完成基础校验。
4. high/critical 任务能创建单级审批，批准后通过显式 continue 继续。
5. 凭据、Token、银行账户和敏感采购数据不进入 LLM、日志或缓存。
6. 审计、审批和 Dashboard 能展示采购数据；内存 seed 必须明确标记为演示数据。
7. 报价流程使用真实 Skyvern 浏览器任务；申请审批和订单跟踪通过受控模拟门户完成场景验收。
8. 文档清楚标识模拟站点、简化审批、单机部署等演示级边界。

达到这 8 点后，该项目才同时具备“可运行”“可演示”和“能说明企业架构取舍”的求职展示价值。
