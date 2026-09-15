# CoordAudit v0 正式冻结记录

状态：`frozen`。本记录冻结的是 `repository_pilot_v0`、N=4 的 S1/P4/B4/T4 合同和实现它们的 runtime/evaluator；它不是完成的 matched block，也不报告 coordination 效果。

## 冻结身份

| 项目 | 值 |
| --- | --- |
| Runtime source commit | `08298fc984a7d3ea7c511e40c1d62eabdc4e2600` |
| 工作树状态 | clean；`git_status` SHA-256 为 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| Block artifact | `experiments/emergent_coordination/runs/n4-pilot-v0-freeze-20260915/block_manifest.json` |
| Block manifest SHA-256 | `3deed67a6667c9813fa1593fb058c77c1bbfd42f650f8a8f97a3208815f239fd` |
| Target tree SHA-256 | `50c304715ea9cc4a157b516f1beb281843b54201a5f7caf2addcef494761b09d` |
| Runtime tree SHA-256 | `41a9f20472e4a50be29b0cc318949e6df6c59a8533827eb4bc5aa186e010d5a3` |
| Private evaluator tree SHA-256 | `493648e159d8cd584e90d9e4eaed9d2d9d24d53dd45d1f7547b8da85153251ea` |
| N=4 config SHA-256 | `b6c5efe44dda548a293cdf3960797349713e9f6f4b2ed67bba6f5dc0d13293ba` |

## 冻结模型与预算合同

| 字段 | 值 |
| --- | --- |
| Provider / requested model | `openai_compatible` / `deepseek-flash` |
| Thinking / temperature / output ceiling | `disabled` / `0` / `1024` |
| 条件 | S1、P4、B4、T4 |
| 团队硬调用预算 | 每个 condition 32 permits；无 per-agent token cap |
| Runtime safety ceiling | 32 steps；600 秒 wall clock；最多 1 次 harness-controlled provider retry |

DeepSeek compatibility probe 已验证 provider 将请求解析为 `deepseek-flash`，且 function call 与 tool-result continuation 可用；详见 [v0 候选记录](v0-candidate-freeze.md)。provider alias 的将来行为不由本地 tag 保证，因此每个后续 block 必须继续记录 resolved model 与 system fingerprint。

## 审阅与验证证据

- Harness：58 tests 通过。
- Agent-visible target smoke：6 tests 通过。
- S1/P4/B4/T4 mock smoke 均通过。
- S1 live harness smoke：`single_n1_20260915T080646.642486+0000_ce952b81`，4/4 provider attempts 成功，`run_validity=valid`、`reconciliation=valid`，并实际调用 bwrap 隔离的 `run_shell`。详情见 [v0 候选记录](v0-candidate-freeze.md)。
- 该 S1 smoke 最终为 `model_format_failure`、0 findings；按 ADR 0005 它不是 infrastructure failure，不构成安全能力或 coordination 效果结论。

## 冻结边界与后续规则

`block_manifest.json` 的 `live_gate.status` 固定为 `blocked`。这是正确且刻意的：现有 `freeze_block.py` 只能产生不可覆盖的合同与 digest，不能调度、停止或整体重跑 S1/P4/B4/T4。

后续正式 matched block 必须由独立 executor 将四个 condition 绑定到本合同；任一 infrastructure-invalid run 必须使整个 block 停止并整体重跑。不得将本记录中的 S1 smoke 或 block manifest 作为 matched-block 完成或 architecture-effect 证据。
