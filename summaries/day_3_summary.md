# Day 3 — JWT 认证与采购角色权限

## 今日改动

今天完成 ProcureRPA Enterprise 的 JWT 登录、服务端角色校验和原生 Skyvern 接口防绕过。采购用户现在必须先登录，且系统不再只相信 Token 里携带的角色。

1. **复用现有登录和 Token 签发**：继续使用 `POST /api/v1/enterprise/auth/login` 校验企业用户密码，并通过现有 `JWTService` 签发 Bearer Token；没有新建用户表、认证服务或增加依赖。修复了 Windows 下使用无时区时间生成 `exp` 时，刚签发的 Token 被误判过期的问题。
2. **每次请求读取可信权限**：`get_current_user` 先校验 Token 签名和过期时间，再按 Token 的 `sub` 从 `enterprise_users`、`user_department_roles`、`user_business_lines` 和 `special_permissions` 表读取用户状态、组织和角色。这样禁用用户会立即失效，Token 中伪造的 `super_admin`、组织或特殊权限不会参与授权判断。
3. **保护采购写接口**：`POST /api/v1/enterprise/procurement/smoke-task` 继续创建真实 Skyvern 任务，但改为复用 `require_any_operator`。operator、org_admin 和 super_admin 可以调用；未带 Token 返回 401，viewer 或 approver 返回 403，保留操作与审批分离。
4. **堵住原生 Skyvern 绕过入口**：应用全局 JWT bridge 也改为读取同一份服务端用户上下文。`/v1/run/tasks`、`/v1/run/workflows` 等依赖 `get_current_org` 的原生接口，只接受当前数据库中仍有效的 operator/管理员企业用户。viewer、禁用用户和 Token 中伪造组织的用户都会在认证阶段被拒绝，不能绕过采购接口直接启动任务或工作流。
5. **补充最小安全测试**：增加合法、过期、伪造 Token、禁用用户、服务端角色覆盖 Token claim、采购写接口 401/403，以及原生 `get_current_org` 对 viewer/禁用用户拒绝的测试。

## 设计决策

| 决策 | 简单说明 |
|------|---------|
| JWT 只证明身份，不保存可信授权结果 | Token 只提供经签名的 `sub`；每次请求从服务端读取组织和角色，角色调整或禁用无需等待旧 Token 过期 |
| 复用 Day 2 角色和已有 dependency | 直接使用 `super_admin`、`org_admin`、`operator`、`approver`、`viewer` 及 `require_any_operator`，避免新增第二套采购权限模型 |
| 在 bridge 统一拦截原生接口 | 原生任务、工作流等大量路由都走 `get_current_org`，在 bridge 校验一次即可覆盖这些入口，不需要逐个修改 Skyvern 核心路由 |
| approver 不可运行任务 | Day 2 已要求 operator 和 approver 分离；审批角色不能借原生任务接口变成操作角色 |
| 不实现 Refresh Token、SSO 或 MFA | 当前目标是采购主流程的最小认证闭环；会话管理和企业单点登录留给后续生产化阶段 |

## 验证结果

| 检查项 | 结果 |
|------|------|
| 合法 JWT 能解码并形成当前用户上下文 | 通过 |
| 过期 Token 和错误签名 Token | 返回 401 |
| 数据库中已禁用/不存在的用户 | 返回 401 |
| Token 声称 super_admin、数据库实际为 viewer | 返回 403 |
| `smoke-task` 未认证与 viewer 调用 | 分别返回 401、403 |
| 原生 `get_current_org` 使用 viewer 或禁用用户 Token | 返回 403，无法进入 `/v1/run/tasks` 和 `/v1/run/workflows` |
| 原生 bridge 组织来源 | 使用服务端组织，不使用 Token 中伪造的 `org_id` |
| Day 1/2 与认证相关最小测试 | `70 passed` |
| 改动文件静态检查 | Ruff、`git diff --check` 通过 |

## 踩坑记录

1. Windows 会将无时区 `datetime` 的 Unix 时间戳按本地时区处理；原实现用 `datetime.utcnow().timestamp()` 生成的 `exp` 少了八小时。改用 `datetime.now(UTC)` 后，Token 过期时间与 JWT 校验时间一致。
2. 只保护采购自定义路由并不够。Skyvern 原生任务和工作流路由统一通过 `get_current_org` 调用全局 JWT bridge；如果 bridge 只按 Token 的 `org_id` 返回组织，viewer 和已禁用用户仍能绕过采购角色限制。现在 bridge 与采购路由共用服务端权限来源。
3. 原生 API Key 认证没有改动。新增限制只作用于企业 JWT，保留 Skyvern 既有 API Key 调用方式。

## 下一步

Day 4 再为采购资源增加组织、部门和品类的数据范围过滤。Refresh Token、SSO、MFA、前端登录跳转和动态权限不属于 Day 3 范围。
