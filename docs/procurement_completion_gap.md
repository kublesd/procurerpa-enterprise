# ProcureRPA 功能对等路线

## 文档用途

本页是后续开发的能力索引和阶段排序，不是生产就绪声明。需要文件级实施步骤时，再读取 [`procurement_rpa_development_guide.md`](procurement_rpa_development_guide.md)。

- 基线：本仓库已重写历史，当前以 ProcureRPA Enterprise 源码为基线。
- 当前决定：先把上游全部企业能力直接改成采购语义，再优化实现质量。
- 第一阶段完成定义：采购语义、契约和演示行为与上游功能对等。
- 第二阶段完成定义：持久化、真实 Skyvern 接链、安全硬化和生产事实源逐项补齐。
- 当前状态：第一阶段 P1～P6 已在 `c4b2e3f` 完成；第二阶段 S1～S3 已完成，下一项只能领取 S4。
- 第二阶段逐文件步骤、验证命令和停止点见 [`procurement_rpa_development_guide.md`](procurement_rpa_development_guide.md)。
- 过期条件：ProcureRPA 基线变更，或本页全部第一阶段能力完成后重新核对。

## 路线原则

1. **直接适配，不先重构。** 上游的内存 store、启动 seed、模拟 Executor、独立 Planner/Skill 链、内存 Action Cache 和演示成本数据都可用于第一阶段。
2. **不回退现有强实现。** ProcureRPA 已有真实 PostgreSQL、权限、审批、审计和 Skyvern 报价链时直接复用；“允许上游原型”不等于删除更可靠的现有实现。
3. **两条链明确命名。** 现有真实采购主链继续叫“真实主链”；新增 ProcureRPA 形态的能力在第二阶段接线前叫“功能对等适配链”。
4. **债务不阻断，但必须可见。** 模拟、内存、未持久化、未接真实任务和安全输入不足统一进入第二阶段债务表。
5. **演示数据不冒充事实。** 第一阶段可以展示 demo 指标，但页面/API/报告必须标记来源；不得写成生产统计或量化收益。

## 当前真实基线

现有真实主链已经接通，不在本路线中重做：

```text
受控供应商页
  → POST /enterprise/procurement/quote-task
  → task_v1_service.run_task()
  → 原生 Skyvern executor / Chromium
  → Task + Artifact + SupplierQuote
  → Decimal 确定性比价
  → 采购工作台 / 审批 / 审计 / PostgreSQL Dashboard
```

Day 16 的自动化、Compose 健康、UI 页面加载和租户隔离抽查已有证据；本轮 `quotes` 与 `controls` 两场真实 LLM smoke 因 Gemini `RateLimitError` 未完成。该外部限流不阻断功能对等路线，也不能被写成 smoke 已通过。

## 企业能力逐项映射

### 1. 认证、租户与多维权限

| 项目 | 内容 |
| --- | --- |
| ProcureRPA 文件/行为 | `enterprise/auth/models.py`、`permission.py`、`dependencies.py` 与 `enterprise/tenant/*`；组织 × 部门 × 业务线 × 角色决定 read/operate/approve，TaskExtension 承载企业维度 |
| 采购等价场景 | 组织 × 采购部门 × 采购品类 × 角色；采购员、品类经理、审批人、管理员和查看人按采购范围访问任务、报价、合同与付款动作 |
| 第一阶段适配 | 把 `business_line` 语义映射为 `procurement_category`，复用当前已存在的部门/品类授权和服务端用户加载；只补上游仍暴露的金融命名与演示契约 |
| 验收演示 | 两个部门、两个品类和至少三种角色的可见/可操作/可审批矩阵可重复；跨组织始终拒绝 |
| 第二阶段债务 | 统一所有旧 business-line 字段、特殊跨域权限和缓存 key；补数据库约束/RLS 与完整边界测试（当前强实现已覆盖的部分不回退） |

### 2. 双阶段风险、审批路由与通知

