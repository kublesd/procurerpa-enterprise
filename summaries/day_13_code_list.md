# Day 13 代码清单

## 1. 新增文件及业务作用

- `skyvern-frontend/src/__tests__/DashboardPage.test.tsx`
  - 覆盖 Dashboard 空数据和 API 500，确认不显示旧金融演示数字。

## 2. 修改文件及业务作用

- `enterprise/dashboard/routes.py`
  - 从 PostgreSQL 加载租户可见采购事实，暴露四个采购 Dashboard 端点。
- `enterprise/dashboard/stats.py`
  - 提供采购概览、趋势、品类去重聚合和最近 Task 纯函数。
- `skyvern/forge/api_app.py`
  - 移除启动时的金融 demo seed 调用。
- `skyvern-frontend/src/routes/enterprise/dashboard/DashboardPage.tsx`
  - 改为真实采购 API、采购趋势/品类/最近 Task、错误和空态。
- `skyvern-frontend/src/routes/enterprise/approvals/ApprovalsPage.tsx`
  - 删除审批 demo，失败不本地伪造决定，备注按真实 API 请求发送。
- `skyvern-frontend/src/routes/enterprise/audit/AuditLogsPage.tsx`
  - 删除审计 demo，按 `{items,total,...}` 读取真实响应并显示错误/空态。
- `skyvern-frontend/src/router.tsx`
  - 下线 Permissions 和 LLM Monitor 路由。
- `skyvern-frontend/src/components/enterprise/EnterpriseSideNav.tsx`
  - 下线 Permissions 和 LLM Monitor 导航入口。
- `skyvern-frontend/src/i18n/locales.ts`
  - 增加采购 Dashboard、审批和审计页面文案。
- `tests/unit/test_dashboard.py`
  - 重写为采购统计、状态边界、唯一 Task、排序、空数据和端点契约测试。
- `DECISIONS.md`
  - 记录 Dashboard 只使用 PostgreSQL 采购事实的取舍。
- `PROGRESS.md`
  - 记录 Day 13 完成项、验证结果和未验证的 Compose 证据。

## 3. 删除文件及业务作用

- `enterprise/dashboard/cache.py`
  - 已无真实调用方，删除未配置且 org-only 的旧 Dashboard 缓存层。

## 4. 复用的已有入口

- `tenant_context_for()`、`filter_task_extensions()`、`apply_tenant_filter()`。
- `TaskModel`、`TaskExtensionModel`、`SupplierQuoteModel`、`ApprovalRequestModel`、`ProcurementCategoryModel`。
- 前端 `authFetch`、`GlassCard`、`StatusBadge`、`RiskBadge`、ECharts 和原生 Task diagnostics 路由。

## 5. 验证命令

```powershell
$env:PYTHONPATH = (Resolve-Path .venv\Lib\site-packages).Path
python -m pytest tests/unit/test_dashboard.py tests/unit/test_tenant_query_filter.py -q
.\.venv\Scripts\ruff.exe check enterprise/dashboard tests/unit/test_dashboard.py skyvern/forge/api_app.py
Set-Location skyvern-frontend
npm.cmd test -- --run src/__tests__/DashboardPage.test.tsx
npx.cmd eslint src/routes/enterprise/dashboard/DashboardPage.tsx src/routes/enterprise/approvals/ApprovalsPage.tsx src/routes/enterprise/audit/AuditLogsPage.tsx src/components/enterprise/EnterpriseSideNav.tsx src/router.tsx src/__tests__/DashboardPage.test.tsx --max-warnings 0
npm.cmd run build
Set-Location ..
git diff --check
```

## 6. 明确不在本 Day 范围内的内容

- 不修改数据库模型、迁移、审批状态机、审计查询权限或 Skyvern executor。
- 不新建权限管理 API、LLM Monitor API、缓存平台或第二套浏览器引擎。
- 不删除 Day 15 才统一清理的 `enterprise/demo_seed.py`、Permissions/LLM Monitor 源文件。
