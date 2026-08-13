# Day 1 — 项目基础搭建

## 今日改动

今天完成 ProcureRPA 的基础项目搭建，后续可以在这个基础上继续开发采购功能。

1. **项目改名**：将项目说明、环境变量模板和 README 改为 ProcureRPA Enterprise。
2. **增加采购入口**：新增采购模块和状态检查接口：
   `GET /api/v1/enterprise/procurement/health`。
   该接口可匿名访问，用来查看 API、数据库、Redis 和浏览器能否正常使用。
3. **保留 Skyvern 能力**：采购功能直接接在现有 Skyvern 应用中，原有的任务和工作流接口仍可使用。
4. **增加开发测试接口**：开发环境可调用
   `POST /api/v1/enterprise/procurement/smoke-task` 创建一次真实的 Skyvern 任务。
   只有管理员、同一组织和白名单网址可以调用，且不能传入密码、Token 或采购数据。
5. **整理本地运行环境**：提供 PostgreSQL、Redis、MinIO、后端和前端五个服务的 Docker Compose 配置；补充 Dockerfile、依赖锁文件和常用 Makefile 命令。
6. **补充测试**：增加基础路由测试、安全测试和可选的真实 E2E 测试。

## 设计决策

| 决策 | 简单说明 |
|------|---------|
| 不新建第二套 RPA 引擎 | 直接使用 Skyvern 已有的浏览器任务和工作流能力 |
| 采购代码放在 `enterprise/procurement/` | 后面的采购功能都放在这个目录，位置清楚 |
| 状态检查允许匿名访问 | 方便本地和 Docker 判断服务是否正常；接口不返回密码或业务数据 |
| 开发测试接口只在开发环境开放 | 避免测试接口在生产环境创建浏览器任务 |
| MinIO 暂时不影响启动 | Day 1 还没有使用 MinIO 保存采购文件，后面需要时再接入 |

## 验证结果

| 检查项 | 结果 |
|------|------|
| Day 1 相关 Python 测试 | `32 passed, 1 skipped` |
| Python 依赖检查 | `pip check` 通过 |
| 前端安装和构建 | `npm ci`、`npm run build` 通过 |
| Docker Compose 配置 | `docker compose config` 通过 |
| Docker 启动 | 未完成，Docker Hub 网络超时导致 PostgreSQL 镜像无法拉取 |

## 踩坑记录

1. Windows 默认使用 GBK 编码，读取 UTF-8 的 Skyvern JavaScript 文件时会报错；已改为明确使用 UTF-8 读取。
2. `docker compose config` 通过只代表配置没问题，不代表容器一定能启动；本机启动时被 Docker Hub 网络问题阻塞。
3. 数据库迁移目前有两个 head，Day 2 新增采购表之前需要先整理迁移关系。

## 下一步

Day 2 再开始做采购基础数据，例如组织、部门和采购品类；不要提前加入审批、风险、供应商或订单功能。
