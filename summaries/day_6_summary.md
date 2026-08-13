# Day 6 — 采购单级审批

## 做了什么

- 采购任务完成 Day 5 风险识别后，`high` 和 `critical` 风险会创建数据库 `pending` 审批；`low` 和 `medium` 继续按原流程执行。
- 高风险任务仍复用 Skyvern 原生 Task 和 task run，但在浏览器执行前保持 `created`，不会提前创建 Step 或启动 Agent。
- 审批列表、通过和拒绝接口改为直接读写 `approval_requests`，不再使用原 ProcureRPA 的进程内字典。
- 审批按组织和发起部门隔离，发起人不能审批自己的任务；错误角色、跨组织、跨部门和重复决定都会被拒绝。
- 审批通过后，发起人调用 `POST /api/v1/enterprise/approvals/{approval_id}/continue`，由原生 `AsyncExecutorFactory` 继续同一条 Skyvern Task。
- 审批拒绝后，原生 Task 被标记为 `canceled`，不能继续执行。

## 设计决策

| 决策 | 简单说明 |
| --- | --- |
| 数据库作为审批事实源 | 复用 `ApprovalRequestModel` 并补 requester/approver 字段；API 与采购提交链都操作同一张表 |
| 单级、同部门审批 | 当前演示只需要采购申请人和本部门审批人分离，不增加 stage、decision、规则版本等表 |
| 显式 continue | 批准只改变审批事实；继续接口再调用 Skyvern 原生 executor，避免实现第二套浏览器恢复机制 |
| 不接 Redis 等待 | 原 ProcureRPA Pub/Sub 没有真实业务调用方；当前用持久化审批 + 显式恢复即可完成演示闭环 |

## 踩坑记录

1. 原审批路由虽然已经注册，但只读写 `_approval_store`，页面操作不会改变数据库审批，也不会控制真实任务。
2. `task_v1_service.run_task()` 原来创建 Task 后必定立即进入 executor。增加默认值为 `False` 的 `defer_execution` 参数后，普通调用行为不变，高风险采购可以只创建 Task/task run，批准后再复用同一 executor。

## 验证结果

- Day 2～6 最小相关回归：`120 passed`。
- 原企业端到端生命周期回归：`40 passed`。
- 覆盖 high 风险暂停并返回审批 ID、数据库审批创建、pending 列表、approve/reject、禁止自批/跨组织/跨部门、重复决定、拒绝取消任务、批准后继续原生 Task。
- Ruff 静态检查通过，`git diff --check` 通过。
- Alembic 只有一个最新 head：`ent_005`；`ent_004 -> ent_005` PostgreSQL 离线 SQL 生成成功。
- 未发现阻断采购主流程的问题。

## 尚未验证

- 本次未连接真实 PostgreSQL 执行 `ent_005`，也未配置 LLM 运行批准后的真实浏览器动作；数据库和 executor 调用链已通过测试替身验证。

## 后续建议

- 配置可用 LLM 后，用采购员提交 high 风险任务、审批人批准、采购员 continue，完成一次真实浏览器闭环验收。
