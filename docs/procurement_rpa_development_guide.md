# ProcureRPA 第二阶段开发指南

## 1. 文档目的

本指南用于把已经完成的 ProcureRPA 第一阶段功能对等实现，逐项接入真实 Skyvern、PostgreSQL、Redis、权限、审计和运行证据。

目标读者是对仓库不熟、推理能力较弱的开发 Agent。执行者不需要一次理解整个系统，但必须严格遵守本指南的读取顺序、阶段边界、验证命令和停止点。

- 第一阶段基线提交：`c4b2e3f`，P1～P6 采购语义功能对等已经完成。
- 第一阶段演示入口：`scripts/demo_procurement_parity.py`。
- 第二阶段不是重写第一阶段，也不是新建第二套浏览器运行时。
- 第二阶段最终目标：真实入口不再依赖内存状态或模拟成功，并能在重启、跨租户、失败恢复和真实浏览器执行条件下重复验证。

旧版 P1～P6 实施细节不再放在本文件中。能力来源、第一阶段边界和技术债索引见 [`procurement_completion_gap.md`](procurement_completion_gap.md)。

## 2. 第二阶段完成定义

只有以下条件全部满足，才能写“第二阶段完成”：

1. Workflow、Planner、Executor、Skill 生产入口最终都复用 Skyvern 原生 Task/Step/Action/Artifact，不创建独立 Playwright 或第二套浏览器执行器。
2. `NEEDS_HUMAN`、计划、子任务、恢复点和人工处置均有 PostgreSQL 事实；服务重启后仍可查询和继续。
3. Action Cache 的真实路径使用 Redis 或已经验证等价的 Skyvern 原生持久缓存；进程重启后缓存行为可重复，且组织隔离有效。
4. 模型路由接入 Skyvern 已有 `llm_key`、`LLMAPIHandlerFactory` 和配置注册表；不能只返回演示档位。
5. 成本 API 查询 Skyvern `steps` 表的真实 token、cached token 和 `step_cost`；固定 demo facts 不再进入真实成本响应。
6. 真实入口的权限、租户过滤、确定性采购规则、审计和 Artifact 证据形成一条可复核链。
7. Compose、PostgreSQL、Redis、MinIO、Chromium 和 UI/API 的目标测试通过；外部 LLM 限流必须保留为“未验证”，不能用 fake 结果替代。
8. 第一阶段演示脚本可以保留，但必须继续标记 `demo/simulated/not_connected`，且不能被生产路由调用。

## 3. 真实、模拟和未验证的统一含义

| 标签 | 可以使用的条件 | 不能表示什么 |
| --- | --- | --- |
| `real` | 使用真实认证上下文、原生 Skyvern Task/Artifact 和持久事实源，重启后仍可读取 | 不等于已做安全审计或生产发布 |
| `simulated` | fake handler、fake page、内存 store 或合成结果 | 不能作为真实链验收证据 |
| `not_connected` | 代码存在但尚未接到生产调用点 | 不能写成“功能已完成” |
| `unverified` | 实现可能存在，但当前环境、依赖或外部服务阻止了验证 | 不能写成通过，也不能写成失败 |

如果响应仍返回 `simulated` 或 `not_connected`，对应第二阶段债务就没有完成。

## 4. 不得回归的真实采购主链

以下链路已经存在，第二阶段只能复用或增强，不能拆除、改回 demo 或绕过服务端规则：

```text
受控供应商页
  → POST /api/v1/enterprise/procurement/quote-task
  → task_v1_service.run_task()
  → Skyvern Agent / Chromium / ActionHandler
  → Task / Step / Artifact
  → SupplierQuote
  → Decimal 确定性比价
  → Approval / Audit / PostgreSQL Dashboard
```

关键真实入口：

- `enterprise/procurement/routes.py`：`quote_task`、`task_v1_service.run_task()`、报价校验和持久化。
- `skyvern/services/task_v1_service.py`：原生 Task 创建和执行；支持 `defer_execution=True`。
- `skyvern/forge/agent.py`：`execute_step()`、`ActionHandler.handle_action()`、LLM handler、token 和成本写入。
- `skyvern/forge/sdk/db/models.py`：`TaskModel`、`StepModel`、`ArtifactModel`；`StepModel` 已有 token、cached token 和 cost 字段。
- `enterprise/auth/models.py`：`TaskExtensionModel`，承载组织、部门、品类和采购风险上下文。

禁止新增 `EnterpriseBrowserRunner`、第二套 Playwright session、通用事件总线或与 Skyvern Task 并行的任务事实表。

## 5. 每个开发会话的固定流程

### 5.1 开始前

依次执行，不跳步：

