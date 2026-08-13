# Day 10 — 报价领域与确定性比价

## 做了什么

- 在 `enterprise/procurement/` 增加 `SupplierQuoteModel`，持久化 Task、组织、部门、品类、供应商、物料、数量、单位、CNY 含税单价、运费、MOQ、交期和 Artifact 证据。
- 增加 `ent_008` Alembic 迁移，并用数据库约束/触发器校验报价与 Task、TaskExtension、Artifact 的组织边界。
- 增加 Decimal 标准化和确定性比较：按含税到岸单价排序，交期、供应商 ID、报价 ID 作为稳定 tie-breaker；不满足 MOQ 的报价不推荐。
- 注册报价创建、列表、详情和比较 API；组织 ID 从认证用户服务端上下文取得，读查询复用租户范围过滤，写入要求 operator 或更高角色。

## 真实调用链

`HTTP /api/v1/enterprise/procurement/quotes*` → `enterprise.auth.dependencies` → `tenant_context_for`/`apply_tenant_filter` → SQLAlchemy `SupplierQuoteModel` → `comparison.compare_quotes`。

Day 10 不启动浏览器，也没有接入第二套 Agent/Executor；Day 11 再把报价采集接到 Skyvern Task 的提取结果。

## 验证结果

- `.\.venv\Scripts\python.exe -m pytest tests -q`：`528 passed, 2 skipped`
- `.\.venv\Scripts\python.exe -m ruff check enterprise/procurement tests/unit/test_day_10_quotes.py alembic/versions/2026_03_14_0008_procurement_quotes.py`：通过
- `.\.venv\Scripts\python.exe -m compileall -q enterprise/procurement alembic/versions/2026_03_14_0008_procurement_quotes.py tests/unit/test_day_10_quotes.py`：通过
- `.\.venv\Scripts\alembic.exe heads`：`ent_008 (head)`

## 未验证

- 真实 PostgreSQL 的 upgrade/downgrade 和触发器联调未执行；当前环境未配置 `DAY2_POSTGRES_DATABASE_URL`。

## 后续建议

- Day 11 将受控供应商页面的 Skyvern 提取结果校验后写入本报价模型，并保留 Task/Artifact 追溯关系。
