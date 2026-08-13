# 项目进度

> 最后更新：2026-08-09 +08:00
>
> 维护规则：只保留当前事实、证据、阻塞和下一步；详细能力映射下沉到 `docs/procurement_completion_gap.md`，历史 Day 证据保留在 `summaries/`。

## 当前目标

ProcureRPA 的采购语义功能对等（P1～P6）已在 `c4b2e3f` 完成。当前进入第二阶段，按 S1～S9 逐项完成真实 Skyvern 接链、持久化、真实缓存/成本、安全硬化和 SIT。

第二阶段仍要求每次只领取一个债务。S8 已达到完成门，S9 已达到当前工程完成门：安全硬化、SIT 和生产 fallback 清理完成；Gemini `quotes` 复测列入后续统一测试。

## 当前事实

- 当前分支：`codex/second-stage-s7-model-routing`；S9 实施和状态文档已提交并推送，工作区状态以 `git status --short` 为准。
- 工作区本轮存在第二阶段源码、测试和文档修改；每次开始必须执行 `git status --short`，不得清理或覆盖无关文件。
- 现有真实采购主链已保留：受控供应商页 → procurement API → 原生 Skyvern Task/Artifact → SupplierQuote → Decimal 比价 → 工作台/审批/审计/PostgreSQL Dashboard。
- Day 12 真实 UI 双供应商采集、报价展示、确定性比价和 diagnostics 链已有用户确认。
- Day 13 Dashboard 已由 PostgreSQL 采购事实驱动，重启前后统计一致由用户于 2026-08-01 手动验证。
- Day 14 既有真实证据：approved/continued `tsk_557918162664443498` → completed；rejected `tsk_557918295808429750` → canceled；MinIO Artifact `a_557918300103397064`；审计含 `quote_file_uploaded`。
- Day 16 自动化、Compose 健康、UI 页面加载和租户隔离抽查已完成；主链目标套件曾为 `27 passed, 11 warnings`，前端曾为 `15 files / 93 tests passed` 且 build 通过。
- Day 16 `quotes` 真实 LLM smoke 已于 2026-08-06 补跑完成：Task `tsk_559670922757641118`、`tsk_559671090261365742` 均 completed，并分别产生 Quote/Artifact `sq_559671090261365740`/`a_559671090261365734`、`sq_559671597067506768`/`a_559671592772539466`；第二 Task 首次 Gemini 调用短暂 `ServiceUnavailableError`，原生重试后成功。`controls` 仍未完成：`tsk_557946163074935158` approved/continued 后因限流 failed。
- P1 已完成采购语义适配：风险关键词/脱敏文本金额扫描、采购化 Stage 2 Prompt 与保守 fallback、组织/部门/品类/角色权限解析，以及审批决定的跨组织和品类授权复核。
- P1 目标测试 `tests/unit/test_p1_procurement_alignment.py`、风险/权限/审批 PubSub/审批路由/采购隔离相关测试共 `118 passed, 11 warnings`；本次修改文件 Ruff 检查通过。
- P2 已完成采购化 LLM 容错：报价/供应商/合同/采购页面动作 schema Prompt、Markdown fence 清理、Pydantic 校验、1/2/4 秒重试耗尽后的 `NEEDS_HUMAN`，以及 skip/manual_complete/terminate 人工处置；错误日志只保留安全错误类型。
- P2 目标测试 `python -m unittest tests.unit.test_llm_resilience -q`：`61 passed`；`python -m compileall -q enterprise/llm tests/unit/test_llm_resilience.py` 与 `git diff --check` 通过。
- P3 已完成采购化 Planner / Executor / Coordinator：fallback 生成寻源、登录、询价、报价提取、比价审批、下单六步；LLM Prompt 使用采购术语并复用现有脱敏器；Executor 顶层返回 `simulated`，fake handler 透传 screenshot/page URL；Coordinator 复用进程内 plan store 支持 resume ID。
- P3 目标测试 `python -m unittest tests.unit.test_agent tests.unit.test_p3_procurement_alignment -q`：`27 passed`；`python -m compileall -q enterprise/agent tests/unit/test_agent.py tests/unit/test_p3_procurement_alignment.py` 与 `git diff --check` 通过。
- P4 已完成采购语义适配：7 个 Skill 包级自动注册；6 个模板覆盖 direct materials/MRO/services 各两个；模板参数映射支持默认值、字面量和 `${parameter}` JSON 占位符，转换为模拟 `SkillStep` Pipeline；Skill、Pipeline 和 ID-only instantiate 均明确返回/标记 `execution_mode=simulated`。
- P4 目标测试 `python -m unittest tests.unit.test_p4_procurement_alignment tests.unit.test_skills -q`：`41 passed`；与 P3、模板注册/校验、加密遮罩合并验证共 `94 passed`；`python -m compileall -q enterprise/skills enterprise/workflows tests/unit/test_skills.py tests/unit/test_workflows.py tests/unit/test_p4_procurement_alignment.py` 与 `git diff --check` 通过。
- P4 六模板 route contract 用合成参数直接调用验证为 `6/6`；完整 FastAPI API 测试仍未验证，当前系统 Python 缺 `python-jose`/`SQLAlchemy`/`structlog`，旧 `.venv` 指向不存在的解释器。
- P5 已完成采购页面三档模型路由：供应商目录、动态询价门户、ERP/合同页分别固定到 light/standard/heavy，并显式返回 `demo_estimate`、`simulated`、`not_connected`。
- P5 已完成组织+DOM+目标的 24 小时内存 Action Cache，缓存统计带 demo 来源标签；过期/清理有效，管理清理按当前组织前缀执行。
- P5 已完成独立固定采购 demo model-call 成本统计与 `/enterprise/dashboard/cost`；成本/节省按三档 token 与 cache hit 估算，不覆盖真实 PostgreSQL Dashboard 四项指标。
- P5 最小验证：组合命令 `python -m unittest tests.unit.test_llm_resilience tests.unit.test_p5_procurement_alignment.TestP5ProcurementAlignment.test_three_procurement_page_profiles_route_to_fixed_tiers tests.unit.test_p5_procurement_alignment.TestP5ProcurementAlignment.test_action_cache_hits_same_org_dom_and_goal_only tests.unit.test_p5_procurement_alignment.TestP5ProcurementAlignment.test_fixed_procurement_demo_costs_are_repeatable_and_labeled -q` 为 `64 passed`（含 3 项 P5 纯逻辑验收）；`python -m compileall -q enterprise/llm enterprise/dashboard skyvern/forge/api_app.py tests/unit/test_action_cache.py tests/unit/test_p5_procurement_alignment.py` 与 `git diff --check` 通过。成本 API 与缓存管理 API 的完整路由测试未验证，当前系统 Python 缺 `python-jose`/`SQLAlchemy`。
- P6 已增加 `scripts/demo_procurement_parity.py` 单入口：合成采购目标依次观察风险/审批、Planner/Executor、fake Skill Pipeline、JSON 重试与 `NEEDS_HUMAN`、模型路由/Action Cache、demo 成本和安全审计摘要；每段显式标记 `demo`/`simulated`/`not_connected`，真实 `quote-task` 主链仅声明保留且不由该入口调用。
- P6 目标测试 `python -m unittest tests.unit.test_p6_procurement_alignment -q`：`1 passed`；脚本 `python scripts/demo_procurement_parity.py` 运行成功并输出 JSON；`python -m compileall -q scripts/demo_procurement_parity.py tests/unit/test_p6_procurement_alignment.py` 与 `git diff --check` 通过。测试输出保留既有 `DeprecationWarning`，未把它们扩展为本阶段任务。
- 第二阶段开发文档已改为 S1～S9 逐债务执行手册，明确真实入口、依赖、固定设计、禁止项、测试、完成门和低推理 Agent 停止条件；本地 Markdown 链接检查通过，`git diff --check` 通过（仅 LF→CRLF 提示）。
- S1 已实现 `procurement_human_reviews` Model、`ent_009` migration、报价失败持久 review、租户隔离的 list/detail/resolve API、Decimal/Artifact 校验、三种处置和现有 AuditLog 接入；未扩展 Skyvern `TaskStatus`，未接 Planner/页面恢复。
- S1 目标测试 `$env:PYTHONPATH='.venv\Lib\site-packages'; python -m pytest tests/unit/test_s1_human_reviews.py tests/unit/test_day_11_quotes.py tests/unit/test_day_4_procurement_isolation.py -q`：`11 passed, 11 warnings`；`python -m pytest tests/unit/test_llm_resilience.py -q`：`61 passed, 5 warnings`；当前修改文件 Ruff 检查通过，`compileall` 与 `git diff --check` 通过。
- S1 真实验收（2026-08-06）：PostgreSQL 从 `ent_008` 成功升级到 `ent_009`；真实失败路径返回持久 Review `phr_559658314019581022`，重复重试复用同一 Review；`manual_complete` 产生 Quote `sq_559658860383129680`，`skip_step` 与 `terminate` 均正确落库并写入 AuditLog；跨租户列表为空、详情返回 404；PostgreSQL 重启后新进程仍按 Review ID 读取 `resolved/manual_complete`。
- S1 容器级完成门：现有依赖镜像挂载当前源码执行 `alembic upgrade head` 与 S1 回归，迁移成功、测试 `11 passed, 11 warnings`；完整 Skyvern 镜像重建因 Docker Hub 基础镜像拉取超时未验证。
- S2 已新增单表 `procurement_coordination_states` 与 `ent_010` migration；当前 plan、子任务状态、完成 ID、replan 次数、状态和脱敏错误码按每个执行边界立即提交，`version` 条件更新拒绝旧快照覆盖。
- S2 已移除 `AgentCoordinator._plans`；注入数据库 Session 的持久路径只信 `task_id + organization_id` 数据库恢复点，忽略客户端 `resume_from`，跨组织与旧版本冲突显式失败，写库失败不会返回成功。无 Session 路径仅保留第一阶段模拟兼容。
- S2 达到 replan 上限时复用 S1 `procurement_human_reviews` 写入 pending review 和 AuditLog；不保存原始 Prompt、DOM、凭据、执行 `result_data` 或 LLM 原始响应。
- S2 目标套件（容器挂载当前源码）`tests/unit/test_agent.py`、`tests/unit/test_p3_procurement_alignment.py`、`tests/unit/test_s2_coordination_persistence.py` 为 `31 passed, 183 warnings`；目标文件 Ruff、compileall、`git diff --check` 通过。
- S2 PostgreSQL 真实验收（2026-08-06）：`ent_009 -> ent_010` 成功；同一真实 Task 上第一 Coordinator 保存中断点，第二新实例只执行未完成步骤并完成；replan 上限产生 S1 pending review。验收测试 `2 passed, 33 warnings`，测试创建的 coordination/review 行已清理。
- S3 已新增 `SkyvernProcurementHandler` tracer bullet：只接受服务端 allowlist 供应商 URL，使用固定脱敏目标调用原生 `task_v1_service.run_task()` 形态，创建 TaskExtension，要求 Task completed 且存在同组织 HTML/截图 Artifact，并返回 `skyvern_task_id/status/artifact_id/page_url/simulated=False`。
- S3 的 failed/timed_out/缺失或跨组织 Artifact 均失败关闭并创建 S1 pending review 与 AuditLog；real 模式缺 handler 返回 `real_executor_handler_missing`，第一阶段无 real 标记的 demo 仍保留 `simulated=True`。
- S3 只把 Task/Artifact/status/page URL/simulated 白名单字段写入 S2 快照，不持久化 handler 原始结果、DOM、Prompt 或 LLM 响应。目标套件在本机与挂载当前源码的现有 Skyvern 镜像均为 `39 passed, 206 warnings`；目标 Ruff、compileall、`git diff --check` 通过。
- S3 真实回归（2026-08-06）：受控双供应商 `quotes` smoke 的两条原生 Task、Artifact、Quote 和确定性比价均成功。smoke 客户端因第二 Task 耗时约 117 秒超过外层 124 秒组合上限而退出，但服务端随后完成全部 GET/compare/audit，PostgreSQL 已核对两条 Task/Quote/Artifact；临时受控页面服务已停止。
- S4 已把 Workflow instantiate 改为真实、延迟执行的原生 Skyvern Task：请求部门/品类必须在认证用户服务端范围内，URL 必须精确命中服务端 allowlist；Task navigation goal 和 S2 初始计划只包含模板静态文本，不保存模板参数或明文敏感值。
- S4 在同一企业事务创建 TaskExtension 与 `procurement_coordination_states` 初始快照；事务失败不返回 Task ID，并补偿取消已创建的原生 Task。响应返回 `execution_mode=real`、原生状态和真实 ID，同时用 `sensitive_parameters_connected=false` 明确凭据仍未接入生产存储。
- S4 目标套件在本机和现有依赖镜像挂载当前源码的容器内均为 `45 passed, 12 warnings`；目标文件 Ruff、compileall 与 `git diff --check` 通过。
- S4 Compose/PostgreSQL 真实验收（2026-08-06）：模板 `tpl_purchase_order_due` 创建 Task `tsk_559678438288146474`，API 同组织查询为 `created`；PostgreSQL 核对 TaskExtension 为 `org_procurement_demo/dept_it_procurement/pc_it`、coordination state 为 `running/version=1`，navigation goal 未出现合成密码。临时验收容器已移除。
- S4 主 Skyvern 镜像重建未验证：Docker Hub OAuth token 请求网络超时；真实验收使用现有依赖镜像挂载当前源码完成，不能等同于主服务镜像已发布。
- S5 已新增生产编译器：七个注册 Skill 校验后合并为一个原生 `TaskRequest` 的静态导航目标、安全 `navigation_payload`、提取目标和 JSON schema；编译结果不含密码、用户名、Token 或 URL，不新增 Action enum，也不调用第二套 Playwright runtime。第一阶段 `build_skill_pipeline`/fake page 仍保持 `simulated`。
- S5 已让 S3 `SkyvernProcurementHandler` 接收编译结果并执行原生 Task；completed Task 必须绑定同组织 Artifact，表格结果再经 Pydantic/header 校验，schema 错误以 `skill_table_schema_invalid` 创建 S1 pending review；下载模板以原生 Task/Artifact 为成功证据，不检查本地路径。
- S5 本机与现有 Skyvern 镜像只读挂载当前源码的目标套件均为 `90 passed, 23 warnings`；目标 Ruff、compileall、`git diff --check` 通过。警告均为既有 datetime/Pydantic/FastAPI deprecation。
- S5 真实 `quotes` smoke 未通过（2026-08-06）：受控页面可达且原生浏览器抓取成功，Task `tsk_559683854904169554` 在提取阶段连续遇到 Gemini `ServiceUnavailableError`，最大重试后失败，失败摘要又遇到 `RateLimitError`，既有规则返回 `quote_needs_human_confirmation`；未产生可作为 S5 完成证据的真实模板结构化结果。临时静态页服务已停止。
- S5 真实 smoke 后续已由用户于 2026-08-06 手动重跑并确认通过，S5 据此完成；本轮未提供新 Task/Artifact ID，具体运行标识未独立验证。此前 `tsk_559683854904169554` 的失败记录继续保留为 Gemini 短暂不可用/限流事实。
- S6 已在真实 `ForgeAgent` extract-action LLM 调用点接入显式注入的 Redis Action Cache；key 使用组织、规范化 DOM、目标、model key 和 schema version 的 SHA-256，24 小时 TTL，Redis 异常时安全回源 LLM。
- S6 缓存值只保留通过原生 `parse_actions` 校验的 click/wait/complete/scroll/keypress/close-page 安全字段；输入、上传、选项、文件 URL、原始 DOM/Prompt/响应正文不入缓存，旧或恶意 schema 会删除并回源。
- S6 管理 API 已优先使用 Redis 持久 store，stats/clear/reset 均按当前组织前缀隔离；第一阶段 `ActionCacheStore` 和同步 helper 继续保留为 `memory_demo/simulated/not_connected`。
- S6 本机目标与 Agent/S3/S5 回归为 `82 passed, 159 warnings`；现有 Skyvern 依赖镜像只读挂载当前源码运行完成门为 `44 passed, 45 warnings`；目标 Ruff、compileall、`git diff --check` 通过。警告均为既有 Pydantic/datetime/只读 pytest cache 警告。
- S6 Compose Redis 健康检查返回 `PONG`；真实 Redis 用两个独立客户端验证重建后命中，剩余 TTL 为 `86400` 秒，临时验证 key 与 stats 已删除。真实 action 调用计数测试在新建第二个 `ForgeAgent` 后仍只调用 LLM 一次。
- S7 已把采购 light/standard/heavy 档位解析到 `LLMConfigRegistry` 已注册 key；Task/Workflow 只写服务端解析出的原生 `llm_key`，heavy 缺失时按 standard/light 白名单降级，无可用模型时创建 deferred Task 和 S1 pending review，不调用 LLM。
- S7 的 Task 路由审计和真实 Step 模型调用审计只保存 tier、resolved key、reason code、Task/Step ID、耗时与安全错误类型；不保存 Prompt、响应正文或 provider secret。S6 cache key 继续使用 Task 的 resolved model key，跨模型不复用。
- S7 本机目标与 S3/S5/S6/P5 回归为 `61 passed, 57 warnings`；LLM 容错/Workflow/S7 合并回归为 `107 passed, 17 warnings`；现有 Skyvern 镜像只读挂载当前源码完成门为 `72 passed, 15 warnings`。目标 Ruff、compileall 和 `git diff --check` 通过。
- S7 真实 Gemini smoke（2026-08-06）：`docker compose exec skyvern python scripts/test_gemini.py` 返回 `OK: GEMINI_3.0_FLASH is available`，模型 `gemini/gemini-3-flash-preview`，耗时 `2.51s`，响应 `OK`。
- S8 已把 `/enterprise/dashboard/cost` 改为读取 PostgreSQL `steps` 的真实 input/output/cached token 与 provider cost；查询通过 Task → TaskExtension 复用组织、部门和品类范围，Task/Step/Extension 组织必须一致。
- S8 成本聚合使用 Decimal；有 token 但 `step_cost` 为 0/空时返回 `cost_status=unknown` 和空成本，不再估算缓存节省；P5/P6 的固定 demo helper 只保留给独立演示入口。
- S8 本机与现有 Skyvern 依赖镜像挂载当前源码的目标套件均为 `12 passed, 2 warnings`；目标 Ruff、compileall 与 `git diff --check` 通过。警告为既有 Action Cache `datetime.utcnow()` 弃用警告。
- S8 PostgreSQL 真实验收（2026-08-06）：132 条可见真实 Step 的 API 与独立数据库聚合完全一致，input/output/cached token 为 `131738/12687/0`，provider cost 为 `0.196832 USD`；API 返回 `data_source=postgresql_steps`、`execution_mode=real`。
- S9 已完成当前真实入口的安全硬化：认证上下文的部门/业务线/品类均从同组织服务端表重载；Task/TaskExtension/Artifact/Quote/Audit 查询补齐组织一致性；受限审计读取同时按部门和品类过滤；签名 URL、文件名和错误审计值不落原文；批准后的 continue 在审批行锁内先 claim Task，重复请求返回 409。
- S9 已清理生产缓存管理 API 的内存 fallback：`/enterprise/cache` 只使用 Redis 持久 store，Redis 未配置或不可用返回 503；Redis stats 的异步扫描 bug 已修复。Action Cache key 不含 Task ID，因此已删除会误清整个组织缓存的虚假 `/task/{task_id}` 端点，只保留明确的组织级 `/all`。第一阶段内存 helper、demo cost 和无 handler Executor 仍只保留在无生产调用方的演示/兼容路径，并保留显式标签。
- S9 当前源码验证（2026-08-09）：误删的受控 Skyvern `workflow/models/block.py` 已从 HEAD 精确恢复；本机 `tests/unit` 为 `517 passed, 300 warnings`，`tests/integration/test_e2e_flow.py` 为 `39 passed, 6 warnings`，前端为 `15 files/93 tests` 且生产 build 通过；缓存 task-scoped 端点回归测试先失败后通过。标准 Skyvern/UI 镜像已用精确版本基础镜像重建并健康启动；容器内 `tests/unit` 为 `518 passed, 302 warnings`，integration 为 `39 passed, 6 warnings`，`alembic heads/current` 均为 `ent_010`；`ready=true`、重启状态一致和修复后的预签名 URL 日志脱敏均通过。
- S9 当前真实 smoke（2026-08-09）：标准容器 `controls` 通过（批准后同一 Task completed、拒绝后 canceled、PDF/MinIO Artifact 与 `quote_file_uploaded` 审计）；标准容器 `quotes` 在日志修复前曾重跑通过。日志修复后的两次 `quotes` 重跑均因 Gemini `RateLimitError` 未完成，最终 Task 进入 `needs_human`；修复版 quotes 证据仍按未验证处理，列入后续统一测试，不阻断当前 S9 工程完成。旧 Day 16 `controls` 因 Gemini 限流失败的历史事实仍保留，不能删除或改写为当时已通过。
- S9 已达到当前第二阶段工程完成门：标准 Skyvern/UI 镜像重建、迁移、健康、unit/integration、controls、重启一致性、前端和日志脱敏均已通过；修复版 quotes 的 Gemini 验证明确延期到统一测试，不能改写为已通过。

