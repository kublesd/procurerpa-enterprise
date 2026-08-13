# 设计决策

> 本文件只追加影响后续开发的重要取舍，不复制代码结构。来源/为什么：代码能说明“是什么”，但不能完整说明“为什么没有选另一条路”；适用条件：新架构选择、边界变化或替代方案被否决时；过期条件：正式 ADR 系统接管。

## 2026-07-31：目标是完成一条真实采购报价链

- 原因：当前企业底座已经接通，最大缺口是报价采集、标准化、比价和真实页面展示。
- 否决方案：按 ProcureRPA 目录逐项改名，或用模块数量和测试数量代表完成度。
- 约束：Day 10～16 按 `docs/procurement_completion_gap.md` 顺序实施，每次只领取一个 Day。

## 2026-07-31：浏览器执行只使用 Skyvern 原生链

- 原因：`task_v1_service`、原生 executor、ForgeAgent 和 ActionHandler 已能驱动真实浏览器。
- 否决方案：把 `enterprise/agent` 或 `enterprise/skills` 接成第二套 Planner/Executor 运行时。
- 约束：新报价任务使用 Skyvern TaskRequest 的提取目标与 schema；修改 Skyvern 核心前必须证明 enterprise 层无法完成。

## 2026-07-31：关键采购决定使用确定性规则

- 原因：金额、风险、审批、提交和供应商推荐需要可重复、可解释。
- 否决方案：让 LLM 直接决定报价是否有效、风险等级下限或推荐供应商。
- 约束：金额使用 Decimal；LLM 只做页面理解、字段候选映射和非决定性说明，输出必须再次校验。

## 2026-07-31：高风险任务采用单级审批和显式继续

- 原因：当前演示只需证明申请人与审批人分离，并继续同一条 Skyvern Task。
- 否决方案：Redis 阻塞等待、多级会签和新的流程编排平台。
- 约束：批准只写审批事实；发起人调用 continue 后才执行，拒绝后原 Task 必须取消。

## 2026-07-31：状态与决策分开持久化

- 原因：低推理 Agent 需要短小的当前状态，也需要关键取舍原因；聊天历史不能可靠跨会话。
- 否决方案：把全部状态塞进 `AGENTS.md`，或为每次会话创建新的长篇 handoff 文件。
- 约束：任务开始阅读 `PROGRESS.md` 和 `DECISIONS.md`；验证后覆盖 PROGRESS 的最新状态，DECISIONS 只追加重要决策。
- 2026-07-31 Day 10：报价事实单独存入 `supplier_quotes`，组织由认证用户服务端上下文派生，写入必须匹配同一组织的 TaskExtension 和 Artifact。
- 首版只接受 CNY 和 `unit` 基础单位；金额/数量使用 Decimal 与 Numeric，比较按含税到岸单价排序，交期、供应商 ID、报价 ID 固定破平局。
- 约束：Day 11 的 Skyvern 提取结果必须先通过同样的字段/租户校验再落库；不把 LLM 输出直接作为比价或推荐决定。

## 2026-07-31：报价采集结果必须绑定浏览器证据

- 原因：真实页面抽取需要保留可复核来源，不能只保存 LLM 返回的字段。
- 取舍：Day 11 只接受完成的原生 Skyvern Task、通过固定字段与置信度校验的单条报价，并绑定同 Task、同组织的 HTML 或截图 Artifact。
- 约束：缺字段、类型错误、低置信度或缺 Artifact 统一进入人工确认；跨 Task 比价保留每条报价的 `task_id` 和 `artifact_id`。

## 2026-08-01：采购工作台固定受控供应商入口

- 原因：Day 12 只需把已验证的真实报价链呈现给采购用户；任意 URL 会扩大 SSRF、权限和演示范围。
- 取舍：前端固定两个受控供应商页面并顺序调用已有 `quote-task`，组织、部门和品类继续由服务端事实控制。

## 2026-08-01：Compose preview 的 API 地址由共享 authFetch 统一解析

- 原因：Vite preview 没有开发服务器 proxy，工作台的相对 `/api/v1` 请求会落到 UI 静态服务并返回 500。
- 取舍：在共享 `authFetch` 中解析已配置的 `VITE_API_BASE_URL`，不让每个页面重复拼接 API 地址。