```powershell
git status --short
git log -1 --oneline
Get-Content -Raw PROGRESS.md
Get-Content -Raw DECISIONS.md
```

然后只读取：

1. 本指南中当前阶段的一节；
2. 该节“必须读取”的源码和测试；
3. 该阶段真实调用方；
4. 需要安全判断时再读 `docs/agent_security_rules.md`；
5. 需要理解 Task/Workflow 调用关系时再读 `docs/agent_architecture.md`。

不要一次加载全部 `docs/`、全部 Skyvern 源码或全部历史 summary。

### 5.2 领取阶段

从 `PROGRESS.md` 读取唯一“当前第二阶段”。如果没有当前阶段，从本指南 S1 开始。领取后先在自己的工作说明中写一句：

```text
本次只完成 Sx：<阶段名称>；达到该阶段完成门后停止，不提前进入 Sx+1。
```

如果工作区已经存在无关修改，记录文件名并避开。不要 reset、checkout、clean 或格式化无关文件。

### 5.3 修改前调查

对准备修改的函数，先找定义、注册点和全部调用方：

```powershell
git grep -n "目标函数或类名" -- enterprise skyvern tests
```

必须回答四个问题后才能编辑：

1. 真实 HTTP/任务入口在哪里？
2. 组织、部门和品类来自哪个服务端对象？
3. 当前事实写到 PostgreSQL、Redis、MinIO，还是仅写到内存？
4. 失败后现有调用方期待 HTTP 错误、Task 状态还是人工处置记录？

找不到答案时继续只读调查，不凭文件名猜测。

### 5.4 最小实现顺序

1. 增加一个会失败的最小测试，证明当前债务存在。
2. 如果需要数据库字段，先写 Model 和 Alembic migration，再写 repository/query helper。
3. 把 helper 接到一个真实调用点，不先接所有入口。
4. 验证组织隔离、重启恢复和失败路径。
5. 删除或绕开对应生产路径中的内存 fallback；演示路径可保留。
6. 运行本阶段完成门；通过后更新 `PROGRESS.md` 并停止。

不要为未来阶段预建接口、工厂、事件总线、配置项或空表。

### 5.5 环境选择

优先使用仓库已配置的 Compose 环境，因为历史 `.venv` 可能指向旧解释器。

主机 Python 可导入全部依赖时：

```powershell
python -m pytest <当前阶段测试> -q
```

主机缺依赖时，不修改代码绕过导入，改用：

```powershell
docker compose exec skyvern python -m pytest <当前阶段测试> -q
```

任何环境都必须运行：

```powershell
git diff --check
```

测试导入失败、被跳过或因外部服务失败，都不能写成通过。

### 5.6 结束和交接

`PROGRESS.md` 只写以下事实：

- 当前阶段和状态；
- 实际修改文件；
- 实际运行的命令及通过数量；
- 未运行或失败的验证及原因；
- 下一阶段只能领取什么。

只有改变后续架构边界时才追加 `DECISIONS.md`。达到阶段完成门后立即停止。

## 6. 第二阶段顺序和依赖

| 阶段 | 唯一目标 | 依赖 |
| --- | --- | --- |
| S1 | 持久化人工核验与 `NEEDS_HUMAN` | 第一阶段基线 |
| S2 | 持久化 Planner/Coordinator 状态和恢复点 | S1 |
| S3 | Executor 接入原生 Skyvern Task/Artifact | S2 |
| S4 | Workflow instantiate 创建真实 Skyvern Task | S3 |
| S5 | Skill Pipeline 编译并执行为原生 Skyvern 行为 | S4 |
| S6 | Action Cache 接真实 action 调用点和持久缓存 | S5 |
| S7 | 模型路由接 Skyvern LLM 配置和调用审计 | S6 |
| S8 | 成本 Dashboard 改用真实 Step 成本事实 | S7 |
| S9 | 安全硬化、SIT、去除生产 fallback 和总验收 | S8 |

不能并行领取有依赖关系的阶段。不能用 S9 的全链测试替代前面每个阶段的局部完成门。

## 7. S1：持久化人工核验与 `NEEDS_HUMAN`

### 7.1 目标

把 `enterprise/llm/human_intervention.py` 的内存 `StuckTaskInfo` 和 helper，接到真实采购报价失败路径，形成可查询、可授权处理、可审计、重启后仍存在的人工核验事实。

### 7.2 必须读取

