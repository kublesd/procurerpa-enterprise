# Day 3 — JWT 认证与采购角色权限代码清单

## 新增文件

| 文件 | 用途 |
|------|------|
| `tests/unit/test_auth_bridge.py` | 验证企业 JWT 通过原生 `get_current_org` 时，viewer 和禁用用户被拒绝，operator 使用服务端组织而不是 Token 中的组织 |
| `summaries/day_3_summary.md` | 记录 Day 3 的认证流、角色限制、防绕过效果和验证结果 |
| `summaries/day_3_code_list.md` | 记录 Day 3 新增和修改的文件 |

## 修改文件

| 文件 | 修改内容 |
|------|---------|
| `enterprise/auth/jwt_service.py` | JWT 仍使用现有 claims 和签名算法；改为使用 `datetime.now(UTC)` 写入 `exp`，修复 Windows 本地时区导致合法 Token 提前过期的问题 |
| `enterprise/auth/dependencies.py` | `get_current_user` 验签后按 `sub` 查询 `EnterpriseUserModel` 和 Day 2 的角色、业务线、特殊权限表；只返回服务端读取的 `UserContext`，禁用或删除用户返回 401 |
| `enterprise/auth/bridge.py` | 原生 Skyvern JWT bridge 改为复用可信用户加载逻辑；仅当前数据库中的 operator、org_admin、super_admin 能解析为组织或用户 ID，阻止企业 JWT 直接绕过采购角色运行原生任务/工作流 |
| `enterprise/auth/routes.py` | `/api/v1/enterprise/auth/me` 的说明改为返回服务端可信权限上下文，和实际认证行为保持一致 |
| `enterprise/procurement/routes.py` | `POST /api/v1/enterprise/procurement/smoke-task` 从 platform_admin 限制改为复用 `require_any_operator`，使采购操作员可执行开发任务，viewer/approver 仍被拒绝 |
| `tests/unit/test_auth_dependencies.py` | 增加过期 Token、伪造签名、禁用用户，以及“Token 为 super_admin、服务端为 viewer”时拒绝操作的测试 |
| `tests/unit/test_day_1_smoke_security.py` | 调整 smoke-task 安全测试，覆盖未认证 401 和服务端 viewer 403，并保持组织、白名单、幂等和任务失败场景 |

## 删除文件

无。

## 备注

Day 3 复用既有 JWT、FastAPI dependency、Day 2 角色表和 Skyvern 的组织认证入口；没有新建认证服务、SSO、MFA、Refresh Token、动态权限或前端认证。Day 4 才处理采购数据的组织、部门和品类范围隔离。
