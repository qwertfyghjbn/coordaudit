# CoordAudit v0 候选冻结记录

状态：`candidate`。模型 compatibility 已验证；单条件 live harness smoke 仍是正式冻结前的剩余 gate。

## 候选范围

- Agent-visible target：`repository_pilot_v0`。
- Hidden evaluator、runtime、prompt、tool schema、N=4 合同与 ADR 0002–0005 的实现均由同一 Git commit 和冻结 digest 共同定位。
- 模型请求别名：`deepseek-flash`；thinking mode：`disabled`；temperature：`0`；每调用 output ceiling：`1024`。

禁用 thinking 是 v0 模型合同的一部分。DeepSeek 在 thinking mode 下不会实际应用 `temperature`，而 N=4 合同把 `temperature=0` 作为可比配置。因此候选配置显式使用 non-thinking mode。

## Provider compatibility 记录

执行日期：2026-09-15。通过 `compatibility_smoke.py --model deepseek-flash` 完成一个不挂载 target、不运行 Agent 的两请求 probe。

| 字段 | 观测值 |
| --- | --- |
| 请求模型 | `deepseek-flash` |
| Provider resolved model | `deepseek-flash` |
| thinking mode | `disabled` |
| system fingerprint | `aeb56401ca74e127821c4f9126dcb669`（两次响应一致） |
| 调用一 | 294 input、0 cached input、37 output tokens；强制 `compatibility_echo` tool call 成功 |
| 调用二 | 347 input、128 cached input、15 output tokens；tool-result continuation 成功 |

该记录证明当前 provider alias、OpenAI-compatible function schema 与多轮 tool protocol 可用；它不测审计能力、不挂载 evaluator，也不是任何 coordination condition。

## 完成条件

1. harness 全量单测、target-visible smoke 与四个 mock mode smoke 通过；
2. 工作树没有未记录的变更，且没有仓库凭证；
3. `compatibility_smoke.py --model deepseek-flash` 成功，记录 provider 的 resolved model 与 system fingerprint（若提供）；**已完成，见上节**；
4. 生成的单条件 live harness smoke 标记 `run_validity=valid` 且 `reconciliation=valid`；
5. 只在上述条件全部满足后，创建不可变 Git tag、block manifest 和正式 release record。

`compatibility_smoke.py` 与单条件 live smoke 都不是 matched block，不产生 S/P/B/T 效果结论。
