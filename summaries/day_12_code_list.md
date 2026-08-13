# Day 12 代码清单

## 1. 新增文件及业务作用

- `skyvern-frontend/src/routes/enterprise/procurement/ProcurementWorkbenchPage.tsx`
  - 采购上下文选择、固定供应商入口、顺序任务启动、任务轮询、单条报价校验、比价展示和 Artifact 诊断链接。
- `skyvern-frontend/src/__tests__/ProcurementWorkbenchPage.test.tsx`
  - 覆盖成功链路和上下文接口 500 错误，防止页面用演示数据掩盖 API 失败。

## 2. 修改文件及业务作用

- `skyvern-frontend/src/router.tsx`：注册 `/enterprise/procurement` 路由。
- `skyvern-frontend/src/components/enterprise/EnterpriseSideNav.tsx`：加入采购工作台入口。
- `skyvern-frontend/src/i18n/locales.ts`：加入中英文采购工作台文案。
- `skyvern-frontend/src/util/authFetch.ts`：让共享认证请求在 Compose preview 中解析 `VITE_API_BASE_URL`。

## 3. 复用的已有入口

- 前端复用 `authFetch`、`GlassCard`、`StatusBadge` 和现有 i18n。
- 后端复用 `/enterprise/auth/me`、`context-options`、`quote-task`、Task 查询、报价查询和 compare API。
- 浏览器复用 Skyvern 原生 `task_v1_service`、Workflow/Action 执行链和 Artifact 持久化。
- 采购隔离、报价字段校验和确定性推荐继续由服务端实现。

## 4. 验证命令

```powershell
$env:NODE_OPTIONS='--no-experimental-webstorage'; npm.cmd test -- ProcurementWorkbenchPage
npm.cmd run build
.\node_modules\.bin\eslint.cmd src\util\authFetch.ts src\routes\enterprise\procurement\ProcurementWorkbenchPage.tsx src\__tests__\ProcurementWorkbenchPage.test.tsx
git diff --check
```

真实 UI smoke 在仓库根目录通过 PowerShell here-string 执行：

```powershell
docker compose exec -T skyvern python -
```

其 Playwright 脚本必须在登录点击后先执行 `await page.wait_for_url("**/discover")`，再访问 `/enterprise/procurement`；登录和工作台加载已由 Agent 验证，完整双供应商真实 UI smoke 已由用户确认通过。

## 5. 明确不在本 Day 范围内

- 不修改 Python 路由、数据库模型、Alembic 迁移或 Skyvern executor。
- 不接入 `enterprise/agent`、`enterprise/skills` 或第二套浏览器引擎。
- 不实现 Dashboard、任意供应商 URL、演示 fallback、前端金额决策或新的采购中台能力。
