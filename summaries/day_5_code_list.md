# Day 5 — 采购风险识别代码清单

## 新增文件

| 文件 | 用途 |
| --- | --- |
| `alembic/versions/2026_03_10_0004_procurement_risk_result.py` | 为 `task_extensions` 增加风险原因和 JSON 规则证据 |
| `summaries/day_5_summary.md` | Day 5 功能、设计决策和验证结果 |
| `summaries/day_5_code_list.md` | Day 5 新增和修改文件清单 |

## 修改文件

| 文件 | 修改内容 |
| --- | --- |
| `enterprise/approval/risk_keywords.py` | 将金融关键词库替换为固定 CNY、报价偏离和采购操作类型规则常量 |
| `enterprise/approval/risk_detector.py` | 实现结构化采购风险上下文、5 类确定性规则、可解释结果和 LLM 只升不降边界 |
| `enterprise/auth/models.py` | 在既有 `TaskExtensionModel` 增加 `risk_reason`、`risk_result` |
| `enterprise/procurement/routes.py` | 采购提交请求增加结构化风险输入，创建 Skyvern Task 前评估并持久化，查询接口返回风险证据 |
| `tests/unit/test_risk_detector.py` | 改为采购规则、边界、缺数据、LLM 降级与敏感输入隔离测试 |
| `tests/unit/test_day_1_smoke_security.py` | 验证真实提交链调用风险函数并持久化 high 风险结果 |
| `tests/unit/test_day_4_procurement_isolation.py` | 补齐任务风险结果，保持采购范围查询回归 |
| `tests/integration/test_e2e_flow.py` | 将原金融风险调用改为结构化采购风险调用 |

## 删除文件

无。

## 备注

未新增风险表、规则管理页面、外部 LLM adapter 或独立采购申请模型；风险识别复用当前唯一的 Skyvern Task 采购提交链。
