# Day 16 交接摘要

## 1. 做了什么

- 按 Day 16 边界完成自动化门禁、Compose 健康、UI 页面加载和租户隔离抽查；没有新增采购功能、模型、迁移或服务。
- 修复前端测试环境读取 Node/happy-dom localStorage 的兼容问题，并让 Status/Risk Badge 测试显式使用英文 locale。
- 补齐 paused、queued、timeout、created、terminated、canceled 的中英文状态文案。
- 更新 README、完成度路线、PROGRESS.md 和本 Day 交接文件；区分历史真实通过证据与本轮复跑结果。

## 2. 真实调用链

    Compose health / UI Chromium / smoke script
      -> FastAPI enterprise auth + tenant context
      -> procurement quote-task or smoke-task
      -> Skyvern task_v1_service -> ForgeAgent -> ActionHandler -> PostgreSQL Task/Artifact/Quote
      -> deterministic compare / approval / MinIO / audit

本轮 UI/租户抽查复用了真实登录、context-options、Dashboard、审批、审计和 Task/Quote API；浏览器执行仍只走 Skyvern 原生链。

## 3. 设计决策

- Day 16 不切换本机 LLM、不修改密钥、不绕过 Skyvern；本轮 Gemini 限流只能记为外部阻塞。
- 历史 SIT 证据继续保留，但不把它伪装成本轮 smoke 通过；最终完成仍要求恢复配额后重跑 quotes 和 controls。

## 4. 踩坑记录

- 本机 .venv 指向不存在的旧 Python；后端门禁在现有 skyvern 容器内执行。
- docker compose up -d --build 超过 10 分钟后，API/UI 容器随后均 healthy；没有清理 volume。
- 宿主浏览器编译的 API 地址在容器 Chromium 中需把 localhost:18000 请求重写为 host.docker.internal:18000，否则只影响探针环境并返回 connection refused。
- 两次 quotes 复跑和一次 controls 复跑均在真实 Skyvern 执行阶段收到 Gemini RateLimitError；vendor-b 页面本身抓取到 24 个元素。

## 5. 验证结果

- 主链目标 pytest：27 passed, 11 warnings。
- 主链 Ruff、全量 compileall、alembic heads（ent_008）、docker compose config：通过；全量 Ruff 仍有 54 个历史非主链 lint 问题。
- 前端：npm.cmd test -> 15 files / 93 tests passed；npm.cmd run build 通过。
- Compose：PostgreSQL、Redis、MinIO、API、UI 均 healthy；直连 health 返回 ready=true。
- UI：it_buyer/services_buyer 工作台上下文分别为 IT/Services；审批人和管理员页面可加载。API 抽查中 IT buyer 可见 IT Task/Quote，Services buyer 返回 Task 404 且 Quote 为空，管理员可见。
- 既有真实 controls 证据：approved/continued tsk_557918162664443498 -> completed；rejected tsk_557918295808429750 -> canceled；MinIO Artifact a_557918300103397064，审计 quote_file_uploaded。
- 本轮 quotes：tsk_557945578959382534 -> completed，Quote sq_557945690628532308，Artifact a_557945686333565006；第二 Task tsk_557945690628532310 -> failed。本轮 controls tsk_557946163074935158 -> failed，此前已写入 approved/continued 审计。

## 6. 尚未验证

1. 有效 LLM 配额恢复后的本轮双供应商 comparison PASS，以及本轮 controls 的 completed/rejected/MinIO 全链复跑。
2. 全量 pytest 仍在旧 tests/integration/test_e2e_flow.py 收集阶段导入已删除的金融 compute_error_distribution；没有进入采购主链测试。
3. 全量 Ruff 的历史 agent/skills/workflows/demo/SIT lint 问题；未在 Day 16 顺手格式化无关代码。

## 7. 后续建议

1. 恢复有效 Gemini 配额或由用户指定已验证的本机模型配置后，重跑两条 smoke 并补写新的运行 ID。