| 项目 | 内容 |
| --- | --- |
| ProcureRPA 文件/行为 | `enterprise/approval/risk_keywords.py`、`risk_detector.py` 先做关键词/金额扫描，命中后可调用 Stage 2 LLM，失败保守回退；`routing.py` 按风险等级选审批部门；`pubsub.py` 可通过 Redis Pub/Sub 等待决定；上游 `routes.py` 使用内存 approval store |
| 采购等价场景 | 识别供应商资质、异常报价、合同条款、预付款、银行账户变更、敏感品类和大额采购；路由到部门审批人、品类经理、财务或合规 |
| 第一阶段适配 | 采购化关键词、Prompt、理由和审批角色；允许保留可选 LLM callable、固定风险路由、内存 store 或 Redis Pub/Sub 演示。当前数据库审批链可直接复用，不要求退回内存 |
| 验收演示 | 合成低风险文本不触发审批；供应商/金额高风险触发；Stage 2 成功和失败回退均有结果；批准/拒绝只在授权采购范围内生效 |
| 第二阶段债务 | LLM 输入最小化、采购专用阈值配置、审批路由持久化、多级/超时策略、Pub/Sub 断线恢复、与真实 Skyvern 暂停/继续统一 |

### 3. 审计、脱敏、通知与文件证据

| 项目 | 内容 |
| --- | --- |
| ProcureRPA 文件/行为 | `enterprise/audit/*` 提供动作日志、递归脱敏和对象存储；`enterprise/notification/*` 提供渠道降级；上游部分路由可由内存 store 驱动 |
| 采购等价场景 | 留存寻源、询价、报价提取、附件下载、比价、审批、合同/付款操作及其 Task/Artifact 证据 |
| 第一阶段适配 | 改采购 action 名称和样例；优先沿用当前 PostgreSQL 审计、MinIO Artifact 和通知实现，新功能尚未接入时可用上游回调/store 做演示 |
| 验收演示 | 密码、Token、银行账户和演示报价字段被遮罩；每个采购能力至少产生一条可识别的审计结果；通知未配置时明确降级 |
| 第二阶段债务 | 独立适配链的审计回调接入真实事务、文件权限和保留策略；消除内存审计源；补统一检索与失败恢复 |

### 4. LLM JSON 容错与人工接管

| 项目 | 内容 |
| --- | --- |
| ProcureRPA 文件/行为 | `enterprise/llm/resilient_caller.py` 生成 schema Prompt、清理 Markdown fence、JSON/Pydantic 校验并指数退避；失败设置 `needs_human=True`。`task_states.py` 定义 `NEEDS_HUMAN` 转换，`human_intervention.py` 支持 skip/manual_complete/terminate |
| 采购等价场景 | 报价字段、供应商信息、合同条款或采购页面动作无法可靠解析时转人工核验/接管 |
| 第一阶段适配 | 替换金融 Prompt 和样例；直接复用 dataclass、状态枚举与 resolution helper，允许 stuck task 保存在内存并由测试/演示直接调用 |
| 验收演示 | 非 JSON、代码围栏 JSON、schema 缺字段、重试后成功、重试耗尽和三种人工处置均可重复 |
| 第二阶段债务 | `NEEDS_HUMAN` 与 Skyvern TaskStatus 映射；stuck task/原始响应持久化与访问控制；真实接管 API、页面恢复点、审计和敏感上下文裁剪 |

### 5. Planner / Executor / Coordinator

| 项目 | 内容 |
| --- | --- |
| ProcureRPA 文件/行为 | `enterprise/agent/planner.py` 将目标拆为带完成条件和 retry/skip/abort/replan 策略的子任务；`executor.py` 顺序重试，未注入 handler 时返回 `simulated=True` 成功；`coordinator.py` 管理顺序执行、replan、resume ID 和审计回调 |
| 采购等价场景 | 把“完成一轮采购”拆为供应商发现、登录、询价、报价/附件提取、比价、审批、下单等子任务 |
| 第一阶段适配 | 采购化 Prompt、schema 字段和样例；允许独立运行、内存 `CoordinationState`、fallback 单步计划与无 handler 模拟成功 |
| 验收演示 | 一个采购目标生成多步计划；成功、retry、skip、abort、replan 和 resume-from 演示可运行；模拟输出必须展示 `simulated=True` |
| 第二阶段债务 | 注入真实 Skyvern handler；完成条件真实校验；计划/子任务/恢复点持久化；统一 Task ID/状态/Artifact/审计；缺 handler 改为失败 |