## 文档路线

- [x] `AGENTS.md` 改为渐进式披露入口，第一阶段不再被真实链门槛阻断。
- [x] `docs/procurement_completion_gap.md` 改为逐项功能对等路线与第二阶段债务索引。
- [x] `docs/procurement_rpa_development_guide.md` 已替换为详细第二阶段 S1～S9 开发指南；第一阶段能力来源和债务保留在路线文档。
- [x] `docs/agent_architecture.md` 改为真实主链 + 功能对等适配链的两阶段架构。
- [x] 安全、开发流程、决策与 README 同步新阶段边界。
- [x] 本轮文档验证：目标链接均存在；`git diff --check` 通过（仅 LF→CRLF 提示）。P1/P2 目标测试通过；P2 当前文件 Ruff 未验证（本机解释器无 `ruff` 模块）。

## 第一阶段状态

| 阶段 | 能力 | 状态 |
| --- | --- | --- |
| P1 | 采购风险词库、Stage 2 LLM、权限与审批路由 | 已完成：功能对等适配链 |
| P2 | LLM JSON 容错与 `NEEDS_HUMAN` | 已完成：采购语义功能对等适配链 |
| P3 | Planner / Executor / Coordinator 采购化 | 已完成：功能对等适配链 |
| P4 | 7 个采购 Skill 与 6 个采购模板 | 已完成：功能对等适配链 |
| P5 | 模型路由、Action Cache、成本统计/Dashboard | 已完成：采购 demo 功能对等适配链 |
| P6 | 功能对等集成演示与文档收口 | 已完成：单入口演示与边界文档收口 |

