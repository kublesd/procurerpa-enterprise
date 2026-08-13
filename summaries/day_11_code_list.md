# Day 11 代码清单

## 新增

- `skyvern-frontend/public/procurement/vendor-a.html`：受控供应商 A 报价页。
- `skyvern-frontend/public/procurement/vendor-b.html`：受控供应商 B 报价页。
- `tests/unit/test_day_11_quotes.py`：抽取字段/置信度校验和原生 TaskRequest 单测。
- `tests/integration/test_day_11_quotes_e2e.py`：可选真实栈双供应商验收测试，需显式设置 `PROCUREMENT_QUOTE_E2E=1`。

## 修改

- `enterprise/procurement/routes.py`：新增报价提取任务、Artifact 绑定校验和跨 Task 比价；保留原生 Skyvern 执行链。
- `scripts/smoke_procurement.py`：改为双供应商报价采集、Task/报价/Artifact/审计检查。
- `skyvern/config.py`、`.env.example`：补充两条受控报价页默认 allowlist。
- `docs/PROGRESS.md`、`docs/DECISIONS.md`：更新 Day11 状态和证据绑定决策。

## 未做

- 未修改 `enterprise/agent`、`enterprise/skills`，未引入第二套浏览器运行时。
- 未修改本机 `.env`，未运行真实 Docker/LLM/Chromium smoke。
