# Day 16 代码清单

## 1. 修改文件及业务作用

- skyvern-frontend/src/i18n/useI18n.ts：对测试/非浏览器环境显式检查 window.localStorage 方法，保持真实浏览器行为不变。
- skyvern-frontend/src/i18n/locales.ts：补齐现有 StatusBadge 状态的中英文文案。
- skyvern-frontend/src/__tests__/StatusBadge.test.tsx、RiskBadge.test.tsx：测试显式选择英文 locale，避免依赖用户本地 locale。
- README.md：改为 Day 16 验收口径，列出已通过证据和 LLM smoke 未完成项。
- PROGRESS.md：写入本轮门禁、Task/Quote/Artifact、UI/隔离结果和阻塞。
- docs/procurement_completion_gap.md：把 Day 16 状态改为自动化/UI 已验证、LLM smoke 待重跑。
- summaries/day_16_summary.md、summaries/day_16_code_list.md：保存本 Day 交接事实。

## 2. 复用的已有入口

- enterprise/procurement/quote-task、smoke-task、Task 查询、报价比较、审批、Artifact/MinIO、审计和租户过滤。
- Skyvern 原生 task_v1_service、ForgeAgent、ActionHandler 和现有 Compose 服务。
- 采购 seed、演示账号、目标 pytest/Ruff、scripts/smoke_procurement.py。

## 3. 验证命令

    docker compose exec skyvern python -m pytest tests/unit/test_day_2_procurement.py tests/unit/test_dashboard.py tests/unit/test_approval_routes.py tests/unit/test_audit.py -q
    docker compose exec skyvern python -m ruff check enterprise/procurement enterprise/dashboard enterprise/approval enterprise/audit scripts/smoke_procurement.py tests/unit/test_day_2_procurement.py tests/unit/test_dashboard.py tests/unit/test_approval_routes.py tests/unit/test_audit.py
    docker compose exec skyvern python -m compileall -q enterprise scripts tests
    docker compose exec skyvern alembic heads
    Set-Location skyvern-frontend
    npm.cmd test
    npm.cmd run build
    Set-Location ..
    docker compose config
    curl.exe --noproxy * -f http://localhost:18000/api/v1/enterprise/procurement/health?ready=true
    docker compose exec skyvern python scripts/smoke_procurement.py --scenario quotes
    docker compose exec skyvern python scripts/smoke_procurement.py --scenario controls
    git diff --check

## 4. 明确不在本 Day 范围内

- 不新增功能、依赖、模型、迁移、页面、缓存或第二套浏览器执行链。
- 不修复与采购主链无调用关系的旧金融集成测试和历史原型 lint。
- 不清理历史失败/待审批演示记录，不打印或提交密钥、Token、原始报价和 presigned URL 参数。