- `enterprise/llm/human_intervention.py`
- `enterprise/llm/task_states.py`
- `enterprise/procurement/routes.py` 中报价提取失败和 `_quote_needs_human_confirmation`
- `enterprise/auth/models.py` 的 `TaskExtensionModel`
- `enterprise/approval/models.py`，只学习组织/审批字段和约束，不复用审批表表示人工核验
- `enterprise/audit/logger.py`、`enterprise/audit/sanitizer.py`
- `skyvern/forge/sdk/schemas/tasks.py` 的 `TaskStatus`
- `tests/unit/test_llm_resilience.py` 和真实采购隔离测试

### 7.3 固定设计

1. 不直接给上游 `TaskStatus` 增加 `needs_human`。Skyvern TaskStatus 继续表示浏览器执行事实；企业人工状态单独持久化。
2. 新建一个最小 `procurement_human_reviews` 表和对应 Model。不要把人工核验混入 `approval_requests`。
3. 每条记录必须包含：review ID、Task ID、组织、部门、品类、状态、原因码、安全错误摘要、Artifact ID、动作索引/类型、创建与解决人、解决动作、时间戳。
4. `llm_raw_response`、密码、Token、银行账户、完整 DOM 和带查询参数的 URL 不进入数据库。需要页面证据时只保存已有 Artifact ID。
5. 同一 Task 同时最多存在一个 pending review；用数据库约束或事务内检查保证。
6. 历史操作写入现有 AuditLog，不另建“review event”表。

建议状态：`pending/resolved/terminated`。建议解决动作继续使用 `skip_step/manual_complete/terminate`。

### 7.4 实现步骤

1. 在 `enterprise/llm` 或更贴近采购领域的现有包中添加 SQLAlchemy Model；不要创建 service/repository/interface 三层。
2. 新增下一条 `ent_009` Alembic migration，`down_revision="ent_008"`；索引至少覆盖 `(organization_id, status)` 和 `task_id`。
3. 在 `alembic/env.py` 注册 Model 模块。
4. 把 `_quote_needs_human_confirmation` 的真实失败分支改为先落 review，再返回含 `review_id` 的安全错误响应。
5. 增加 list/detail/resolve API；所有查询先使用认证用户的组织、部门和品类范围。
6. `manual_complete` 只能接受服务端 schema 校验后的报价字段，并继续使用 Decimal、CNY、unit 和 Artifact/Task 同组织校验。
7. `terminate` 记录审计；只有 Skyvern Task 仍允许转换时才更新 Task，否则保留原终态并以 review 状态表示人工终止。
8. 服务重启后使用 review ID 再次查询，证明不是内存事实。

### 7.5 禁止项

- 不把完整 LLM 原始响应写入 review。
- 不让客户端提交 organization_id、department_id 或 category_id 作为可信范围。
- 不修改所有 Skyvern TaskStatus 调用方。
- 不在本阶段持久化 Planner 计划；那是 S2。
- 不建设人工接管前端，API 和测试足以完成 S1。

### 7.6 最小测试

至少覆盖：

- 非法报价或缺 Artifact 创建一条 pending review；
- 同一 Task 重试不会重复创建 pending review；
- 跨组织、跨部门、跨品类不可见且不可 resolve；
- 三种 resolution 状态正确；
- `manual_complete` 再次执行报价字段和 Artifact 上下文校验；
- 密码、Token、银行账户和原始响应不在数据库与日志中；
- 重新创建数据库 Session 后仍能读取 review。

### 7.7 完成门

```powershell
docker compose exec skyvern alembic upgrade head
docker compose exec skyvern python -m pytest tests/unit/test_llm_resilience.py tests/unit/test_day_4_procurement_isolation.py -q
git diff --check
```

实际测试文件名以仓库现有命名为准；如果新增专用测试，可追加到命令。只有真实失败路径能返回持久 review ID，S1 才完成。

## 8. S2：持久化 Planner/Coordinator 状态和恢复点

### 8.1 目标

移除 `AgentCoordinator._plans` 作为生产事实源。计划、子任务状态、已完成 ID、replan 次数和恢复点写入 PostgreSQL，进程重启后能从同一 Task ID 恢复。

### 8.2 必须读取

- `enterprise/agent/schemas.py`
- `enterprise/agent/planner.py`
- `enterprise/agent/executor.py`
- `enterprise/agent/coordinator.py`
- S1 的人工核验 Model/API
- `enterprise/audit/logger.py`
- `tests/unit/test_agent.py`、`tests/unit/test_p3_procurement_alignment.py`

### 8.3 固定设计

使用一个最小 `procurement_coordination_states` 表保存当前状态，不先拆 plans/subtasks/events 三张表。至少包含：

- `task_id` 主键和外键；
- `organization_id`；
- `navigation_goal` 的脱敏版本；
- `current_plan` JSON；
- `completed_subtask_ids` JSON；
- `total_replans/max_replans/status/error_code`；
- `version` 乐观并发字段；
- `created_at/modified_at`。

