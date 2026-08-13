# Day 6 — 采购单级审批代码清单

## 新增文件

| 文件 | 用途 |
| --- | --- |
| `alembic/versions/2026_03_11_0005_procurement_approval.py` | 创建单级采购审批表、审批状态约束和组织/部门待办索引 |
| `summaries/day_6_summary.md` | Day 6 功能、设计决策、踩坑和验证结果 |
| `summaries/day_6_code_list.md` | Day 6 新增和修改文件清单 |

## 修改文件

| 文件 | 修改内容 |
| --- | --- |
| `enterprise/approval/models.py` | 为现有 `ApprovalRequestModel` 增加发起人、审批人外键、任务唯一约束和采购风险约束 |
| `enterprise/approval/routes.py` | 将内存审批 API 改为数据库查询与状态更新，增加职责分离、范围校验、重复决定保护和显式 continue |
| `enterprise/approval/pubsub.py` | 旧构造入口补齐 requester 参数，保持模型字段一致；采购主链不依赖 Redis 等待 |
| `enterprise/procurement/routes.py` | high/critical 创建 pending 审批并延迟 Task 执行，响应返回审批 ID；low/medium 保持原执行链 |
| `skyvern/services/task_v1_service.py` | 为原生 Task 创建增加最小 `defer_execution` 开关，默认行为不变 |
| `alembic/env.py` | 注册审批模型 metadata |
| `enterprise/demo_seed.py` | 停止把演示内存审批注入真实审批路由，Dashboard 演示数据保持不变 |
| `tests/unit/test_approval_model.py` | 校验 requester 和单级审批模型约束 |
| `tests/unit/test_approval_pubsub.py` | 补齐 requester 构造参数回归 |
| `tests/unit/test_approval_routes.py` | 改为数据库审批、权限、幂等、拒绝和 continue 调用链测试 |
| `tests/unit/test_day_1_smoke_security.py` | 验证 high 风险暂停、审批持久化、幂等响应和 Skyvern 延迟执行开关 |

## 删除文件

无。

## 备注

未增加多级审批、审批规则平台、Redis 恢复、SLA、通知或新浏览器执行引擎；当前实现只覆盖采购演示所需的单级审批闭环。
