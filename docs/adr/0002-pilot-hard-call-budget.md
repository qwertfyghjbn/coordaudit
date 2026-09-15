# 0002. Pilot 以团队调用许可作为唯一严格模型预算

## 状态

Accepted

## 决策

N=4 pilot 的每个 condition 共享 32 个原子 model-call permits，不设置 per-agent call cap；单次 output ceiling 为 1024 tokens。请求实际发给 provider 即消耗 permit，timeout、provider error 仍计 attempted call，retry 必须取得新 permit。Token stop threshold 只是允许一次 in-flight overshoot 的安全软阈值，provider 报告的实际 token 用量作为资源结果完整记录且不补偿。

## 理由

Provider 只能在响应后给出权威 token usage，无法用它实现精确的调用前 token admission。固定 per-agent 配额又会压平 T 的自发综合分工，并在未来结构性惩罚 manager/aggregator；团队共享 permit 能冻结总调用机会，同时把各 Agent 的实际资源分配保留为 coordination outcome。

## 后果

- S1、P4、B4、T4 使用同一个 32-permit contract；Agent 循环上限可设为 32，但不构成额外配额。
- 日志必须区分 attempted、successful、timeout、provider-error 与 retry calls，并记录 permit 的申请、发放、拒绝和所属 Agent。
- 单个可恢复的随机基础设施失败标记为 `valid_with_infrastructure_warning`；同一 run 累计两个随机基础设施失败 attempt，或一次失败导致 Agent 终止且无后续成功响应时，该 run 与所在 matched block 立即标为 infrastructure-invalid。
- Block invalid 后停止当前 run 和尚未执行的 conditions，保留全部产物并整体重跑；实现/隔离错误直接暂停采样并修复，重复出现的 provider 类故障也升级为暂停调查。

## 实现对齐（2026-09-15）

`BudgetTracker.acquire_call_permit()` 在 provider 请求前原子发放 permit，并由 `settle_call_permit()` 以 `succeeded`、`timeout` 或 `provider_error` 结算且从不退还。`AgentRunner` 对每个 attempt 写入 `call_permit_requested`、`call_permit_granted`/`call_permit_denied`、`llm_call_attempted`、`llm_call`，每次 harness retry 都重新申请 permit；OpenAI-compatible SDK retry 已关闭。run 结束时 `classify_infrastructure_validity()` 按本 ADR 的单次恢复/两次失败规则分类。

当前 `BlockRunner` 只冻结合同，不执行或中止一整块运行；上述“block invalid 后停止并整体重跑”仍是正式 block executor 必须实施的运行规则，不能由现有单 run runner 自动满足。
