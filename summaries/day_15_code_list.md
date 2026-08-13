# Day 15 代码清单

## 1. 修改文件及业务作用

- `Makefile`
  - 增加后端/前端测试、前端构建、统一 verify、唯一采购 seed、quotes smoke 和 controls SIT 入口。
- `README.md`
  - 统一采购演示账号、seed 命令、smoke 输出、Makefile 速查和 Day 10～15 状态。

## 2. 删除文件及业务作用

- `enterprise/demo_seed.py`
  - 删除未被调用的金融内存演示 seed。
- `scripts/seed_demo_data.py`
  - 删除旧 SQL seed runner。
- `tests/fixtures/seed_demo_data.sql`
  - 删除旧金融数据库 fixture。
- `tests/sit_test.py`
  - 删除已被 Day 14 真实采购 scenarios 替代的旧金融 SIT。
- `skyvern-frontend/src/routes/enterprise/permissions/PermissionsPage.tsx`
  - 删除已从运行路由和导航下线的静态权限页面。
- `skyvern-frontend/src/routes/enterprise/llm/LLMMonitorPage.tsx`
  - 删除已从运行路由和导航下线的静态 LLM 监控页面。

## 3. 复用的已有入口

- `enterprise/procurement/seed.py` 的 `seed_procurement_data()`。
- `scripts/smoke_procurement.py` 的 quotes/controls scenarios。
- 当前审批、审计、Dashboard、采购工作台真实 API 和 Skyvern 原生执行链。

## 4. 验证命令

```powershell
docker compose exec skyvern python -m pytest tests/unit/test_day_2_procurement.py tests/unit/test_dashboard.py -q
docker compose exec skyvern python scripts/seed_procurement_demo.py
docker compose exec skyvern python scripts/seed_procurement_demo.py
docker compose config
npm.cmd run build
git diff --check
```

## 5. 明确不在本 Day 范围内

- 不新增数据库模型、迁移、采购字段、浏览器执行器或 seed 格式。
- 不清理历史数据库演示记录、通用 i18n 文案或与采购主链无关的旧单元测试常量。
- 不把 Day 14 已通过的真实浏览器 smoke 重新宣称为 Day 15 新验证。
