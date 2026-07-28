# ProcureRPA Enterprise

基于 Skyvern 的采购 RPA 演示级企业原型。项目保留 Skyvern 原生
Task、Workflow、Action、Artifact 和 Browser Session 执行链，在同一
FastAPI 进程中增加模块化 `enterprise/` 扩展层。

当前处于 Day 1：只建立可运行开发基线、采购 API 边界和健康检查，不包含
组织权限、供应商、报价、采购申请、订单、风险或审批业务。

## 当前架构

```text
skyvern-frontend/                    React + Vite
        |
        v
skyvern/forge/api_app.py             FastAPI app factory
        |-- Skyvern native routers   /v1, /api/v1, /api/v2
        `-- enterprise/procurement   /api/v1/enterprise/procurement/*
                |
                `-- PostgreSQL / Redis / MinIO (reserved)
```

浏览器任务仍走 Skyvern 原生调用链：

```text
POST /v1/run/tasks/
-> task_v1_service.run_task()
-> AsyncExecutorFactory
-> BackgroundTaskExecutor
-> ForgeAgent.execute_step()
-> ActionHandler.handle_action()
```

工作流仍由 `workflow_service.run_workflow()` 进入 Skyvern 原生
`WorkflowService.execute_workflow()`。

## Day 1 API

```http
GET /api/v1/enterprise/procurement/health
```

该接口允许匿名访问，不读取数据库、Redis、MinIO、凭据或采购数据。

```json
{
  "status": "degraded",
  "service": "procurerpa-enterprise",
  "ready": false,
  "skyvern_core": {"status": "ok", "detail": "..."},
  "database": {"status": "unavailable", "detail": "..."},
  "redis": {"status": "unavailable", "detail": "..."},
  "minio": {"status": "unavailable", "detail": "..."},
  "browser": {"status": "ok", "detail": "..."},
  "version": "0.1.0"
}
```

`?ready=true` makes the endpoint return HTTP 503 unless ForgeAgent, PostgreSQL,
Redis and Chromium are available; MinIO is reported but is not a Day 1 task
dependency. LLM credentials are never checked by health.

### Development-only smoke task

```http
POST /api/v1/enterprise/procurement/smoke-task
Authorization: Bearer <enterprise super_admin JWT>
Idempotency-Key: <non-empty-key>
```

The request body must contain the authenticated organization and the exact
allowlisted URL (`https://example.com/` by default). The route is rejected
outside `local`/`dev`/`development`, accepts only the existing `super_admin`
role as the platform-admin equivalent, calls `task_v1_service.run_task()`,
waits for the native background executor/ForgeAgent, and returns HTTP 502 for
a non-completed Skyvern task. It accepts no prompt, credential, or procurement
data.

## Docker 开发环境

先复制环境变量模板；其中只包含明确标注的本地开发默认值。

```powershell
Copy-Item .env.example .env
# Set POSTGRES_PASSWORD, MINIO_ROOT_USER, MINIO_ROOT_PASSWORD and SECRET_KEY.
# Generate SECRET_KEY with: python -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose config
docker compose up --build
```

服务地址：

| 服务 | 地址 | Day 1 用途 |
| --- | --- | --- |
| ProcureRPA/Skyvern API | `http://localhost:18000` | 核心 API 与企业扩展 |
| 前端 | `http://localhost:18080` | Skyvern React UI |
| PostgreSQL | `localhost:15432` | 核心持久化 |
| Redis | `localhost:16379` | 后续企业协调能力 |
| MinIO API / Console | `19000` / `19001` | 后续私有审计制品；Day 1 无调用方 |

后端和前端镜像均由当前仓库源码构建。基础镜像及 PostgreSQL、Redis、MinIO
均在 Dockerfile/Compose 中固定版本。Compose 的后端健康检查调用真实采购
健康接口。

浏览器任务还需要在 `.env` 中配置一个 LLM provider。健康检查不需要 LLM
密钥，也不会向 LLM 发送任何数据。

## 本地开发

后端要求 Python 3.11～3.13：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.lock
.\.venv\Scripts\python -m pip install --no-build-isolation --no-deps .
Copy-Item .env.example .env
.\.venv\Scripts\python -m uvicorn skyvern.forge.api_app:create_api_app --factory --host 0.0.0.0 --port 18000
```

前端要求 Node.js 20：

```powershell
Set-Location skyvern-frontend
npm.cmd ci
npm.cmd run dev
```

Vite 开发地址为 `http://localhost:28080`，并把 `/api` 代理到
`http://localhost:18000`。

## 数据库迁移

Skyvern 和 enterprise 共用 `skyvern.forge.sdk.db.models.Base.metadata` 与根目录
Alembic 配置：

```powershell
.\.venv\Scripts\alembic upgrade heads
```

仓库中已有的 FinRPA enterprise 权限迁移仍是独立 Alembic head。这是继承的
迁移链问题，Day 1 不修改 Day 2 数据模型；Day 2 开始前必须把新增采购迁移接到
明确的 Skyvern head，并消除双建表路径。

## 测试

最小 Day 1 检查：

```powershell
.\.venv\Scripts\python -m pytest tests/unit/test_day_1_baseline.py -q
.\.venv\Scripts\python -m pytest tests/unit/test_day_1_smoke_security.py -q
docker compose config
```

The opt-in non-mocked E2E acceptance is
`pytest tests/integration/test_day_1_smoke_e2e.py -q` with
`PROCUREMENT_SMOKE_E2E=1`, `SMOKE_API_URL`, `SMOKE_PLATFORM_ADMIN_TOKEN`,
`SMOKE_ORGANIZATION_ID`, and `SMOKE_DATABASE_URL`. It requires a configured
LLM and asserts `tasks`, `steps`, and `actions` rows for the actual smoke task.

测试覆盖采购模块导入、匿名健康响应、完整 FastAPI app 路由注册，以及 Skyvern
原生 Task/Workflow 路由仍存在。真实浏览器任务、数据库迁移和容器启动需要本机
Docker、浏览器依赖及有效 LLM 配置，不以单元测试结果替代。

## 基线与边界

- 原 FinRPA Day 1 实现提交：`c3d8e38`；阶段分支：
  `upstream/day-1/project-setup`。
- 原分支没有记录被导入 Skyvern 源码对应的官方 upstream commit，因此本项目
  不虚构该版本；当前源码和本仓库 Git commit 是可审计基线。
- 当前仓库仍包含原 FinRPA Day 2～Day 16 的参考原型代码。它们不是采购功能，
  也不代表已接入 Skyvern 主执行链；本轮没有删除或改造这些文件。
- Day 1 不新增业务表、不实现 JWT/RBAC、风险、审批、采购 Agent、采购 Skill、
  供应商/报价/申请/订单或 Dashboard。
- 生产环境仍需 secrets manager、TLS、镜像签名/SBOM、固定镜像 digest、迁移链
  整理、备份恢复和高可用验证。

详细迁移设计见
[`docs/procurerpa_enterprise_migration_plan.md`](docs/procurerpa_enterprise_migration_plan.md)。
