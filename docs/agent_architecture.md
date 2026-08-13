# Agent 专题：架构与两阶段调用链

## 什么时候读

修改 API、Agent、Skill、Workflow、LLM 状态、缓存、数据库、采购任务或 Skyvern 接线前阅读。能力选择和阶段顺序先看 [`procurement_completion_gap.md`](procurement_completion_gap.md)。

本文基线：ProcureRPA 当前源码（2026-08-10 已重写历史，不再引用上游 commit）。核心路由或两阶段决策变化后重新核对。

## 当前架构：一套应用，两条用途不同的链

```text
React / API / script
        │
        ├─ 已验证真实采购主链
        │    procurement API
        │      → task_v1_service.run_task()
        │      → Skyvern executor / ForgeAgent / ActionHandler
        │      → Task / Artifact / SupplierQuote
        │      → Decimal 比价 / Approval / Audit / PostgreSQL Dashboard
        │
        └─ 第一阶段功能对等适配链
             Risk / Resilient LLM / NEEDS_HUMAN
             Planner → Executor → Coordinator
             Skill Registry → Pipeline → Workflow Template
             Model Router → in-memory Action Cache → demo cost
             （允许 fake page、内存状态、simulated handler、独立入口）
```

它们仍在同一个模块化单体中，不代表要永久建设两个产品。第一阶段允许按 ProcureRPA 形态把企业能力采购化；第二阶段再逐项决定接入原生 Skyvern、复用现有采购服务或删除重复运行时。

## 两阶段边界

| 判断 | 第一阶段：功能对等 | 第二阶段：真实化优化 |
| --- | --- | --- |
| 完成依据 | 采购语义 + 最小可运行演示 | 真实数据源、Task/Artifact、持久化与 SIT |
| Executor | 允许无 handler `simulated=True` | 注入 Skyvern handler，缺失即失败 |
| Planner/状态 | 独立 Pydantic/内存状态 | 计划、子任务、恢复点持久化并映射 TaskStatus |
| Skill/模板 | fake page、Pipeline、ID-only instantiate | 真实 browser/session/action、Task/Workflow 和运行记录 |
| `NEEDS_HUMAN` | helper 与内存 stuck task | 权限、状态、恢复、审计、页面全部接通 |
| Cache/路由 | 内存 dict、纯函数、独立 API | Redis、真实 action/LLM 调用点、版本化失效 |
| Dashboard | demo model calls/固定成本可接受且标记来源 | 真实 token、价格、租户过滤与重启一致性 |

“尚未接真实 Skyvern”在第一阶段是已知债务，不是停止适配的理由；“模拟链已经生产可用”始终是错误声明。

## 已验证真实采购主链

```text
受控供应商 URL
  → POST /api/v1/enterprise/procurement/quote-task
  → 认证 + 组织/部门/品类校验 + 确定性风险
  → TaskRequest(data_extraction_goal + schema)
  → task_v1_service.run_task()
  → AsyncExecutorFactory / BackgroundTaskExecutor
  → ForgeAgent.execute_step() / ActionHandler.handle_action()
  → extracted_information 校验
  → SupplierQuote + Artifact
  → Decimal 标准化和确定性比较
```

高风险真实链仍使用 defer execution → ApprovalRequest → approver decide → requester continue 同一 Task。现有链不得为了适配 ProcureRPA 原型而回退。

## 功能对等适配链

```text
采购目标/采购页面样例
  → 采购关键词 + 可选 Stage 2 LLM
  → Planner 生成采购 SubTask
  → Coordinator 顺序调用 Executor
       ├─ handler 已注入：使用该演示 handler
       └─ handler 缺失：simulated=True
  → Skill Pipeline / Workflow Template（可独立调用）
  → LLM JSON 容错；耗尽后 NEEDS_HUMAN helper
  → PageFeatures 模型档位 + 内存 Action Cache
  → demo 审计/成本摘要
```

第一阶段允许这些模块仅由测试、脚本或独立 API 调用。是否注册到采购公开路由由阶段需求决定，不要求一次把全部模块串成唯一运行时。

## 模块职责与当前事实

| 路径 | 当前事实 | 第一阶段用法 | 第二阶段关注点 |
| --- | --- | --- | --- |
| `enterprise/procurement/` | 真实报价、权限、Task/Artifact、比价已接通 | 保持不变，提供采购术语和现有契约 | 作为真实集成目标之一 |
| `enterprise/approval/` | 当前采购路由已使用数据库；上游还保留关键词、routing、Pub/Sub 形态 | 采购化双阶段风险和路由，可复用当前强实现 | 统一暂停/继续、品类路由和超时恢复 |
| `enterprise/llm/` | resilient caller、human helper、router、cache 多为独立模块 | 直接采购化并以测试/demo 验收 | 接真实模型/Task/action，持久化人工状态/cache |
| `enterprise/agent/` | 无采购运行时调用方；Executor 无 handler 会模拟成功 | 允许形成独立采购适配链 | 真实 handler、状态和审计映射 |
| `enterprise/skills/` | 7 个 Skill 使用 page context 和 Pipeline | 保留 fake page/独立 Pipeline | Skyvern session/action、凭据和 Artifact |
| `enterprise/workflows/` | 路由已注册；6 个金融模板；instantiate 只生成 ID | 改六个采购模板并保留上游行为 | 真实 Task/Workflow、实例持久化 |
| `enterprise/llm/action_cache.py` | 内存 singleton、24h TTL；cache API 已注册 | 采购 DOM/目标演示 | Redis、全维 key、真实 action 接点 |
| `enterprise/dashboard/` | 当前真实采购指标来自 PostgreSQL；上游成本函数依赖内存 model calls | 保留真实指标，成本区单独标记 demo | 模型调用事实和统一租户过滤 |
| `enterprise/audit/` | 当前 PostgreSQL/MinIO 实现强于上游 store | 优先复用；独立链可先回调演示 | 跨链事务、保留和检索 |
| `skyvern/services/task_v1_service.py` | 真实 Task 创建/执行入口 | 第一阶段不强制接入 | 第二阶段优先复用，不重写核心 |

## 架构修改规则

- 先从公开路由、测试或脚本追到最终状态；明确它属于真实主链还是适配链。
- 第一阶段只改当前能力需要的模块，不为未来真实化新增 repository/interface/event bus。
- 上游形态能完成采购演示时直接沿用；当前已有更强采购实现时直接复用，不做降级迁移。
- 任何输出都携带来源标签：`real`、`demo`、`simulated` 或 `not_connected`。
- 新的真实采购表仍必须带 organization，按业务带 department/category；文件证据继续优先复用 Artifact。
- 第二阶段修改 Skyvern 核心前，先证明 enterprise 层与公开 Skyvern service 不能完成。
- 真实金额、审批、提交、删除和推荐仍由确定性服务端规则决定；模拟/LLM 只能在隔离演示中表达上游行为。

## 最小核查

```powershell
rg -n "include_router|add_middleware" skyvern/forge/api_app.py
rg -n "run_task|execute_subtask|execute_pipeline|instantiate_template" enterprise skyvern/services
rg -n "simulated|in-memory|configure_store|configure_stores|demo|fallback" enterprise skyvern-frontend/src/routes/enterprise
rg -n "organization_id|department_id|category_id|business_line_id" enterprise
```

检查后在 `PROGRESS.md` 记录：真实调用方、仅测试调用方、模拟行为和第二阶段债务。第一阶段的最小演示通过后停止；不要顺手真实化下一项。
