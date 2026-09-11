# ProcureRPA Enterprise Agent 入口

## 当前工作入口

[`PROGRESS.md`](PROGRESS.md) 是当前目标、活动任务、最新证据、阻塞和下一步的唯一事实源。没有明确的“活动任务”时，不得根据历史路线自行领取 P1～P6、S1～S9 或扩展生产化范围。

现有采购主链必须保留：受控供应商页 → procurement API → 原生 Skyvern Task/Artifact → SupplierQuote → Decimal 比价 → 审批/审计/Dashboard。

## 每次开始

1. 执行 `git status --short`，记录并避开所有无关工作区修改。
2. 阅读 [`PROGRESS.md`](PROGRESS.md) 和 [`DECISIONS.md`](DECISIONS.md)。
3. 为当前任务写一句完成定义、范围外事项和最小验证。
4. 只读取一份最相关的专题文档、真实调用方和代表性测试，不一次加载全部资料。
5. 每次只处理一个有明确停止条件的任务；达到验收或触发范围/风险边界后停止。

## 硬约束

- 真实源码、路由、数据库迁移图和本次运行证据高于旧计划、README、历史 commit ID 和 summary。
- `PROGRESS.md` 之外的路线、指南和 summary 不得声明当前任务或下一任务。
- 演示、模拟、内存或未接入能力必须标记为 `demo`、`simulated`、`memory_demo`、`not_connected` 或等价明确标签，不能冒充真实采购主链。
- 现有真实采购主链不能因适配、兼容或演示改动而退化。
- 密钥、Token、密码、Webhook、银行账户和真实敏感采购数据不得进入代码、日志、测试、文档或 LLM；演示只使用受控、合成或已脱敏数据。
- 金额、提交、删除、审批和推荐等真实采购决定由服务端确定性规则控制；LLM 或模拟结果不能直接决定。
- 先复用仓库实现、标准库和已安装依赖；不为未来需求增加抽象、依赖或配置。
- 不覆盖、清理、恢复或格式化当前任务之外的工作区修改。
- 本地修改权限不包含 commit、push、分支切换、部署、生产/外部写入、凭据访问或破坏性数据操作；这些动作必须获得单独明确授权。

## 按需文档

- [能力与债务索引](docs/procurement_completion_gap.md)：确认能力边界、真实/模拟状态和保留债务时读；不从中领取任务。
- [S1～S9 历史实施契约](docs/procurement_rpa_development_guide.md)：仅在复核或重开对应阶段时读相关小节。
- [架构与两阶段调用链](docs/agent_architecture.md)：修改路由、Agent、Skill、Workflow、Skyvern 接线或状态时读。
- [安全与采购数据规则](docs/agent_security_rules.md)：涉及权限、金额、LLM、日志、文件、缓存或审批时读。
- [开发、验证与交接流程](docs/agent_development_workflow.md)：编码、验证、更新状态或交接时读。

## 结束任务

运行当前任务的最小验证和 `git diff --check`，确认改动未超出已批准路径，再更新 `PROGRESS.md`。只有影响后续工作的重大取舍才追加 `DECISIONS.md`。

最终汇报必须列出修改文件、实际验证及环境、未验证项、保留债务和停止原因；计划运行、历史运行、用户报告和本次直接观察必须明确区分。