### 6. 七个可组合 Skill

| ProcureRPA Skill | 采购映射 | 第一阶段演示 | 第二阶段债务 |
| --- | --- | --- | --- |
| `login` | 登录供应商门户、采购平台或合同系统 | fake page/受控页填写账号并验证成功标识 | 凭据引用、Captcha/2FA、真实浏览器会话 |
| `session_keep_alive` | 保持供应商门户会话并在过期后重新登录 | 模拟 heartbeat、过期文本和 re-login | 会话持久化、并发占用与安全超时 |
| `form_fill` | 填写询价单、采购申请、合同或下单表单 | 普通输入、下拉/日期与提交回调 | 接 Skyvern 元素定位、字段策略与提交审批门 |
| `search_and_select` | 搜索供应商、物料、询价单或订单并选择 | 搜索框、结果等待与目标选择 | 歧义处理、候选证据与权限过滤 |
| `pagination` | 遍历供应商/报价/订单多页列表 | 页数上限、next/无限滚动演示 | 断点、去重、限流与大数据量处理 |
| `table_extract` | 提取报价表、交期、MOQ、税费或合同清单 | HTML table/CSS grid 输出 JSON/CSV | schema/Decimal 校验、Artifact 绑定与人工确认 |
| `file_download` | 下载报价单、合同、资质或对账附件 | 受控下载、类型和文件名检查 | MinIO/Artifact、病毒扫描、权限与留存策略 |

Skill 基础设施继续使用 `enterprise/skills/base.py` 的注册表、Pydantic 参数模型、错误策略和 `executor.py` 的顺序 Pipeline/audit callback。第一阶段不要求把 Pipeline 接入原生 Skyvern action loop。

### 7. 六个声明式 Workflow 模板

| ProcureRPA 模板 | 上游步骤形态 | 采购模板映射 |
| --- | --- | --- |
| `tpl_banking_statement` | login → 条件表单 → table_extract → file_download | 供应商历史报价台账采集与附件下载 |
| `tpl_banking_loan_reminder` | login → 到期条件表单 → table_extract | 采购订单交付到期与催交清单查询 |
| `tpl_insurance_claim_query` | login → search_and_select → table_extract | 询价单/采购任务批量状态查询 |
| `tpl_insurance_renewal` | login → 到期条件表单 → table_extract | 供应商合同到期与续签核查 |
| `tpl_securities_report` | login → search_and_select → pagination → file_download | 供应商资质/报价附件批量检索归档 |
| `tpl_securities_nav` | login → 编码/日期表单 → table_extract | 物料市场价/历史基准价采集 |

`enterprise/workflows/schemas.py` 的参数定义、敏感标记、SkillStepDefinition 和字面量/参数映射直接沿用；模板 industry 改为采购场景分类。`routes.py` 的参数校验、Fernet 加密和遮罩可保留。第一阶段允许 instantiate 只返回生成的 task ID，而不创建真实 Skyvern Task。

**模板验收：** 六个采购模板均可列出、查看、校验参数并实例化；密码等敏感参数只显示遮罩；至少一个模板能解析成 Skill Pipeline。第二阶段再补模板/实例持久化、真实 Task 创建、参数密钥托管和运行记录。

### 8. 页面复杂度路由与 Action Cache