## 2026-08-01：Day 13 Dashboard 只保留 PostgreSQL 采购事实端点

- 原因：旧 Dashboard 使用进程内金融演示数据和未配置的缓存层，重启后会制造假统计，也无法按采购部门/品类隔离。
- 取舍：Dashboard 只保留 `overview`、`trend`、`categories` 和 `recent-tasks`，直接查询现有 TaskExtension、Task、SupplierQuote、ApprovalRequest 与采购品类表。
- 否决方案：继续保留旧金融端点、Redis org-only 缓存或前端失败 fallback；这些方案会把接口失败伪装成采购事实。
- 约束：查询先应用组织/部门/品类租户范围；审批只按已可见 Task ID 限制；无数据显示空态，接口失败显示真实错误；Permissions 与 LLM Monitor 暂不接入运行路径。

## 2026-08-01：采购演示数据只保留数据库 seed

- 原因：演示主链已经由真实 PostgreSQL、Skyvern Task、报价、审批、Artifact 和审计事实组成，旧金融内存/SQL seed 会制造第二套数据源。
- 取舍：`enterprise/procurement/seed.py` 是唯一演示数据来源；旧金融 seed、SIT runner 和无调用方的静态企业展示页面删除。
- 约束：seed 保持幂等，调用方负责 commit；不在 import 或 FastAPI 启动时自动写入业务数据。

## 2026-08-01：先完成 ProcureRPA 采购化功能对等，再统一真实链

- 原因：当前目标已从“只收口一条真实报价链”调整为“逐项把 ProcureRPA 企业能力适配成采购 RPA”；若先要求每项持久化并接入原生 Skyvern，会阻断 Planner、Skill、模板、容错、缓存和成本能力的直接适配。
- 取舍：第一阶段允许保留上游的内存 store、demo seed、模拟 Executor、独立 Planner/Skill 链、ID-only workflow instantiate、内存 Action Cache 和演示成本数据；完成标准是采购语义与最小演示对等。第二阶段再逐项完成 PostgreSQL/Redis、真实 Skyvern Task/Workflow/Action、安全硬化和 SIT。
- 保留：现有受控供应商 → Skyvern → Task/Artifact/SupplierQuote → Decimal 比价 → 审批/审计/Dashboard 真实主链不回退；已有更强采购实现无需降级成上游原型。
- 否决方案：继续用旧 Day 12～16 的“不得接 Planner/Skill/第二运行链”作为全局禁令；或为了对齐上游而删除当前真实采购实现。
- 约束：该决策对新的 P1～P6 路线优先，取代 2026-07-31 两项旧决策对新开发顺序和“只能使用原生链”的绝对适用；旧决策仍作为现有真实采购主链的历史设计依据。模拟/demo/未接入必须明确标记，真实密钥和真实敏感采购数据仍不得进入 LLM、日志或演示 store。

## 2026-08-01：P1 审批品类授权复用 TaskExtension

- 原因：现有 `approval_requests` 表只有部门和兼容 `business_line` 字段；P1 需要先证明品类授权，不能为第一阶段引入迁移和第二套审批事实源。
- 取舍：审批列表与 approve/reject 决定从同组织 TaskExtension 读取采购 `category_id`，再用服务端 `procurement_category_ids` 校验；`business_line` 只保留给旧调用方，管理员仍不能跨组织。
- 约束：审批表的 category/routing 持久化、多级路由、恢复和真实 Skyvern 暂停/继续进入第二阶段；现有真实报价与审批主链不回退。

## 2026-08-02：P4 模板按采购场景分类并保留模拟 Pipeline

- 原因：P4 需要让上游六个声明式模板具备采购语义，同时证明参数映射可以进入现有 Skill Pipeline。
- 取舍：模板按直接物料、MRO、服务采购各两个分类；包级导入自动注册七个 Skill；`build_skill_pipeline` 只做参数校验、字面量/占位符解析和 `SkillStep` 转换。
- 约束：Pipeline 和 instantiate 响应明确标记 `simulated`；当前只使用 fake page/内存步骤，不创建真实 Skyvern Task、不持久化实例，敏感参数仍只在响应中遮罩。

## 2026-08-02：P5 成本区与真实采购 Dashboard 分离