详细历史继续写 AuditLog。原始 Prompt、浏览器 DOM、凭据和 LLM 原始响应不进入 plan JSON。

### 8.4 实现步骤

1. 新增 Model 和 `ent_010` migration。
2. 在 Coordinator 内只增加直接的 load/save helper；不要先建抽象 repository 接口。
3. `run()` 开始时按 `task_id + organization_id` 读取；没有状态才创建计划。
4. 每个子任务开始、成功、失败、skip、replan 和转 S1 review 后立即提交状态。
5. 使用 `version` 防止两个请求同时覆盖状态；冲突返回 409，不做静默 last-write-wins。
6. resume 只相信数据库的 completed IDs，不相信客户端传入列表。旧 `resume_from` 参数只允许测试兼容，生产入口不得使用客户端值覆盖数据库。
7. 达到 `max_replans` 时创建 S1 review，并把 coordination status 写成 `needs_human`。

### 8.5 最小测试

- 初次 run 创建持久状态；
- 完成一个子任务后重新构造 Coordinator，能跳过已完成项；
- replan version 和次数持久化；
- 跨组织不能加载同一 task_id；
- 并发旧 version 更新得到 409/明确冲突；
- 写库失败不把内存状态返回成成功。

### 8.6 完成门

```powershell
docker compose exec skyvern alembic upgrade head
docker compose exec skyvern python -m pytest tests/unit/test_agent.py tests/unit/test_p3_procurement_alignment.py -q
git diff --check
```

必须额外留下一个“新 Coordinator 实例恢复旧 Task”的测试；否则 S2 未完成。

## 9. S3：Executor 接入原生 Skyvern Task/Artifact

### 9.1 目标

为 `ExecutorAgent` 注入真实 handler，使一个采购子任务通过 `task_v1_service.run_task()` 执行，并把真实 Task ID、最终状态、页面 URL 和 Artifact ID 返回给 Coordinator。

### 9.2 必须读取

- `enterprise/agent/executor.py`
- `enterprise/agent/coordinator.py`
- `enterprise/procurement/routes.py` 中 `_run_smoke_task`/`quote_task` 的组织加载和 TaskRequest 构造
- `skyvern/services/task_v1_service.py::run_task`
- `skyvern/forge/agent.py::execute_step`
- `skyvern/forge/sdk/db/models.py` 的 Task/Step/Artifact
- `tests/unit/test_agent.py`

### 9.3 固定设计

- 复用 `task_v1_service.run_task()`；不直接调用 Playwright。
- handler 从服务端上下文获取 organization、受控 URL、部门和品类；不接受任意客户端 URL。
- 每个执行结果至少返回 `skyvern_task_id`、`status`、`artifact_id`、`page_url` 和 `simulated=False`。
- 成功必须同时满足：Task 完成、completion condition 经确定性检查、需要证据的步骤存在同组织 Artifact。
- handler 缺失时：演示脚本仍可模拟；任何标记为 real 的 API 必须失败关闭，不能模拟成功。

### 9.4 实现步骤

1. 先复制 `enterprise/procurement/routes.py` 已验证的组织加载和 TaskRequest 调用形态，不发明通用 Skyvern SDK 包装层。
2. 只接一个受控供应商页面子任务作为 tracer bullet。
3. 为创建的原生 Task 同事务写 `TaskExtensionModel`，组织/部门/品类来自认证用户。
4. 查询最新 HTML 或截图 Artifact，并验证 `task_id + organization_id`。
5. 把 Task/Artifact ID 写入 S2 状态和 AuditLog。
6. Skyvern 失败或缺 Artifact 时创建 S1 review，不返回模拟成功。
7. 一个子任务真实通过后停止；不要在 S3 接七个 Skill。

### 9.5 最小测试

- fake `task_v1_service` 证明 TaskRequest、organization 和受控 URL 传递正确；
- completed + Artifact 返回 real 成功；
- failed、超时、缺 Artifact 返回失败并创建 review；
- handler 缺失的 real 入口失败；
- 跨组织 Artifact 被拒绝；
- 原有 demo 测试仍显示 `simulated=True`。

### 9.6 完成门

```powershell
docker compose exec skyvern python -m pytest tests/unit/test_agent.py tests/unit/test_p3_procurement_alignment.py -q
docker compose exec skyvern python scripts/smoke_procurement.py --scenario quotes
git diff --check
```

Gemini 限流时 smoke 标记未验证；单元测试通过不能替代真实 smoke。

## 10. S4：Workflow instantiate 创建真实 Skyvern Task

### 10.1 目标