## 第二阶段状态

| 阶段 | 能力 | 状态 |
| --- | --- | --- |
| S1 | 持久化人工核验与 `NEEDS_HUMAN` | 已完成：真实 PostgreSQL、失败 Review、三种处置、审计/租户隔离与重启读取均通过 |
| S2 | 持久化 Planner/Coordinator 状态和恢复点 | 已完成：PostgreSQL 快照、逐步提交、租户/版本冲突、重启恢复与 S1 review 均通过 |
| S3 | Executor 接入原生 Skyvern Task/Artifact | 已完成：allowlist handler、TaskExtension、同组织证据、S1 review、S2 安全结果、real fail-close 与真实 quotes 回归均通过 |
| S4 | Workflow instantiate 创建真实 Skyvern Task | 已完成：deferred 原生 Task、TaskExtension、S2 初始状态、租户/allowlist/敏感参数边界与 PostgreSQL 真实验收均通过 |
| S5 | Skill Pipeline 编译并执行为原生 Skyvern 行为 | 已完成：原生编译、S3 handler、schema/review/Artifact 与目标测试通过，真实 smoke 由用户确认通过 |
| S6 | Action Cache 接真实 action 调用点和持久缓存 | 已完成：真实 Agent 调用点、Redis 持久化、组织/model/schema/DOM 隔离、24h TTL、fail-open 与重建命中均通过 |
| S7 | 模型路由接 Skyvern LLM 配置和调用审计 | 已完成：Registry key、Task/handler、白名单降级、S1 review、model cache 隔离、Task/Step 审计与真实 Gemini smoke 均通过 |
| S8 | 成本 Dashboard 改用真实 Step 成本事实 | 已完成：PostgreSQL Step token/cost、租户范围、Decimal/未知成本语义、目标测试与真实聚合核对均通过 |
| S9 | 安全硬化、SIT 和生产 fallback 清理 | 已完成当前工程门：安全/租户/审计/幂等硬化、虚假 task-scoped 缓存端点清理、标准镜像/迁移/重启/controls/integration 已通过；修复版 quotes 因 Gemini 限流未验证，列入后续统一测试 |