| 项目 | 内容 |
| --- | --- |
| ProcureRPA 文件/行为 | `model_router.py` 根据元素数、iframe、动态内容、shadow DOM 和表单数路由 light/standard/heavy；`action_cache.py` 对清理后的 DOM 与目标做 hash，以组织为 key，默认内存 TTL 24 小时并统计 hit/miss；`cache_routes.py` 暴露管理 API |
| 采购等价场景 | 简单供应商目录用轻模型，动态询价门户用标准模型，复杂 ERP/合同页用重模型；重复页面目标复用动作决定 |
| 第一阶段适配 | 修改采购页面样例和模型档位说明；直接保留阈值、内存 dict、模块 singleton、DOM/goal hash、TTL 和管理 API |
| 验收演示 | 三类采购页面特征得到固定档位；同组织相同 DOM+目标命中缓存，DOM 或目标变化 miss；过期与清理可验证 |
| 第二阶段债务 | 接入 Skyvern action 决策点；迁移 Redis；补部门/品类/模型版本/Prompt 版本隔离；并发、失效、碰撞和敏感 DOM 处理 |

### 9. 成本统计、Dashboard 与演示 seed

| 项目 | 内容 |
| --- | --- |
| ProcureRPA 文件/行为 | 上游 `enterprise/dashboard/stats.py` 从内存 task/approval/model-call 列表计算趋势、人工接管、三档模型成本和缓存节省；`routes.py` 使用模块 store；`demo_seed.py` 在启动时生成固定随机演示数据并预置 cache 统计 |
| 采购等价场景 | 展示寻源/询价/报价/审批任务趋势、人工接管数量、采购页面模型调用和缓存命中/估算成本 |
| 第一阶段适配 | 当前 PostgreSQL 采购 Dashboard 继续作为真实事实页；成本/模型路由板块可另用采购化 demo model-call store/seed，必须展示“演示估算”来源 |
| 验收演示 | 固定 seed 生成可重复采购指标；成本按 light/standard/heavy 分组；缓存命中影响估算节省；真实与 demo 区块不混算 |
| 第二阶段债务 | 模型调用事实持久化、真实 token/价格版本、租户全维过滤、重启一致性、真实 cache 指标、去除启动写入和前端 fallback |

### 10. 企业页面与集成演示

| 项目 | 内容 |
| --- | --- |
| ProcureRPA 文件/行为 | 企业 Dashboard、审批、审计、权限和 LLM Monitor 页面配合 demo fallback 展示；认证桥把企业 JWT 接到 Skyvern；集成测试大量直接调用 helper/store |
| 采购等价场景 | 采购工作台、风险/审批中心、审计、权限矩阵、人工接管、模型路由/cache/成本运营页 |
| 第一阶段适配 | 复用当前页面壳和 API 接法；允许新增能力先由脚本、API 或 demo 页面演示，不要求本阶段全部接同一运行链；任何 fallback/demo 必须有醒目标识 |
| 验收演示 | 一次受控演示能看到采购权限、风险/审批、Planner/Skill、容错/人工、模型路由/cache/成本各自结果及其真实/模拟标签 |
| 第二阶段债务 | 统一登录态、状态与导航；移除未标记 fallback；接真实数据源和 Task diagnostics；建立跨模块事务、SIT 与持续验收 |

## 第一阶段已完成顺序

| 阶段 | 只完成这一项 | 领取下一阶段的门槛 |
| --- | --- | --- |
| P1 | 采购风险词库、Stage 2 LLM、权限与审批路由 | 合成数据的低/高风险、LLM fallback、授权审批演示通过 |
| P2 | LLM JSON 容错与 `NEEDS_HUMAN` 人工处置 | 重试、耗尽和三种处置演示通过 |
| P3 | Planner / Executor / Coordinator 采购化 | 多步计划及四种失败策略可演示，模拟标识清楚 |
| P4 | 7 Skill 与 6 采购模板 | 注册表数量、参数校验、模板实例化和一个 Pipeline 通过 |
| P5 | 模型路由、Action Cache、成本统计/Dashboard | 路由、hit/miss/TTL 与采购 demo 成本可重复 |
| P6 | 功能对等集成演示与文档收口 | 全部能力可从一个入口观察，真实/模拟/未接入边界清楚 |

P1～P6 已完成并固化在 `c4b2e3f`。这些阶段不再领取；保留本表用于解释第二阶段债务的来源。

## 第二阶段技术债总表