把 `POST /enterprise/workflows/instantiate/{template_id}` 从“生成假 task ID”改成创建真实原生 Skyvern Task 和 TaskExtension，并返回可查询的真实 ID。

### 10.2 必须读取

- `enterprise/workflows/routes.py`
- `enterprise/workflows/templates.py`
- `enterprise/workflows/validator.py`
- `enterprise/workflows/crypto.py`
- `skyvern/services/task_v1_service.py` 的 `defer_execution`
- S2 状态和 S3 handler
- `tests/unit/test_workflows.py`、`tests/unit/test_p4_procurement_alignment.py`

### 10.3 实现步骤

1. 保留模板参数校验和响应遮罩。
2. URL 只能来自服务端模板或受控供应商配置；模板参数不能提供任意 URL。
3. 使用 `task_v1_service.run_task(..., defer_execution=True)` 创建原生 Task，不复制 Task 插入逻辑。
4. 创建 TaskExtension 和 S2 coordination state；任一步失败时回滚企业侧事务，不能返回孤儿假 ID。
5. 敏感参数不要写入普通 JSON。优先引用现有凭据/加密存储；如果当前 crypto 只是演示实现，S4 不得宣称敏感模板生产可用。
6. 响应改为 `execution_mode="real"`、真实 Task 状态和可查询 Task ID；删除生产消息中的 `Skyvern not connected`。
7. list/detail 仍可读取静态模板；本阶段不要求把模板定义持久化。

### 10.4 最小测试

- 六模板参数校验保持通过；
- instantiate 调用原生 Task service 且 `defer_execution=True`；
- TaskExtension 的组织/部门/品类正确；
- 返回 ID 可由同组织查询；
- 跨组织不可见；
- 敏感参数响应、日志和 Task navigation goal 中均不出现明文；
- 原生 Task 创建失败时不返回 ID。

### 10.5 完成门

```powershell
docker compose exec skyvern python -m pytest tests/unit/test_workflows.py tests/unit/test_p4_procurement_alignment.py -q
git diff --check
```

至少一个模板必须在 Compose 中创建出真实 Task 记录；仅 mock 测试不够。

## 11. S5：Skill Pipeline 统一到 Skyvern 执行

### 11.1 目标

保留七个采购 Skill 的声明和参数校验，但生产执行不得创建独立浏览器 session。Skill Pipeline 应编译成 Skyvern TaskRequest 的导航目标、提取 schema 和安全参数，再由 S3 原生 handler 执行。

### 11.2 必须读取

- `enterprise/skills/base.py`、`executor.py` 和七个 Skill
- `enterprise/workflows/templates.py::build_skill_pipeline`
- S3 handler 和 S4 instantiate
- `skyvern/forge/agent.py` 的 ActionHandler 调用
- `tests/unit/test_skills.py`、`tests/unit/test_workflows.py`

### 11.3 固定设计

1. `build_skill_pipeline` 可以继续作为模板编译器和 demo fake-page 测试入口。
2. 新增的生产编译结果只包含 Skyvern 已需要的 TaskRequest 字段和安全结构化参数；不要定义第二套 Action enum。
3. `login/session_keep_alive/form_fill/search_and_select/pagination` 转为导航目标和受控参数。
4. `table_extract` 必须提供 Pydantic/JSON schema；采购金额落库前继续走 Decimal 校验。
5. `file_download` 的成功条件是产生同组织 Task/Artifact，不是本地路径存在。
6. 未支持的 Skill 必须明确失败并创建 S1 review，不能 silently skip。

### 11.4 实现顺序

按以下顺序一次接一个 Skill：

1. `login`
2. `form_fill`
3. `table_extract`
4. `file_download`
5. `search_and_select`
6. `pagination`
7. `session_keep_alive`

前三个 Skill 跑通一个采购模板后，再补其余 Skill。不要同时重写七个实现。

### 11.5 最小测试

- 七个注册项不变；
- 编译输出不包含密码、Token 或任意 URL；
- login/form_fill/table_extract 组合产生真实 TaskRequest；
- table_extract schema 错误进入 review；
- file_download 绑定 Artifact；
- fake page demo 仍通过并保持 simulated 标签；
- real 路径没有直接 Playwright 调用。

### 11.6 完成门

```powershell
docker compose exec skyvern python -m pytest tests/unit/test_skills.py tests/unit/test_workflows.py tests/unit/test_p4_procurement_alignment.py -q
docker compose exec skyvern python scripts/smoke_procurement.py --scenario quotes
git diff --check
```

至少一个包含 login/form_fill/table_extract 的模板必须产生真实 Artifact 和结构化结果。

## 12. S6：Action Cache 接真实调用点和持久缓存

### 12.1 目标

