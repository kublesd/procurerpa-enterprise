# Day 8 — 采购审计、脱敏和 MinIO 文件存储代码清单

## 新增文件

| 文件 | 用途 |
| --- | --- |
| `alembic/versions/2026_03_12_0006_procurement_audit.py` | 创建采购审计表、组织/部门查询索引和业务对象索引 |
| `summaries/day_8_summary.md` | Day 8 功能、设计决策、踩坑和验证结果 |
| `summaries/day_8_code_list.md` | Day 8 新增和修改文件清单 |

## 修改文件

| 文件 | 修改内容 |
| --- | --- |
| `enterprise/audit/models.py` | 增加采购事件类型和业务对象类型/编号 |
| `enterprise/audit/sanitizer.py` | 增加密码、Token、Webhook、银行账户、报价、身份证和手机号的递归脱敏 |
| `enterprise/audit/logger.py` | 使用独立事务写入脱敏审计，失败时不影响采购主流程 |
| `enterprise/audit/routes.py` | 将审计查询切换到 PostgreSQL，增加组织/部门范围过滤和报价 PDF 上传 |
| `enterprise/audit/storage.py` | 装配真实 MinIO 客户端、按月 Bucket、对象上传和短期预签名地址 |
| `enterprise/procurement/routes.py` | 在风险判断、采购提交和审批创建节点写审计，并统一使用 MinIO 配置做健康检查 |
| `enterprise/approval/routes.py` | 在审批通过、拒绝和任务继续节点写审计 |
| `enterprise/notification/dispatcher.py`、`templates.py` | 把脱敏后的通知发送结果写入审计，并携带最小组织/部门上下文 |
| `enterprise/demo_seed.py` | 停止把演示审计列表注入真实审计接口 |
| `skyvern/config.py`、`.env.example`、`docker-compose.yml` | 增加 MinIO 连接配置并传入后端容器 |
| `alembic/env.py` | 注册审计模型，确保迁移元数据完整 |
| `tests/unit/test_audit.py` | 覆盖数据库审计、脱敏、MinIO、权限、文件校验和失败处理 |
| `tests/unit/test_day_1_smoke_security.py` | 验证采购提交真实调用点会产生风险、提交和审批审计 |
| `tests/unit/test_approval_routes.py` | 验证审批决定和继续任务会产生审计 |
| `tests/unit/test_notification.py` | 验证通知结果写审计且不包含 Webhook 秘密 |

## 备注

未新增证据表、对象存储服务层、Hash Chain、WORM、KMS、病毒扫描或消息队列。当前演示继续复用 PostgreSQL、MinIO 和 Skyvern Artifact。
