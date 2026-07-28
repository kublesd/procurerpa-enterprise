# ProcureRPA Enterprise

## 项目定位
- 基于 Skyvern 的采购 RPA 演示级企业项目。
- 目标是主流程真实跑通，不追求大型生产系统完整度。
- 设计依据：docs/procurerpa_enterprise_migration_plan.md。

## 架构约束
- 优先复用 Skyvern 原生 Task、Workflow、Action 和浏览器执行链。
- 不新增第二套浏览器执行引擎。
- 不引入微服务、Kafka、复杂规则平台等非必要组件。
- 企业功能优先采用单体模块化实现。

## 安全约束
- 密码、Token、供应商银行账户和敏感采购数据不得发送给 LLM。
- 金额、提交、删除、审批等决策必须由确定性规则控制。
- LLM 只能用于解释、字段映射和非决定性补充判断。

## 开发规则
- 修改前检查真实调用方、路由注册和数据库模型。
- 不根据 README 推断实现状态。
- 不修改当前任务以外的文件。
- 每次实现必须运行最小相关测试。
- 无法验证的内容必须明确说明。
- 每个 Day 完成后更新 summary 和 code list。

