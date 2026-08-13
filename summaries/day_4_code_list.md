# Day 4 — 采购数据隔离代码清单

## 新增文件

| 文件 | 用途 |
| --- | --- |
| `alembic/versions/2026_03_09_0003_procurement_category_scope.py` | 创建用户-采购品类范围表和采购任务范围索引。 |
| `tests/unit/test_day_4_procurement_isolation.py` | 验证采购路由先按范围过滤再关联核心任务，越权详情返回 404。 |
| `summaries/day_4_summary.md` | Day 4 总结和验证结果。 |
| `summaries/day_4_code_list.md` | Day 4 文件清单。 |

## 修改文件

| 文件 | 修改内容 |
| --- | --- |
| `enterprise/procurement/models.py`、`seed.py` | 增加 `UserProcurementCategoryModel` 和最小采购演示种子（管理员、IT/服务采购员、审批人、viewer）。 |
| `enterprise/auth/dependencies.py`、`schemas.py`、`routes.py`、`bridge.py` | 从数据库加载并公开可信采购品类范围；受限用户不能通过原生 Skyvern JWT 入口绕过采购范围。 |
| `enterprise/auth/models.py` | 为组织、部门、品类任务查询增加复合索引。 |
| `enterprise/tenant/context.py`、`middleware.py`、`query_filter.py`、`routes.py` | 将范围从业务线切换为品类，默认拒绝无范围查询，并修复可见性诊断跨组织查询。 |
| `enterprise/procurement/routes.py` | 增加受保护的采购任务列表和详情，收紧上下文选项，并在真实 smoke 任务创建后写入采购上下文。 |
| `tests/unit/test_tenant_*.py`、`test_day_4_procurement_isolation.py`、`test_day_1_smoke_security.py`、`test_auth_bridge.py`、`test_day_2_procurement.py` | 覆盖服务端权限覆盖 JWT、admin/cross-org-read、多品类、缺范围拒绝、跨部门/品类/组织隔离、任务上下文写入和最小采购角色种子。 |

## 备注

未新增通用 repository、透明 ORM 事件或第二套任务执行链；采购任务继续复用 Skyvern `TaskModel`。

`enterprise/auth/routes.py` 使用已安装的原生 bcrypt 校验本地演示账号，避免当前 Passlib 与 bcrypt 版本不兼容导致登录失败。