让真实 Skyvern action 决策使用组织隔离的持久缓存；服务重启后可命中，DOM/目标/模型版本变化时失效。

### 12.2 必须读取

- `enterprise/llm/action_cache.py`、`cache_routes.py`
- `enterprise/approval/pubsub.py` 的 async Redis 使用方式
- `skyvern/forge/agent.py` 中 action 生成、`_build_extract_action_cache_variant` 和已有 cache 调用
- `alembic/versions/2026_02_27_1200-700dfebe7c5f_add_adaptive_caching_tables.py`
- `skyvern/config.py` 的 `REDIS_URL`
- `tests/unit/test_action_cache.py`

### 12.3 先做复用判断

先确认 Skyvern 原生 adaptive cache 是否已经覆盖当前 action decision。能复用时扩展组织、目标和版本 key，不再新建并行 Redis cache。只有原生缓存不能满足 24h TTL 和管理 API 时，才用 `redis.asyncio.Redis` 的 `get/setex/delete/scan_iter` 写最小 adapter。

### 12.4 Key 和数据规则

真实 key 至少包含：

```text
organization_id + normalized_dom_hash + goal_hash + model_key + prompt/schema_version
```

不要使用 MD5 处理需要抗碰撞的 key；统一 SHA-256。缓存 value 只能保存通过 schema 校验的动作结果，不能保存原始 DOM、截图、Prompt、凭据或页面正文。

### 12.5 实现步骤

1. 保留 `ActionCacheStore` 给 demo/unit test，但生产依赖必须显式注入持久 store。
2. 在真实 LLM action 调用前 lookup，成功校验后 set。
3. 缓存不可用时降级为正常 LLM 调用，不把业务 Task 判为成功或失败；记录安全指标。
4. 管理 API 的 stats/clear/reset 必须按当前组织前缀限制；禁止全局清理。
5. DOM、goal、model、schema version 任一变化必须 miss。
6. 记录 hit/miss/invalid/expired，不记录 value 内容。

### 12.6 最小测试

- 同组织相同 key 命中；
- 跨组织、DOM、goal、model、schema version 变化均 miss；
- TTL、删除和组织级清理有效；
- Redis/原生缓存异常时回源 LLM；
- 缓存恶意或旧 schema value 被拒绝并覆盖；
- 重建应用进程后仍能命中。

### 12.7 完成门

```powershell
docker compose exec skyvern python -m pytest tests/unit/test_action_cache.py tests/unit/test_p5_procurement_alignment.py -q
docker compose exec redis redis-cli ping
git diff --check
```

必须留下一个真实 action 调用计数证明第二次调用没有请求 LLM；仅测试 Redis adapter 不算完成。

## 13. S7：模型路由接 Skyvern LLM 配置和调用审计

### 13.1 目标

把 `route_procurement_page()` 的 light/standard/heavy 决策映射到 Skyvern 已配置的 LLM key，并在真实 Task/Step 上记录所选模型和安全路由原因。

### 13.2 必须读取

- `enterprise/llm/model_router.py`
- `skyvern/config.py` 的 LLM key 设置
- `skyvern/forge/sdk/api/llm/config_registry.py`
- `skyvern/forge/sdk/api/llm/api_handler_factory.py`
- `skyvern/forge/agent.py` 中 `task.llm_key` 和 handler 选择
- S6 cache key 构造
- `tests/unit/test_llm_resilience.py`、`tests/unit/test_p5_procurement_alignment.py`

### 13.3 固定设计

- 档位映射到配置 key，不在业务代码硬编码供应商模型名称。
- 如果所选 key 未配置，按 `heavy → standard → light` 的明确白名单降级；没有可用模型时失败并进入 S1 review。
- 金额、审批、供应商推荐和提交决定不由模型档位改变，仍由服务端确定性规则控制。
- 模型 key 必须进入 S6 cache key，避免跨模型复用。
- 日志只记录 tier、resolved key、reason code、Task/Step ID 和耗时，不记录 Prompt/响应正文。

### 13.4 实现步骤

1. 在 TaskRequest 创建前根据受控页面类型选择 tier。
2. 通过 `LLMConfigRegistry` 验证 key 存在，再写入 Task 的 `llm_key` 或原生 override 参数。
3. 复用 `LLMAPIHandlerFactory.get_override_llm_api_handler()`，不直接实例化 provider SDK。
4. 为路由和降级写 AuditLog；缺配置时给出安全错误类型。
5. API 响应从 `not_connected` 改为真实 resolved key 的安全别名，不返回密钥或 provider secret。

### 13.5 最小测试

