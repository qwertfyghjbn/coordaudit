# Flowise repository-v1 S1 live smoke（2048 output ceiling，2026-09-18）

## 结论

`flowise_3_1_3_repository_v1` 在新的 2048-token output ceiling 下完成一次真实 provider S1 smoke。provider、fail-closed OS sandbox、预算账本、模型可见 transcript、reconciliation 与 hidden evaluator 均闭环通过。本次运行仍是 smoke，不属于正式 matched block，也不产生协调效果结论。

## 配置

- run_id：`single_n1_20260918T141114.622570+0000_5b4db6fa`
- case / 条件：`flowise_3_1_3_repository_v1`、`single`、1 agent
- provider / requested model：`openai_compatible` / `deepseek-flash`
- resolved model：`deepseek-flash`
- thinking：`disabled`；temperature：`0`
- 单次 output ceiling：`2048`
- smoke budget：8 permits、0 retries、120 秒 wall-clock、无 token stop threshold
- sandbox：bwrap 0.6.1；live run fail-closed self-check 通过

## 证据登记

| 检查项 | 结果 |
| --- | --- |
| run validity | `valid`；provider failure attempts = 0 |
| reconciliation | `valid`；66 events / 31 transcript entries / 26 artifacts / 8 permits |
| budget ledger | 8/8 permits `succeeded`；无 retry |
| observed usage | input 75,242（cached 60,160）；output 1,053；reasoning 0 |
| model metadata | resolved model、system fingerprint、finish reason 均记录 |
| hidden evaluator | positive recall 0/20；unmatched 0；near-miss FP 0；invalid submissions 0 |

## 判读

- 0 findings / 0 TP 不影响 smoke 通过；8-permit smoke 在提交 finding 前耗尽预算，终态为 `model_format_failure`，不属于 infrastructure failure。
- 实际 output 1,053，低于 2048 ceiling；本次未观察到 output ceiling 截断。
- 本记录替代不了 1024 ceiling 的历史 smoke，也不能与 1024 smoke 混入同一 matched block。

## 后续

下一步是提交合同层改动、冻结 `n4_flowise_v1` 的 2048 block，并按同一合同执行 S1/P4/B4/T4。原始 run 产物留在 `experiments/emergent_coordination/runs/`，不提交。