| 债务 | 当前允许状态 | 第二阶段目标 |
| --- | --- | --- |
| Executor 无 handler | 第一阶段 demo 保留 `simulated=True`；real 模式已失败关闭，S3 受控页 handler 已接 Task/Artifact | S4～S5 再由真实 Workflow/Skill 调用，不扩成第二套浏览器运行时 |
| Workflow instantiate | 只生成 task ID | 创建并追踪真实 Skyvern Task/Workflow |
| Planner/Coordinator 状态 | PostgreSQL 单表快照与乐观版本已完成；S3 已白名单持久化真实 Task/Artifact 结果；无 Session 路径仅供模拟 | 后续统一 Workflow/Skill 的恢复状态与事务边界 |
| Skill Pipeline | fake page/独立 Playwright context | 统一到 Skyvern browser/session/action 与 Artifact |
| `NEEDS_HUMAN` | 真实报价失败和 Planner replan 上限已写 PostgreSQL review | 页面恢复点、审批联动和统一事务仍后置 |
| Action Cache | 进程内 dict、24h TTL | Redis、全维租户 key、版本/失效/并发策略 |
| 模型路由 | 纯函数、未接 LLM 调用点 | 接真实模型配置、降级和调用审计 |
| 成本 Dashboard | 固定单价与 demo model calls | 真实 token、价格版本、持久化和租户过滤 |
| Demo seed/store | 启动或模块级内存数据 | 显式 seed、数据库事实源、重启一致性 |
| LLM 输入 | 可能接收原始文本/页面上下文 | 数据分类、最小化、脱敏、保留与访问控制 |
| 状态/审计双轨 | 独立枚举、回调或 store | 与 Task/Approval/Artifact/审计事务统一 |
| 集成证据 | 单元/演示链为主 | Compose + Chromium + PostgreSQL/Redis/MinIO SIT |

## 第二阶段执行顺序

| 阶段 | 只消除这一项债务 | 进入下一阶段的门槛 |
| --- | --- | --- |
| S1 | 持久化人工核验与 `NEEDS_HUMAN` | 真实报价失败创建持久 review；授权处置、审计、重启和租户隔离通过 |
| S2 | 持久化 Planner/Coordinator 状态 | 新 Coordinator 实例可恢复计划、已完成子任务和 replan 次数 |
| S3 | Executor 接原生 Skyvern Task/Artifact | 一个受控采购子任务真实执行；缺 handler 不再模拟成功 |
| S4 | Workflow instantiate 创建真实 Task | 模板返回可查询的原生 Task ID 和 TaskExtension，不再生成假 ID |
| S5 | Skill Pipeline 统一到 Skyvern | 至少一个 login/form_fill/table_extract 模板产生真实 Artifact 和结构化结果 |
| S6 | Action Cache 接真实调用点和持久缓存 | 重启后可命中，跨组织/DOM/目标/模型/版本严格 miss |
| S7 | 模型路由接 Skyvern LLM 配置 | 档位解析到真实配置 key，降级、审计和 cache 隔离通过 |
| S8 | 成本 Dashboard 改用真实 Step 事实 | `/cost` 查询 PostgreSQL token/cached token/cost，不再读取 demo facts |
| S9 | 安全硬化、SIT 和 fallback 清理 | Compose、真实 smoke、重启、越权、前端和全链目标测试全部有证据 |

第二阶段一次只能领取一项。不得笼统领取“全部生产化”，不得提前实现后续阶段的表、抽象或基础设施。

## 下一项只做 S4

先领取 **S4：Workflow instantiate 创建真实 Task**。S1 已提供持久人工 review，S2 已提供可恢复协调快照，S3 已提供一个受控供应商页的原生 Skyvern Task/Artifact handler；下一步只把一个采购模板实例化为可查询的真实 Task 与 TaskExtension。

S4 不接七个 Skill、不实现通用 Workflow 引擎，也不移除第一阶段 demo 的 `simulated=True` 路径。具体 Task 创建、参数边界、测试和完成门以第二阶段开发指南的 S4 小节为准。