- 三类采购页面解析到配置档位；
- 可用 key 进入 Task/handler；
- 缺 key 按白名单降级；
- 全部缺失进入 review；
- 不同 model key 的 cache 不互相命中；
- 日志和响应不包含 API key。

### 13.6 完成门

```powershell
docker compose exec skyvern python -m pytest tests/unit/test_llm_resilience.py tests/unit/test_p5_procurement_alignment.py -q
docker compose exec skyvern python scripts/test_gemini.py
git diff --check
```

外部限流时最后一项标记未验证，不得用 fake key 宣称完成真实模型 smoke。

## 14. S8：成本 Dashboard 改用真实 Step 成本事实

### 14.1 目标

让 `/enterprise/dashboard/cost` 查询 PostgreSQL `steps` 的 `input_token_count`、`output_token_count`、`cached_token_count` 和 `step_cost`，并应用与真实采购 Dashboard 相同的组织/部门/品类范围。

### 14.2 必须读取

- `enterprise/dashboard/routes.py`、`stats.py`
- `skyvern/forge/sdk/db/models.py::StepModel`
- `skyvern/forge/agent.py` 和 `api_handler_factory.py` 的 token/cost 写入
- `enterprise/auth/permission.py`、`enterprise/tenant/query_filter.py`
- `tests/unit/test_dashboard.py`、`tests/unit/test_p5_procurement_alignment.py`

### 14.3 固定设计

- 不新增 LLM call 表：Skyvern Step 已有真实 token 和 cost 字段。
- 通过 Task → TaskExtension 限定组织、部门和品类，再聚合 Step。
- `step_cost` 是 provider/runtime 记录值；为 0 或空时返回“成本未知”，不能用固定单价补成真实值。
- cache 节省只能根据真实 cached token 和明确价格事实计算；无法可靠计算时返回 cached token 数，不编造 saved USD。
- demo 成本 helper 可保留给 P6 脚本，但真实 `/cost` 不再调用 `get_demo_model_calls()`。

### 14.4 最小测试

- 两个组织的 Step 成本严格隔离；
- 部门/品类权限过滤与 overview 一致；
- token/cost 聚合使用 Decimal，舍入稳定；
- 空数据返回空 breakdown/零值，不 fallback 到 demo；
- 重启后数据一致；
- API 明确返回 `data_source="postgresql_steps"` 和 `execution_mode="real"`。

### 14.5 完成门

```powershell
docker compose exec skyvern python -m pytest tests/unit/test_dashboard.py tests/unit/test_p5_procurement_alignment.py -q
git diff --check
```

还必须用至少一个真实 Task 的 Step 行核对 API 聚合值；只插入 demo facts 不算完成。

## 15. S9：安全硬化、SIT 和生产 fallback 清理

### 15.1 目标

对 S1～S8 的真实链做统一安全、恢复、租户、审计和 Compose 验收；删除生产路径的模拟成功和 demo fallback。

### 15.2 必须读取

- `docs/agent_security_rules.md`
- `docs/agent_architecture.md`
- `docs/agent_development_workflow.md`
- S1～S8 修改的真实调用方
- `scripts/smoke_procurement.py`
- `tests/integration/test_e2e_flow.py`

### 15.3 安全检查表

- 组织、部门、品类全部来自认证服务端上下文；客户端同名字段只能作为过滤请求，不能扩大范围。
- 任意 URL、文件名、对象 key 和回调地址都有 allowlist/规范化校验。
- LLM 只接收任务所需的最小化、脱敏内容。
- 密码、Token、银行账户、原始 DOM、完整 Prompt 和预签名 URL不进入普通日志、AuditLog、缓存或测试快照。
- 金额使用 Decimal；报价有效性、风险下限、审批、提交、删除和推荐由服务端规则决定。
- 人工 resolution 有权限复核、幂等和审计。
- Redis key、SQL 查询、Artifact 查询均包含组织边界。
- 缓存、LLM、MinIO 或浏览器不可用时失败模式明确，不出现模拟成功。

### 15.4 fallback 清理

逐个搜索：

```powershell
git grep -n "simulated\|not_connected\|demo_estimate\|memory_demo\|_simulate_execution" -- enterprise skyvern
```

每个命中只能属于以下两类之一：

1. P6 演示或单元测试，继续明确标记；
2. 真实入口不可达的兼容代码，并有测试证明生产依赖不会走到它。

真实 API 仍返回这些标签时，不得完成 S9。

### 15.5 全链验证

```powershell
docker compose config
docker compose up -d --build
docker compose ps
docker compose exec skyvern alembic upgrade head
docker compose exec skyvern python -m pytest tests/unit -q
docker compose exec skyvern python -m pytest tests/integration/test_e2e_flow.py -q
docker compose exec skyvern python scripts/smoke_procurement.py --scenario quotes
docker compose exec skyvern python scripts/smoke_procurement.py --scenario controls
npm test
npm run build
git diff --check
```

