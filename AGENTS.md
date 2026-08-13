# ProcureRPA Enterprise Agent 入口

## 当前目标

当前开发路线是：以 `ProcureRPA Enterprise` 为基线，先完成 **ProcureRPA 企业能力的采购语义功能对等**，再单独处理真实 Skyvern 接链、持久化和安全硬化。

第一阶段允许直接沿用上游的独立 Planner/Executor、Skill Pipeline、模板、内存 store、启动 demo seed、模拟 handler、模型路由和 Action Cache。它们必须明确标记为演示/模拟能力，但不能因为尚未持久化或尚未接入原生 Skyvern 链而阻断适配。

现有已验证采购主链继续保留，不回退、不重写：受控供应商页 → procurement API → 原生 Skyvern Task/Artifact → SupplierQuote → Decimal 比价 → 审批/审计/Dashboard。

## 每次开始

1. 执行 `git status --short`，保留所有无关未提交修改。
2. 阅读 [`PROGRESS.md`](PROGRESS.md) 和 [`DECISIONS.md`](DECISIONS.md)。
3. 只读取当前能力对应的一份专题文档和真实调用方，不一次加载全部资料。
4. 每次只领取一个功能对等阶段；达到该阶段验收后停止。

## 硬约束

- 真实源码、路由和运行证据高于旧计划、README 和历史 summary。
- 第一阶段以“采购语义可演示”为完成定义；不得擅自把模拟/内存实现升级为数据库、Redis 或原生 Skyvern 集成。
- 第二阶段债务不得被宣传为已解决或生产级能力；统一记录在功能对等路线和 `PROGRESS.md`。
- 现有真实采购主链不能因功能对等适配而退化；独立适配链不能冒充该真实主链。
- 密钥、Token、密码、Webhook、银行账户和真实敏感采购数据不得进入代码、日志、测试、文档或 LLM。第一阶段 LLM 演示只使用受控、合成或已脱敏数据。
- 金额、提交、删除、审批和推荐等真实采购决定仍由服务端确定性规则控制；上游 LLM/模拟决策只能用于隔离演示。
- 先复用当前仓库实现、标准库和已安装依赖；不为未来需求增加抽象、依赖或配置。
- 不覆盖、清理或格式化当前任务之外的工作区修改。

## 按需文档

- [功能对等阶段开发指南](docs/procurement_rpa_development_guide.md)：实现某一阶段时读。
- [架构与两阶段调用链](docs/agent_architecture.md)：修改路由、Agent、Skill、Workflow、Skyvern 接线或状态时读。
- [安全与采购数据规则](docs/agent_security_rules.md)：涉及权限、金额、LLM、日志、文件、缓存或审批时读。
- [开发、验证与交接流程](docs/agent_development_workflow.md)：编码、验证、更新状态或交接时读。

## 结束任务

运行当前阶段的最小验证和 `git diff --check`，再更新 `PROGRESS.md`；只有重要取舍才追加 `DECISIONS.md`。最终汇报修改文件、实际验证、未验证项和保留债务。
