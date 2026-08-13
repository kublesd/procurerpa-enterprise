# Day 9 — 采购主链路验收与安全收口代码清单

## 新增文件

| 文件路径 | 作用 |
| --- | --- |
| `docker-compose.dev.yml` | 本地开发覆盖配置：挂载源码并启用 Skyvern 热重载。 |
| `scripts/seed_procurement_demo.py` | 初始化演示组织、采购员、管理员、部门和品类；可重复运行。 |
| `scripts/smoke_procurement.py` | 一键验证低风险采购主链：seed、健康、LLM、登录、Skyvern Task、采购详情和审计。 |
| `tests/unit/test_request_logging.py` | 验证请求和响应中的密码、访问令牌会被脱敏。 |
| `alembic/versions/2026_03_13_0007_procurement_orchestration.py` | 保留已有开发数据库迁移记录的兼容迁移，不再新增已延期编排字段。 |
| `summaries/day_9_summary.md` | Day 9 完成内容、验证和延期边界说明。 |
| `summaries/day_9_code_list.md` | Day 9 关键文件清单。 |

## 修改文件

| 文件路径 | 作用 |
| --- | --- |
| `docs/procurerpa_enterprise_migration_plan.md` | 明确 ProcureRPA 当前只完成采购 RPA 主链；Day 9 通用多 Agent 编排和人工接管延期。 |
| `enterprise/approval/routes.py` | 审批 continue 在 session 关闭前复制必要字段，避免提交后访问过期 ORM 对象。 |
| `skyvern/forge/request_logging.py` | 统一递归脱敏请求/响应 JSON 中的密码和各类令牌。 |
| `skyvern/forge/sdk/api/llm/api_handler_factory.py` | LLM 失败时不输出异常链中的敏感调用信息，只保留错误类型。 |
| `skyvern/config.py` | 增加 Gemini 3.6 Flash 的可选模型映射。 |
| `skyvern/forge/sdk/api/llm/config_registry.py` | 注册 `GEMINI_3.6_FLASH`，使用 `GEMINI_API_KEY`。 |

## 复用的已有能力

| 位置 | 本阶段用途 |
| --- | --- |
| `skyvern/services/task_v1_service.py` | 创建原生 Skyvern Task。 |
| `skyvern/forge/sdk/executor/async_executor.py` | 执行审批通过后的原生任务。 |
| `enterprise/procurement/routes.py` | 低风险 smoke 入口、采购上下文写入和风险判断。 |
| `enterprise/audit/routes.py` | 按组织和角色查询审计记录。 |
| `enterprise/auth/routes.py` | 演示采购员和管理员登录。 |

## 验证命令

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --no-build --force-recreate skyvern

docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T skyvern `
  python scripts/smoke_procurement.py

.\.venv\Scripts\python.exe -m pytest -q `
  tests/unit/test_request_logging.py tests/unit/test_llm_resilience.py
```

## 不在本阶段范围内

- 不把 `enterprise/agent` 的 Planner、Executor、Coordinator 原型接入采购运行时。
- 不新增第二套浏览器执行器、通用 handler DSL、计划快照或断点恢复表。
- 不实现模型路由、缓存、通用人工接管页面或生产级编排恢复。