- 原因：P5 需要展示模型档位、缓存命中和成本节省，但当前 Dashboard 已由 PostgreSQL 真实采购事实驱动，不能用 demo model-call 数据覆盖任务、报价和审批统计。
- 取舍：复用现有 `dashboard/routes.py` 入口新增 `/cost`，成本计算读取独立固定采购 demo facts；模型路由与缓存继续使用纯函数/内存 singleton。
- 约束：成本单价、token、cache hit、节省值和模型路由均返回 `demo_estimate`/`simulated`/`not_connected` 标签；真实模型调用、价格事实、Redis、Skyvern action 接点和持久化进入第二阶段。

## 2026-08-02：P6 使用单入口演示收口，不统一第一阶段运行时

- 原因：P6 的验收目标是一次观察 P1～P5 的采购语义结果和边界，不是提前建设跨模块生产编排器。
- 取舍：新增 `scripts/demo_procurement_parity.py`，直接复用现有风险/路由、Agent、Skill Pipeline、LLM 容错、模型路由、Action Cache 和 demo 成本 helper；输出只保留采购结果、状态、合成 ID 和来源标签。
- 约束：fake page、内存 store、模拟模型和审计摘要统一标记 `demo`/`simulated`/`not_connected`；现有真实 `quote-task` → Skyvern → SupplierQuote → 比价/审批/审计/Dashboard 主链不由该脚本替换或冒充已联通。第二阶段再逐项接真实 handler、状态/审计持久化、Redis、模型调用和统一登录态。

## 2026-08-06：S6 在真实 Agent 调用点使用 Redis Action Cache

- 原因：Skyvern 既有数据库 action-plan 只按 URL+goal 复用，缺少组织、DOM、model、schema 和 24 小时 TTL；Vertex cache 只缓存 Prompt，均不能满足 S6 action decision 约束。
- 取舍：保留既有机制不改表，在 `ForgeAgent` extract-action LLM 调用点显式注入最小 Redis store；key 使用组织前缀和 SHA-256 variant，Redis 不可用时回源 LLM。
- 约束：只缓存原生解析器校验后的非个性化动作安全字段；输入、上传、选项、文件 URL、DOM、Prompt 和响应正文不得持久化。模型路由与真实 model key 解析仍属于 S7。

## 2026-08-06：S7 只路由到已注册的原生 LLM key

- 原因：Skyvern 的前端 model-name 映射不覆盖所有已启用 Registry key；仅写 model name 会让部分真实配置静默回落到默认 handler。
- 取舍：采购三档配置保存 Registry key，Task `model` 保存服务端解析出的 key/tier/reason；Task 只接受 Registry 已注册 key，继续复用原生 override handler，不实例化 provider SDK。
- 约束：heavy 只向 standard/light 降级；无可用 key 时创建 deferred Task 和 S1 review。审计只保存安全路由字段、Step ID、耗时和错误类型；真实 token/cost 聚合仍属于 S8。

## 2026-08-06：S9 生产入口失败关闭，第一阶段 fallback 不回流

- 原因：S9 的真实 API 不能在 Redis、MinIO、浏览器或持久化链不可用时返回 `simulated`/`demo` 成功；租户边界也必须由数据库事实再次约束，不能只依赖客户端 JWT 快照或关联表 ID。
- 取舍：缓存管理 API 只注入 Redis 持久 store，未配置/异常统一返回 503；Task/TaskExtension/Artifact/Quote/Audit 查询加入同组织关联条件；认证请求每次从同组织服务端表重载部门、业务线、品类和特殊权限；审批 continue 在审批行锁内 claim 原生 Task，失败则显式置为 failed。
- 约束：P6 的内存 Action Cache、demo cost、独立模型路由和无 handler Executor 仍保留给演示/兼容测试，但生产路由不可达且不得移除 `simulated` 边界标签。旧金融 Dashboard integration helper 不恢复为生产兼容 API，测试需迁移到当前采购事实 contract。

## 2026-08-09：HTTP response 日志不保存预签名 URL

- 原因：文件上传接口需要向调用方返回短期预签名 URL，但通用 response logger 不得把该 URL写入普通日志。
- 取舍：在共享精确字段脱敏集合中加入 `presigned_url`，仅把日志值替换为 `****`，不改变 API response 或 MinIO 对象引用。
- 约束：日志回归测试必须证明 `X-Amz-*` 查询值不落日志；业务库仍只保存 `minio://` object URI。
