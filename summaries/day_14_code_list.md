# Day 14 代码清单

## 1. 修改文件及业务作用

- `scripts/smoke_procurement.py`
  - 增加 `quotes`/`controls` 场景、审批人登录、轮询、拒绝后 409、PDF 上传与 MinIO 回读校验。
  - 增加未注册 Gemini 模型的 fail-fast 检查，并脱敏成功输出。
- `enterprise/approval/routes.py`
  - 在拒绝分支的嵌套 Task 更新前快照审计上下文，避免 commit 后访问过期 ORM 属性。
- `tests/unit/test_approval_routes.py`
  - 增加嵌套提交使 approval 过期时的拒绝路径回归测试。
- `PROGRESS.md`
  - 更新 Day 14 当前事实、验证结果、已知问题和下一步。

## 2. 新增交接文件

- `summaries/day_14_summary.md`
  - 记录真实调用链、SIT 证据、踩坑和未验证项。
- `summaries/day_14_code_list.md`
  - 记录本 Day 文件边界、复用入口和验证命令。

## 3. 复用的已有入口

- 原生 Skyvern Task/Workflow/Action 执行链和现有 `smoke-task` API。
- 现有审批、Task continue、Artifact、MinIO presigned URL、审计 API。
- 现有 `ApiError`、租户隔离、确定性风险与审批状态机。

## 4. 明确不在本 Day 范围内

- 不新增数据库模型、迁移、浏览器引擎、编排器或后端业务路由。
- 不清理诊断过程中留下的历史演示记录。
- 不修复完整 pytest/前端测试中的 Day 13 既有阻断。
