# 运行级 live gate 开启记录（2026-09-18）

## 结论

`block_runner` 冻结 manifest 中的运行级 `live_gate` 由 `blocked` 翻转为 `open`（用户批准）。四个预注册前置逐项登记实现锚点与实证证据；此前仅有的两层缺口（case 级 gate、B 类 validator）已分别于今日闭合。本记录只声明 **harness 具备生成可解释 live matched block 的条件**，不等于任何 live matched block 已经运行。

## 四个前置的证据登记

| 前置 | 实现锚点 | 实证 |
| --- | --- | --- |
| `pre_call_permit_ledger` | `harness/budget.py` `acquire_call_permit`：请求到达 provider 前预扣 team permit；retry 恒为新 permit | harness 单测覆盖；2026-09-15 S1 live smoke 实跑 |
| `fail_closed_os_sandbox` | `harness/tools/sandbox.py` `assert_os_sandbox_ready`：bwrap 缺失即 fail-closed（本机 bwrap 0.6.1） | S1 live smoke 通过 bwrap self-check 并真实调用工具 |
| `model_visible_transcript_and_reconciliation` | `harness/events.py` `TranscriptLog` + `reconcile_run`（每个 condition 后运行） | S1 live smoke 记录 `run_validity=valid`、`reconciliation=valid` |
| `strict_finding_schema_dedup_and_private_verification` | `harness/findings.py` / `repository_v1_findings.py` 拒绝重复 evidence refs 与 anchor 复用；`evaluator/repository_v1_score.py` 将 evaluator verification 与 Agent 自报分离记录 | schema 契约测试与 evaluator 测试覆盖；flowise verifier 全链通过 |

S1 live smoke 出处：`docs/releases/v0-candidate-freeze.md`（2026-09-15，pilot v0 case，真实 provider、完整 loop）。

## 变更与验证

- `harness/block_runner.py`：`live_gate` 块改为 `status: open` + `satisfied_before_execution`（每项含 `requirement` 与 `evidence` 字段）。
- `tests/test_block_contract.py`：断言 `status == "open"`、四项 requirement 齐备、每项 evidence 非空。
- 回归：unittest 95 passed；flowise S/P/B/T mock smoke 4/4 通过；试冻结 `gate-open-check` 确认 block manifest 携带 `live_gate: open`（opened_on 2026-09-18、4 项证据）；`git diff --check` 通过。
- 试冻结使用的是 `n4_pilot_v0` 合同（S1/P4/B4/T4、32 permits），仅作 manifest 结构验证，运行产物已删除。

## 与正式实验之间剩余的步骤

1. flowise case 的单条件 S1 live smoke（repository-v1 任务真实模型闭环验证；花真实调用费，待用户确认后执行）。
2. 新建 flowise matched block 合同 JSON（S1/P4/B4/T4、64 permits、引用冻结 case digest）并冻结。
3. 逐条件执行 live matched block；任一 infrastructure-invalid condition 触发整块重跑（预注册规则）。
4. hidden evaluator 评分与 versioned release record。

运行级 gate 的开启不改变 `required_for_tp` 语义，也不构成任何协调效果结论。