前端命令在 `skyvern-frontend` 目录运行。不得为了让全量测试变绿而顺手修改无关历史失败；应先证明失败是否由当前阶段引入。

### 15.6 必须人工核对的场景

1. 正常双供应商报价采集、Artifact、SupplierQuote 和 Decimal 比价。
2. 高风险采购批准后继续；拒绝后不能继续。
3. 报价 schema 错误创建 review；授权用户 manual complete 后形成有效报价。
4. 服务重启后 coordination/review/cache/cost 仍可查询。
5. 第二组织、第二部门和第二品类不能读取或处置第一组织事实。
6. Dashboard 的采购事实和模型成本均来自 PostgreSQL，不出现 demo fallback。

### 15.7 第二阶段总完成门

只有以下证据齐全才更新 `PROGRESS.md` 为“第二阶段完成”：

- S1～S8 每项完成门的命令和结果；
- Alembic 从 `ent_008` 升级到最新 head 的证据；
- Compose 重启前后状态一致证据；
- quotes 与 controls 两场真实 smoke；
- 租户越权测试；
- 无敏感信息输出的日志抽查；
- 前端测试和 build；
- `git diff --check`。

Gemini `RateLimitError`、浏览器不可用或依赖缺失时，保留“未验证”并停止宣称总完成；已完成的局部阶段可以保留。

## 16. 数据库迁移规则

1. 当前企业迁移链最新已知 revision 是 `ent_008`；新迁移按 `ent_009`、`ent_010` 顺序追加。
2. 一次阶段只增加该阶段需要的表、字段、索引和约束。
3. Model 必须被 `alembic/env.py` import，避免 metadata 漏表。
4. 外键同时保留组织上下文检查；仅有 `task_id` 外键不足以防跨租户引用。
5. downgrade 必须能移除本阶段对象，但只在一次性测试数据库验证，不对共享开发数据库执行破坏性 downgrade。
6. migration 成功不等于 Model 与查询正确；必须同时验证 API/query。

检查命令：

```powershell
docker compose exec skyvern alembic heads
docker compose exec skyvern alembic current
docker compose exec skyvern alembic upgrade head
```

出现多个 head 时先调查迁移图，不随意创建 merge migration。

## 17. API 和错误契约

- 400：请求格式正确但业务动作无效。
- 401：未认证。
- 403：已认证但组织/部门/品类/角色无权限。
- 404：资源不存在或为防枚举而隐藏不可见资源。
- 409：重复 resolution、并发 version 冲突或状态不允许转换。
- 422：参数、报价 schema、Artifact 上下文或 Decimal 校验失败。
- 503：Redis、LLM、MinIO、浏览器等真实依赖不可用且当前动作无法安全继续。

错误正文只返回稳定 error code、简短安全说明和允许公开的资源 ID。堆栈、Prompt、provider 原始响应和凭据不得返回客户端。

## 18. 测试证据书写模板

在 `PROGRESS.md` 使用以下格式，不写“应该通过”“看起来正常”：

```markdown
- Sx 实际修改：`file_a.py`、`file_b.py`、`migration.py`。
- 目标测试：`<完整命令>` → `NN passed`。
- 真实验证：Task `<id>`、Artifact `<id>`、Review `<id>`；结果 `<状态>`。
- 重启验证：重启前 `<事实>`，重启后 `<事实>`。
- 未验证：`<命令/场景>`，原因 `<具体错误类型>`。
- 保留债务：`<只列不属于当前阶段的债务>`。
```

禁止使用以下表述：

- “全部完成”但没有命令和 ID；
- “pytest 通过”但实际是 import error 或 skip；
- “真实链已接入”但响应仍是 `simulated/not_connected`；
- “限流不影响”后把真实 smoke 写成通过。

## 19. 低推理 Agent 的停止条件

遇到以下任一情况，停止编码并把事实写入交接，不继续猜测：

1. 真实调用方与本指南描述不一致；
2. 必须修改 Skyvern 核心，但 enterprise 层尚未证明无法完成；
3. 需要新增密钥、外部账户或真实供应商数据；
4. 迁移出现多个 head 或现有数据库 schema 与 Model 不一致；
5. 无法证明 organization/department/category 的服务端来源；
6. 真实采购决定只能依赖 LLM 才能继续；
7. 同一阻塞连续三次仍无法推进。

停止时必须写清：已读取文件、实际错误、已尝试命令、未修改内容和需要的唯一用户决定。不要用“可能”“大概”代替证据。
