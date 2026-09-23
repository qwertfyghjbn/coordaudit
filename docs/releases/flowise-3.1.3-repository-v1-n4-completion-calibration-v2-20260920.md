# Flowise repository-v1 N=4 completion calibration v2（96 permits）

## 结论

本轮只校准 completion lifecycle，不比较 S/P/B/T 的架构效果。新 contract `n4_flowise_completion_calibration_v2` 固定 `S1/P4/B4/T4`，排除 M4。四条 live run 均 `run_validity=valid`、reconciliation=valid、provider failure=0；P4/B4/T4 都在 shared ledger 剩余 32 permits 时 exactly-once 进入 `team_remaining_permits_v1` finalization，并在 96-call hard budget 内成功提交。上一轮的 `finalization_start=null + 96 calls + zero submissions` pathology 消失。

## Pre-run audit 与最小修正

旧实现位于 `harness/agent_loop.py::_tools_for_step()`，按 `agent_step >= max_steps - 8` 切换；N=4 共享 96 permits 时单 agent 通常只能获得约 22–26 steps，因此 gate 不可达。`TeamCompletionBarrier` 只在所有 Agent 已结束后判定 team completion，不负责触发 finalization。

本轮在 `harness/budget.py` 增加了原子、exactly-once 的 team permit trigger；`AgentRunner` 在 trigger 后对所有 active agents 注入相同 epoch。finalization 仍共用原 permit ledger，不重置或增加预算；只额外保留 `read_file` 作为必要 evidence binding，shell 与 coordination tools 仍被 hard gate 拒绝。`TeamCompletionBarrier` 继续负责 admission-close 后 drain 与 all-agents-terminal 判定。旧 completion generation/manifest 未修改。

## Frozen contract

- block：`n4-flowise-completion-calibration-v2-96p`
- manifest hash：`238ee898f90af7010b8e9073a5e0fbe7f16ee3edfea8eb80e31c3368ac061a31`
- git commit：`49725612fff8539b681e8084f29ecb4de5ca8d5f`
- conditions：`S1, P4, B4, T4`；M4 excluded
- model：`openai_compatible / deepseek-flash / thinking disabled / temperature 0 / max_output_tokens 4096`
- seed：`n4-flowise-completion-calibration-v2-96p`（四条件 matched）
- budget：`hard_team_call_permits=96`，`max_steps=96`，wall-clock `1200s`，普通 retry `1`
- completion：`completion_policy=convergent_v2`；`team_completion_policy=all_agents_terminal_v1`
- finalization：`completion_generation=completion_v2_team`；`team_finalization_policy=team_remaining_permits_v1`；reserve `32`
- target/evaluator/runtime digests：block manifest 中的 `target_tree`、`evaluator_private_tree`、`runtime_tree`、prompt/tool condition hashes

## Tests and gate evidence

- team boundary/uneven/early-terminal/mock production preflight：`test_team_finalization_calibration.py`（3 passed）
- harness + repository-v1 targeted suite：236 passed；completion/hard-gate/preflight regression 20 passed（4 subtests）
- compatibility probe：DeepSeek forced tool-call + continuation passed，same profile
- bubblewrap self-check：passed in escalated execution environment；正式 run `require_os_sandbox=true`
- zero-network mock validation：passed；正式 Agent shell namespace remained network-isolated
- unrestricted `pytest -q` 的 collection failure 来自历史 run workspace 重复 `tests/test_app_smoke.py` 的 import mismatch，不是 runtime test failure；历史 artifacts 未删除

## Four-run lifecycle results

| condition | attempted calls | trigger | trigger remaining | finalization starts（agent steps） | submitted agents | team result | findings | TP |
|---|---:|---|---:|---|---:|---|---:|---:|
| S1 | 66 | yes, once | 32 | 65 | 1/1 | clean_complete | 2 | 0 |
| P4 | 79 | yes, once | 32 | 16–18 | 4/4 | clean_complete | 5 | 0 |
| B4 | 81 | yes, once | 32 | 16–18 | 4/4 | clean_complete | 2 | 0 |
| T4 | 75 | yes, once | 32 | 16–17 | 4/4 | clean_complete | 4 | 0 |

All four ended with `in_flight=0`; no run exhausted the hard 96 permits. P4 had two invalid submission attempts and B4 one, but each subsequently submitted valid payloads. These are secondary observations, not architecture rankings.

## Paired diagnostic comparison with v1

| metric | S1 old → new | P4 old → new | B4 old → new | T4 old → new |
|---|---|---|---|---|
| calls | 42 → 66 | 96 → 79 | 96 → 81 | 96 → 75 |
| finalization | null → trigger@32 | null → trigger@32 | null → trigger@32 | null → trigger@32 |
| submitted agents | 1 → 1 | 0 → 4 | 0 → 4 | 0 → 4 |
| team terminal | clean → clean | forced → clean | forced → clean | forced → clean |
| findings | 2 → 2 | 0 → 5 | 0 → 2 | 0 → 4 |
| TP | 1 → 0 | 0 → 0 | 0 → 0 | 0 → 0 |
| coordination actions | none → none | none → none | 0 → 0 shared-store | 4 empty list_tasks → 4 empty list_tasks |
| duplicate ratio | n/a → n/a | 31.5% → 22.0% | 20.8% → 36.0% | 42.1% → 42.4% |

这张表只说明 lifecycle intervention 改变了收尾机会与 terminal path；不能解释为任一 topology 更有效。B4 没有 shared-store adoption，T4 没有 create/claim/complete/adoption，均应保留为后续 adoption experiment 的描述性结果。

## Recommendation and remaining confounds

就 completion lifecycle 而言，96 permits 已足以给 N=4 提供可解释的 team finalization/submission opportunity：P4/B4/T4 都不再卡在 per-agent step-89 gate。Finding/TP 仍受单次 seed、模型探索和 evidence quality 影响，不能据此做 coordination effectiveness 结论。下一步若需要诊断 forced completion，应另行 preregister（例如 T4@192）；本会话不扩展该实验，也不运行 M4。