## 第二阶段技术债

- Executor 的第一阶段 demo 在无 handler 时仍模拟成功；任何 `execution_mode=real` 调用均失败关闭。生产调用方仍需显式注入 S3 handler 和持久 Session；S3 只接一个受控供应商页，不是通用 Skill/Workflow 运行时。
- Workflow instantiate 已创建真实 deferred Skyvern Task、TaskExtension 和 S2 初始状态，并使用 S5 编译字段；敏感凭据仍未接生产凭据存储，用户验收使用受控/合成数据，不代表生产凭据链已接通。
- P4 的 `build_skill_pipeline` 仍保留为模拟 fake-page 入口；S5 生产编译器与 S3 handler 已接原生 Task/Artifact 和表格 schema 校验，但模板/实例未持久化，报价落库仍由既有 `ExtractedSupplierQuote`/Decimal 主链负责。
- S6 生产 Action Cache 已接真实 Skyvern action 调用点和 Redis；第一阶段内存 demo 仍保留。为避免持久化敏感值，输入/上传/选项类个性化动作当前不缓存，待有 secrets-safe value schema 后再扩展。
- S8 真实成本 Dashboard 已改读 PostgreSQL Step token/cost；P5/P6 的固定单价、token 与 cache hit 估算仅保留给独立演示脚本，不属于真实 API 或真实成本事实。
- S9 已把生产缓存管理入口收敛到 Redis；第一阶段内存 Action Cache、模型路由 demo helper、成本 demo helper 和无 handler Executor 仍属于演示/兼容债务，生产路由没有调用方，后续可在删除第一阶段入口时再移除。
- S9 标准镜像已由当前 Dockerfile 重建并完成 Compose image restart；基础镜像通过官方 AWS Public ECR 镜像按原标签供本机构建，仓库 Dockerfile 未改动。
- 上游 Prompt 可能接收原始文本/page context；当前只允许合成/脱敏演示数据，真实输入最小化与访问控制后置。
- P2 `NEEDS_HUMAN` 的真实报价失败已创建持久、租户隔离的 review 并写入 AuditLog；独立枚举/内存 `StuckTaskInfo` 仍保留给第一阶段演示，真实 Skyvern TaskStatus 映射、页面恢复点、审批联动、原始响应留存策略和统一事务仍后置。
- P1 的审批品类授权复用 TaskExtension 查询，审批表仍未持久化 category/routing 字段；采购阈值配置、品类级持久化路由、多级审批和真实 Skyvern 暂停/继续后置。
- 独立适配链的状态、权限、审计、恢复与真实采购主链尚未统一。

