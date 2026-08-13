# Day 7 — 企业微信与钉钉通知代码清单

## 新增文件

| 文件 | 用途 |
| --- | --- |
| `summaries/day_7_summary.md` | Day 7 功能、设计决策、踩坑和验证结果 |
| `summaries/day_7_code_list.md` | Day 7 新增和修改文件清单 |

## 修改文件

| 文件 | 修改内容 |
| --- | --- |
| `enterprise/notification/channels.py` | 收敛企业微信/钉钉 HTTP adapter，统一脱敏错误分类 |
| `enterprise/notification/templates.py` | 新增脱敏采购审批模板和订单异常模板 |
| `enterprise/notification/dispatcher.py` | 实现企业微信优先、钉钉降级和不影响业务的安全发送入口 |
| `enterprise/procurement/routes.py` | 审批提交后调度后台通知，幂等命中不重复发送 |
| `skyvern/config.py` | 增加审批地址和 `SecretStr` Webhook 配置 |
| `.gitignore` | 忽略本地 `.env`；该文件同时从 Git 索引解除跟踪 |
| `.env.example` | 增加不含真实密钥的通知配置，并改为显式启用 LLM provider |
| `docker-compose.yml` | 将通知环境变量传入 Skyvern 容器，默认不启用无 Key 的 Gemini |
| `README.md` | 说明基础 API 无需 LLM Key，浏览器任务运行前才需配置 provider |
| `tests/unit/test_notification.py` | 覆盖模板、双渠道、错误、超时、fallback 和脱敏 |
| `tests/unit/test_day_1_smoke_security.py` | 覆盖审批创建到通知的真实调用点和幂等行为 |

## 删除文件

| 文件 | 说明 |
| --- | --- |
| `.env` | 仅从 Git 索引删除，本地文件和本地 Key 保留 |

## 备注

未新增通知表、公开 API、接收人目录、Outbox、Redis 重试队列或 worker。订单异常模板将在真实订单服务出现后接入。
