# ProcureRPA 能力与债务索引

## 文档用途

本页负责采购能力边界、真实/模拟关系和仍需显式保留的技术债，不负责声明当前任务、当前分支、最新验证或下一阶段。

- 当前目标、活动任务和最新证据：[`../PROGRESS.md`](../PROGRESS.md)
- 通用开发与验证流程：[`agent_development_workflow.md`](agent_development_workflow.md)
- S1～S9 历史阶段契约：[`procurement_rpa_development_guide.md`](procurement_rpa_development_guide.md)
- 架构和安全边界：[`agent_architecture.md`](agent_architecture.md)、[`agent_security_rules.md`](agent_security_rules.md)

P1～P6 与 S1～S9 均是已执行路线的历史名称，不能从本页直接领取。仓库 Git 历史重写后，旧 commit ID 只作为历史标签；是否可复现必须以当前 Git 对象和本次运行证据为准。

## 长期边界

1. **保留真实采购主链。** 已有 PostgreSQL、权限、审批、审计、Artifact 和 Skyvern 报价链只能复用或增强，不能改回 demo。
2. **模拟能力显式隔离。** fake page、内存 store、模拟 Executor、固定成本等只允许进入标记过的演示或兼容入口。
3. **真实决定保持确定性。** 金额、风险下限、审批、提交、删除和供应商推荐由服务端规则决定。
4. **证据等级不混用。** mock、用户报告、历史记录和本次真实运行分别标记；外部服务不可用时写 `unverified`。
5. **债务可见但不自动扩展范围。** 任何债务都需要在 `PROGRESS.md` 中形成有界活动任务后才能实施。

## 已验证真实采购主链

```text
受控供应商页
  → POST /enterprise/procurement/quote-task
  → task_v1_service.run_task()
  → 原生 Skyvern executor / Chromium
  → Task + Artifact + SupplierQuote
  → Decimal 确定性比价
  → 采购工作台 / 审批 / 审计 / PostgreSQL Dashboard
```

`demo_procurement_parity.py` 展示的是功能对等适配能力，不替代这条链，也不能作为真实链验收证据。

## 能力索引

| 能力 | 主要实现责任 | 真实/模拟边界 | 关键不变量 |
| --- | --- | --- | --- |
| 认证与租户范围 | `enterprise/auth/`、`enterprise/tenant/` | 生产 API 从同组织服务端事实重载范围 | 客户端字段不能扩大组织、部门或品类权限 |
| 风险与审批 | `enterprise/procurement/`、`enterprise/approval/` | 真实规则与 demo LLM 判断分离 | 申请人不能自批；决定可审计且幂等 |
| 报价与比价 | `enterprise/procurement/` | 真实 SupplierQuote 绑定 Task/Artifact | Decimal 计算；LLM 输出校验后才可入库 |
| Artifact 与审计 | `enterprise/audit/`、Skyvern Artifact | 真实文件存 MinIO/object URI；演示摘要需标记 | 同组织证据；日志不含预签名 URL 或敏感正文 |
| Planner/Coordinator | `enterprise/agent/` | 持久 Session 路径使用 PostgreSQL；无 Session 兼容路径仅供模拟 | 恢复只信数据库状态；写入失败不返回成功 |
| Skill 与模板 | `enterprise/skills/`、`enterprise/workflows/` | 生产编译结果交给原生 Skyvern；fake pipeline 仅供 demo/test | 不创建第二套浏览器运行时 |
| 人工核验 | `procurement_human_reviews` 与相关 API | 真实失败形成持久 Review；内存 helper 仅供演示 | 租户隔离、授权处置、审计和重启可读 |
| Action Cache | Skyvern Agent 调用点与 Redis | 生产缓存使用 Redis；内存 store 仅供 demo | 组织、DOM、目标、模型和 schema 隔离；敏感动作不缓存 |
| 模型路由 | Skyvern LLM Registry 与采购路由 | 生产只使用已注册 key；demo tier helper 不代表真实调用 | 无可用模型时失败关闭或进入 Review |
| 成本 Dashboard | PostgreSQL Step token/cost | 真实 API 不读取固定 demo facts | Decimal 聚合；未知成本不估算成真实值 |
| 集成验收 | Compose、pytest、Vitest、smoke scripts | 历史成功不覆盖当前未验证实现 | quotes、controls、重启、租户和日志证据分别记录 |

## 历史两阶段路线

| 阶段 | 历史目标 | 当前用途 |
| --- | --- | --- |
| P1～P6 | 取得采购语义功能对等，允许明确标记的内存、fake 和 demo 路径 | 解释演示兼容代码来源，不再领取 |
| S1～S8 | 逐项接入 PostgreSQL、原生 Skyvern、Redis、真实模型配置和 Step 成本 | 复核实现与验收边界，不再领取 |
| S9 | 安全硬化、SIT 和生产 fallback 清理 | 区分工程门与真实外部 smoke 的剩余验证 |

阶段顺序、原始完成门和禁止项保留在历史实施契约中。某项需要返工时，应根据当前源码重新定义独立任务，不能假定旧阶段描述仍与调用方一致。

## 保留债务与开放问题

以下项目是能力限制，不是自动排期：

- 第一阶段无 handler Executor、内存 Action Cache、demo 模型路由和固定成本 helper 仍保留在演示/兼容路径；生产路由不得调用。
- Skill/template 实例本身尚未形成完整持久化运行时；fake-page pipeline 仍只能作为演示证据。
- 敏感模板参数尚未接入生产凭据存储；受控合成验收不代表真实凭据链可用。
- Planner、Workflow、审批、页面恢复和审计的状态/事务仍未完全统一。
- 个性化输入、上传和选项动作因敏感值边界不进入 Action Cache，除非后续形成 secrets-safe schema。
- 审批 category/routing 尚未独立持久化；多级审批、采购阈值配置和完整暂停/继续模型仍未实现。
- 上游 Prompt/page context 的真实输入最小化、访问控制和保留策略仍需单独安全任务。
- 当前标准源码的 `quotes` 真实 smoke 在日志修复后因 Gemini 限流未验证；它只是一项外部验证差距，不等同于新的开发阶段。

任何债务进入实施前，必须在 `PROGRESS.md` 写明目标、范围外、验收、验证、授权边界和停止条件。