## 既有非路线阻塞

- 本地 `.venv` 创建于旧机器路径；需要时在容器内运行后端验证或重建环境。
- 系统 Python 缺少项目依赖；本轮复用工作区 Python 加载旧 `.venv\Lib\site-packages` 完成 S1 pytest/Ruff，旧 `.venv` 解释器本身仍指向不存在路径。
- 完整 `skyvern`/UI 镜像重建已验证：Docker Hub OAuth 不可达时改用官方 AWS Public ECR 精确版本基础镜像本地标签，`docker compose up -d --build` 成功，Skyvern/UI/DB/Redis/MinIO 均 healthy。
- S9 本机当前全量 unit 为 `517 passed, 300 warnings`；2026-08-06 现有依赖镜像挂载当前源码的证据为 `517 passed, 302 warnings`。警告主要是既有 datetime/Pydantic/FastAPI 弃用。
- S9 的 `tests/integration/test_e2e_flow.py` 已迁移到当前采购 Dashboard contract，`39 passed, 6 warnings`；未为恢复旧金融统计 API 添加兼容 fallback。全量 Ruff 仍有历史 agent/skills/workflows/demo/SIT 问题。
- S9 修复后的标准 `quotes` smoke 两次均遇 Gemini `RateLimitError`，因此 quotes 当前未验证；此前同一标准源码在日志修复前的 quotes 重跑通过，不能覆盖修复后限流未验证事实。该项不作为当前工程开发阻断，列入后续统一测试。
- 本机 Windows 没有 GNU Make；使用 `docs/agent_development_workflow.md` 中的 PowerShell 等价命令。
- Day 14 诊断产生的历史失败/待处理演示记录仍在数据库中，未清理。

## 下一步

1. 后续统一测试：Gemini 配额/服务可用时重跑修复版标准 `quotes` smoke，记录其未验证项的最终结果；当前 legacy integration、标准镜像、重启复核和 S9 工程门已完成。
2. 保留 Day 16 `controls` 曾因 Gemini 限流失败的历史记录；本轮当前源码 `controls` 已通过，但不能覆盖该历史未完成事实。
