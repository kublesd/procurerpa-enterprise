# Day 1 — 项目基础搭建代码清单

## 新增文件

| 文件 | 用途 |
|------|------|
| `.dockerignore` | Docker 构建时不复制缓存、虚拟环境和本地密钥 |
| `enterprise/procurement/__init__.py` | 采购模块入口 |
| `enterprise/procurement/routes.py` | 采购状态检查和开发测试接口 |
| `requirements.lock` | 固定 Python 依赖版本 |
| `tests/unit/test_day_1_baseline.py` | 检查采购路由和 Skyvern 路由是否正常 |
| `tests/unit/test_day_1_smoke_security.py` | 检查开发测试接口的管理员、组织和网址限制 |
| `tests/integration/test_day_1_smoke_e2e.py` | 可选的真实浏览器任务测试 |
| `summaries/day_1_summary.md` | Day 1 总结 |
| `summaries/day_1_code_list.md` | Day 1 文件清单 |

## 修改文件

| 文件 | 修改内容 |
|------|---------|
| `.env.example` | 改为 ProcureRPA 的环境变量示例，不再提供默认密码 |
| `.gitignore` | 忽略 npm 本地缓存 |
| `Dockerfile` | 构建并启动后端服务 |
| `Dockerfile.ui` | 构建前端服务 |
| `docker-compose.yml` | 配置 PostgreSQL、Redis、MinIO、后端和前端五个服务 |
| `Makefile` | 提供启动、测试和迁移命令 |
| `README.md` | 更新项目说明、启动方法和测试方法 |
| `pyproject.toml` | 更新项目名称和 Python 依赖 |
| `enterprise/__init__.py` | 更新企业扩展包说明 |
| `enterprise/auth/dependencies.py` | 增加开发测试接口的管理员检查 |
| `enterprise/tenant/middleware.py` | 允许匿名访问采购状态检查 |
| `skyvern/config.py` | 检查生产环境密钥，并配置开发测试网址白名单 |
| `skyvern/forge/api_app.py` | 把采购路由注册到现有 FastAPI 应用 |
| `skyvern/webeye/scraper/scraper.py` | 修复 Windows 下读取 UTF-8 文件失败的问题 |
| `skyvern-frontend/src/__tests__/Icon.test.tsx` | 删除无效 TypeScript 注释 |
| `skyvern-frontend/src/__tests__/ScreenshotDiff.test.tsx` | 删除未使用变量，保证前端能构建 |

## 删除文件

无。

## 备注

Day 1 只完成项目基础、状态检查、开发测试接口和测试。采购表、供应商、报价、采购申请、订单、审批和风险功能都留到后续 Day 开发。
