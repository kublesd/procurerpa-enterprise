# 项目进度

> 最后更新：2026-09-11 +08:00
>
> 本文件是当前目标、活动任务、最新证据、阻塞和下一步的唯一事实源。能力映射与保留债务见 `docs/procurement_completion_gap.md`，历史阶段契约见 `docs/procurement_rpa_development_guide.md`，重大取舍见 `DECISIONS.md`。

## 当前目标

当前没有活动的应用实现阶段。P1～P6 与 S1～S9 均为已执行的历史路线，不得自动领取或按旧顺序继续开发。

最近完成的任务是优化工程 harness：收敛文档职责、修复历史路线和当前状态冲突、补齐授权与证据边界。修改范围仅限：

- `AGENTS.md`
- `PROGRESS.md`
- `docs/procurement_completion_gap.md`
- `docs/procurement_rpa_development_guide.md`
- `docs/agent_development_workflow.md`

完成门已达到：只有 `PROGRESS.md` 声明动态状态；旧路线不再产生可领取任务；本地 Markdown 链接、harness validator、批准文件边界和 `git diff --check` 均通过。当前已回到“无活动实现任务”，不自动开始新的应用工作。

## 当前仓库事实

- 2026-09-11 本轮开始时直接观察：`main` 指向 `9d078c0be9569e2c7401250c2127be6e5e1a5e35`；仓库历史已重写，旧标签 `c4b2e3f` 和旧开发分支不再可解析，不能作为当前 revision 证据。
- 迁移源码直接观察：企业迁移链包含 `ent_009` 和 `ent_010`；当前运行数据库 revision 未在本轮验证，需执行 `alembic current` 才能声明。
- 现有真实采购主链继续保留：受控供应商页 → procurement API → 原生 Skyvern Task/Artifact → SupplierQuote → Decimal 比价 → 工作台/审批/审计/PostgreSQL Dashboard。
- 本轮开始前已有用户工作区修改：`skyvern/forge/sdk/workflow/models/block.py` 处于删除状态；不属于 harness 任务，必须保留且不得恢复、覆盖或纳入结论。

## 路线状态

| 路线 | 状态 | 证据边界 |
| --- | --- | --- |
| P1～P6 采购语义功能对等 | 历史记录为已完成 | 包含明确标记的 demo/simulated/not_connected 路径；不代表生产真实链 |
| S1～S8 逐项真实化 | 历史记录为已完成各自工程门 | 本轮未重新运行应用测试；不得把历史结果写成本次结果 |
| S9 安全硬化与 SIT | 历史记录为已完成“当前工程门” | 不等于第二阶段总完成；日志修复后的真实 `quotes` smoke 仍未验证 |

“当前工程门完成”只表示历史记录中的标准镜像、迁移、重启、权限、controls、测试和日志硬化证据已达到当时约定；“第二阶段总完成”仍要求当前相关源码下的真实 quotes 与 controls 两场 smoke。不得混用两个状态。

## 最近可用历史证据

以下均来自 2026-08-06～2026-08-09 的历史记录，不是本轮重跑：

- 主机 unit：`517 passed, 300 warnings`；容器 unit：`518 passed, 302 warnings`。
- `tests/integration/test_e2e_flow.py`：`39 passed, 6 warnings`。
- 前端：`15 files / 93 tests`，生产 build 通过。
- Compose 标准 Skyvern/UI 镜像、PostgreSQL/Redis/MinIO 健康、`ent_010` 迁移与重启一致性曾通过。
- `controls` 历史当前源码 smoke 曾通过：批准后 Task completed，拒绝后 canceled，并包含 PDF/MinIO Artifact 与审计证据。
- `quotes` 在日志修复前曾通过；日志修复后的两次运行均因 Gemini `RateLimitError` 进入 `needs_human`，因此当前对应真实 smoke 只能标记为 `unverified`。
- S5 真实 smoke 曾由用户报告通过但未提供新的 Task/Artifact ID；该项保留为“用户报告”，不是独立直接观察。

## 未验证与阻塞

- 待外部模型配额/服务可用且用户明确安排验证时，重跑标准源码的 `python scripts/smoke_procurement.py --scenario quotes`，记录 revision、环境、Task/Artifact/Quote ID 和结果。
- 本机 `.venv` 来自旧机器路径，系统 Python 依赖也可能不完整；应用验证优先使用已配置 Compose，或在明确任务中重建环境。
- 全量 Ruff 存在历史 agent/skills/workflows/demo/SIT 问题；没有当前应用改动时不顺带修复。
- Day 14 诊断产生的历史失败/待处理演示记录仍在数据库中；未经单独破坏性数据授权不得清理。

外部 Gemini 可用性是 quotes 真实验收的环境阻塞，不是当前 harness 文档优化的阻塞。

## 保留债务

详细边界由 `docs/procurement_completion_gap.md` 负责，当前仍影响后续工作的摘要为：

- 演示/兼容路径仍保留无 handler Executor、内存 Action Cache、demo 路由和固定成本 helper，生产路由不得调用。
- Skill/template 实例、Planner/Workflow/审批/页面恢复的持久状态与事务尚未完全统一。
- 敏感模板参数尚未接生产凭据存储；真实 Prompt/page context 的最小化、访问控制和保留策略仍需单独安全任务。
- 多级审批、采购阈值和独立 category/routing 持久化尚未实现。

这些债务都不是自动排期。实施前必须在本文件建立一个有范围、验收、验证、授权边界和停止条件的活动任务。

## 本轮 harness 证据

- 来源：本次直接观察。
- 修订与环境：`main@9d078c0be9569e2c7401250c2127be6e5e1a5e35`；Windows PowerShell；仅文档修改。
- 中间检查：4 个职责文档的本地 Markdown 链接通过；harness validator 退出码 `0`，仅给出 `discovery_incomplete` 和 `reuse_existing_owners` 建议。
- 最终验证：5 个批准文档的本地 Markdown 链接检查通过；harness validator 退出码 `0`，仅保留两项非阻塞建议；过期领取语句搜索无命中；`git diff --check` 退出码 `0`，只有 LF→CRLF 工作区提示。
- 批准边界：`git status --short` 只显示 5 个批准文档被修改，以及任务开始前已有的 `skyvern/forge/sdk/workflow/models/block.py` 删除。
- 范围外状态：预先存在的 `skyvern/forge/sdk/workflow/models/block.py` 删除保持不变。

## 下一步

1. 当前没有可自动领取的实现任务；等待用户定义下一项有界工作。
2. `quotes` 复测仅在外部模型可用且用户明确安排时执行；不要因此自行修改应用代码或领取旧阶段。
