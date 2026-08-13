# ProcureRPA Enterprise

### 企业采购 AI 浏览器自动化平台 · 采购执行 / 风险审批 / 全程审计


---

## 这个项目是什么

ProcureRPA Enterprise 是一个基于 [Skyvern](https://github.com/Skyvern-AI/skyvern) 二次开发的采购 RPA 演示级企业项目。

Skyvern 使用 LLM 和视觉理解操作网页，不依赖容易随页面改版失效的固定 XPath。本项目保留它原生的 Task、Workflow、Action、浏览器会话和执行链，在同一个 FastAPI 应用中增加采购权限、数据隔离、风险判断、人工审批、消息通知和审计留痕，让一条采购任务能够从发起一直走到浏览器执行完成。

---

## 为什么要做这个改造

原生浏览器自动化解决了“怎么操作网页”，但企业采购还需要回答另外几个问题：

- 谁可以发起采购任务，又能看到哪些部门和品类的数据？
- 金额、供应商资质或报价异常时，系统应该继续执行还是等待审批？
- 谁可以审批，如何避免申请人审批自己的任务？
- 采购动作、审批决定和报价文件怎样安全留痕？
- 通知或审计服务临时失败时，是否会阻断已经完成的采购业务？

ProcureRPA 把这些采购规则接到 Skyvern 的真实执行入口上。关键决定由确定性规则控制，LLM 只做页面理解和脱敏文本的补充判断，不接收密码、Token、供应商银行账户、原始报价等敏感信息。

---

## 核心改造内容

### 采购组织、角色与数据隔离

系统使用组织、部门、采购品类和角色共同限定数据范围。采购员只能操作获授权部门和品类的任务，审批人负责本部门审批，采购管理员可以查看本组织数据。JWT 只用于确认身份，真实角色和权限每次都从数据库读取，用户被停用或权限变化后会立即生效。

Skyvern 原生 Task 和 Workflow 入口也复用同一套企业认证桥接，普通查看人不能绕过采购接口直接启动浏览器任务。

### 确定性的采购风险判断

采购任务提交前会检查金额、供应商状态、供应商资质、报价偏离和操作类型。金额边界、无效资质、单一来源、预付款、银行账户变更等规则由普通代码判断，不交给 LLM 决策。

LLM 只能读取已经脱敏的采购说明并补充提示，不能降低规则已经判定的风险等级。输入不合法时会在任务进入浏览器执行前直接拒绝，避免错误采购数据继续流转。

### 高风险任务人工审批

低风险任务直接进入 Skyvern 原生执行链；高风险和严重风险任务只创建 Task 与审批记录，不提前启动浏览器 Agent。

审批通过后，申请人调用继续接口恢复同一条 Skyvern Task；审批拒绝后，原任务被取消。申请人不能审批自己的任务，跨组织、跨部门和重复决定都会被拒绝。当前演示采用单级审批，足以覆盖“采购员发起 → 审批人决定 → 原任务继续”的闭环。

### 企业微信与钉钉通知

高风险审批创建后，系统优先发送企业微信群机器人通知，失败时再尝试钉钉。通知只包含审批编号、任务编号、部门、风险等级、处理时限和审批中心链接，不发送采购描述、银行账户或 Webhook Token。

通知在接口响应后执行。渠道未配置或发送失败不会影响已经创建的采购任务和审批记录。

### 采购审计与报价文件

风险判断、采购提交、审批创建、审批决定、批准后继续和通知结果都会写入 PostgreSQL 审计日志。密码、Token、Webhook、银行账户、手机号、身份证号和供应商报价等内容会在入库前递归脱敏。

报价文件首版只接收 PDF。接口会校验任务权限、扩展名、真实 PDF 文件头和 10 MB 大小限制，再把文件存入 MinIO，并复用 Skyvern Artifact 关联原任务。访问文件时只返回短期预签名地址。

## 项目架构

```text
procurerpa-enterprise/
├── skyvern/                       # Skyvern 原生 Agent、Task、Workflow 和浏览器执行链
├── enterprise/                    # 企业采购扩展层
│   ├── auth/                      # JWT 登录、角色权限和 Skyvern 认证桥接
│   ├── tenant/                    # 组织、部门和品类数据隔离
│   ├── procurement/               # 采购任务、风险接入和演示数据
│   ├── approval/                  # 单级审批、审批路由和任务继续
│   ├── notification/              # 企业微信 / 钉钉通知
│   ├── audit/                     # 审计、递归脱敏和报价 PDF
│   ├── agent/                     # 第一阶段 Planner / Executor / Coordinator 适配
│   ├── skills/                    # 7 个可组合采购 Skill
│   ├── workflows/                 # 6 个声明式采购模板
│   ├── llm/                       # JSON 容错、人工接管、模型路由和 Action Cache
│   └── dashboard/                 # 真实采购统计与后续 demo 成本区
├── skyvern-frontend/              # React 前端和企业页面
├── alembic/                       # Skyvern 与采购扩展数据库迁移
├── scripts/
│   ├── demo_procurement_parity.py # P1～P5 采购语义单入口演示
│   ├── seed_procurement_demo.py   # 唯一采购演示数据 seed
│   └── smoke_procurement.py       # 采购主链一键验收
├── tests/                         # 最小相关单元测试与集成测试
├── summaries/                     # 每个 Day 的功能、决策和验证记录
├── docker-compose.yml             # PostgreSQL、Redis、MinIO、API 和前端
├── docker-compose.dev.yml         # 本地源码挂载与热重载
├── docker-compose.prod.yml        # 演示部署覆盖配置
└── Makefile                       # 常用开发命令
```

---

## 技术栈

| 层次 | 技术 |
| --- | --- |
| AI 浏览器自动化 | Skyvern + Playwright + Chromium |
| 后端 | FastAPI + Python 3.11～3.13 |
| 数据库 | SQLAlchemy 2.0 + PostgreSQL 14 + Alembic |
| 缓存与协调 | Redis 7 |
| 文件存储 | MinIO + Skyvern Artifact |
| 认证授权 | JWT + 组织 / 部门 / 品类 / 角色权限 |
| 前端 | React 18 + TypeScript + Vite + ECharts |
| 容器化 | Docker Compose |
| 测试 | pytest + pytest-asyncio + Vitest |

---

## 快速启动

### 1. 准备环境变量

```powershell
git clone https://github.com/kublesd/procurerpa-enterprise.git
Set-Location procurerpa-enterprise
Copy-Item .env.example .env
```

编辑 `.env`，至少填写：

```dotenv
POSTGRES_PASSWORD=your-local-password
MINIO_ROOT_USER=your-local-user
MINIO_ROOT_PASSWORD=your-local-password
SECRET_KEY=your-random-secret
```

可以用 Python 标准库生成本地 JWT 密钥：

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

API 可以在没有 LLM Key 时启动；运行真实浏览器任务前，需要在 `.env` 中启用一个模型供应商，例如：

```dotenv
LLM_KEY=OPENAI_GPT4O
ENABLE_OPENAI=true
OPENAI_API_KEY=your-api-key
```

真实密钥只能保存在本地 `.env`，不要提交到 Git。

### 2. 启动服务

```powershell
docker compose config
docker compose up --build
```

本地开发需要热重载时：

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

服务地址：

| 服务 | 地址 |
| --- | --- |
| ProcureRPA / Skyvern API | `http://localhost:18000` |
| 前端 | `http://localhost:18080` |
| PostgreSQL | `localhost:15432` |
| Redis | `localhost:16379` |
| MinIO API | `http://localhost:19000` |
| MinIO Console | `http://localhost:19001` |

健康检查：

```powershell
curl.exe -f "http://localhost:18000/api/v1/enterprise/procurement/health?ready=true"
```

