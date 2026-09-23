# T4 task lifecycle closure gate v1：trace diagnosis and matched diagnostic（2026-09-21）

## 1. Trace-level root cause

本诊断读取了 immutable 的 `t4-sequenced-bootstrap-v1-corrected-3seed-192p` 三条 trace，并将 seed-01/02 的未完成 owner 与 seed-03 的正常 owner 做了事件和 transcript 对照。

| run / owner | create | claim | finalization signal | `complete_task` attempt | submit | task state |
|---|---:|---:|---:|---:|---:|---|
| seed-01 / agent_001 | seq 38 | seq 46 | step 50 / call 161 / rem 32 | 0 | step 50→52 | claimed |
| seed-02 / agent_003 | seq 168 | seq 190 | step 41 / call 161 / rem 32 | 0 | step 41→43 | claimed |
| seed-03 / agent_001 | seq 38 | seq 46 | step 46 / call 161 / rem 32 | seq 1102→1103 | step 46 | completed |

seed-01/02 的 finalization transcript 都包含明确的 `complete_task` 工具和 reminder；`complete_task` 没有被 prohibited-tool gate 拒绝，也没有 schema/evidence rejection。模型在 finalization 后直接构造并重试 `submit_findings`，而没有调用 `complete_task`。seed-03 的最小行为差异是先完成 task，再在后续 model call 提交。

因此原因分类为：

- **E：ordering conflict**：模型把 submit 放在 task close 之前；
- **F：runtime lifecycle invariant 缺失**：旧 runtime 允许 `claimed task + successful submit + agent terminal`，而 `TeamCompletionBarrier` 只检查 stop reason 是否全为 `submitted`，不检查 task-board ownership。

不是 B/C/D（授权、schema 或 evidence 失败），也不是 G（finalization 未触发或 reserve 不足）。现有 prompt 本身已经写明“complete_task 后再 submit”（`harness/prompts.py:111-119`），但 seed01/02 仍失败，说明 prompt-only 不能提供稳定 invariant。

## 2. 当前 contract 缺口

旧路径在 `AgentRunner._dispatch` 中直接执行 `submit_findings`；`TaskBoard.complete_task` 只做 owner 检查，team barrier 只按 terminal reasons 分类。故以下状态在旧语义下合法：

```text
claimed task → submit accepted → agent_finished(submitted) → clean_complete
```

## 3. 最小修正

新增明确 versioned policy：`task_closure_policy=task_closure_gate_v1`。

- `AgentRunner` 在 `submit_findings` dispatch 和 text-content submission 两条路径检查当前 agent 的 claimed tasks。
- 若仍有 claimed task，runtime 返回 deterministic `task_closure_required`，记录 `task_closure_gate_rejected`，不接受 submission、不自动生成 result、不增加 permit。
- `complete_task` 仍是正常 model-visible tool；完成后原 submit path 恢复。
- `TaskBoard.complete_task` 增加 exactly-once 状态转换、result 类型和 `evidence_refs` 列表边界检查；失败不会伪造 completed artifact。
- 未启用该 policy 的旧 runs、S/P/B/M 语义不变；sequencing lease、decomposition prompt、tools、scheduler、budget、reserve 均未改变。

相关实现：

- [agent_loop.py](/home/lqs/coordaudit/experiments/emergent_coordination/harness/agent_loop.py:482)
- [task_board.py](/home/lqs/coordaudit/experiments/emergent_coordination/harness/task_board.py:231)
- [runner.py](/home/lqs/coordaudit/experiments/emergent_coordination/harness/runner.py:31)
- [contract.py](/home/lqs/coordaudit/experiments/emergent_coordination/harness/contract.py:184)

## 4. Test evidence

新增 [test_task_closure_gate.py](/home/lqs/coordaudit/experiments/emergent_coordination/tests/test_task_closure_gate.py)，覆盖 claimed/direct submit、complete-before-submit、completed/no-task compatibility、invalid owner/schema/evidence、exactly-once、no permit、no auto-completion、deterministic event、finalization tool surface、legacy policy 和 sequencing compatibility，共 13 tests。

结果：

- task-closure gate + hard finalization regression：`25 passed`；
- closure + harness + block contract：`62 passed`；
- preflight（S1/P4/B4/T4/M4）中已有的 5 个 mock cases：`5 passed`；另一个已有 `n4_hard_gate` preflight 在当前工作树中长时间不返回，未将其作为 closure 结果；
- 全部上述验证均 provider calls=0、network=0；live 前未用测试替代 provider 验证。

## 5. Frozen identity

- block：`t4-sequenced-bootstrap-task-closure-v1-192p`
- contract：`t4_flowise_sequenced_bootstrap_task_closure_v1`
- manifest hash：`8c7d412bb059402641d4e8e32a419ebb2d67804008693202e5e34cfe31827e5e`
- condition：T4 / `structured_team` / 4 agents；M4 排除
- model：`deepseek-flash`，thinking disabled，temperature 0，output ceiling 4096
- seed identity：`matched-seed-01-from-t4-sequenced-bootstrap-v1-corrected-3seed-192p`
- permits：192；max_steps=96；reserve=32
- completion：`convergent_v2` / `all_agents_terminal_v1` / `team_remaining_permits_v1`
- sequencing：`initialization_lease_v1`
- task closure：`task_closure_gate_v1`
- retry=1；wall-clock=1200s；prompt profile=`repository_v1_t4_sequenced_bootstrap_v1`
- target digest：`c612819a833fc8ab3c58fe5085fb80fc0a6c4cb1d86cbb8ed41b0b431e4a1638`
- evaluator digest：`76aaef174369769e70b8ef61cda454d96a503fc033e1437a6b6efba934915e12`
- runtime digest at freeze：`21bf06336bf9fcc43a828b80b3759e5d8622558667bf3ec81494716917c8ebf2`
- git HEAD recorded：`49725612fff8539b681e8084f29ecb4de5ca8d5f`

## 6. Live diagnostic

第一次 live 外层工具会话在 4 个 provider call 仍 in-flight 时中断，只有 `events.jsonl/run_manifest.json`，没有 summary/reconciliation；按 infrastructure-invalid replacement 处理，保留原始 artifact，不进入比较。

有效 replacement：`formal_seed-01-replacement-01`。原始结果见 [summary.json](../../experiments/emergent_coordination/runs/t4-sequenced-bootstrap-task-closure-v1-192p/formal_seed-01-replacement-01/summary.json) 和 [metrics.json](../../experiments/emergent_coordination/runs/t4-sequenced-bootstrap-task-closure-v1-192p/formal_seed-01-replacement-01/metrics.json)。

| 指标 | replacement result |
|---|---:|
| attempted model calls / permits used | 165 |
| permits remaining | 27 |
| provider failures / reconciliation | 0 / valid |
| finalization | call 161, remaining 32, exactly once |
| create / claim / complete | 4 / 4 / 4 |
| claimed_without_completion | 0 |
| complete-before-submit | 4 / 4 |
| completed artifacts with evidence_refs | 4 / 4 |
| submit / team completion | 4 / 4, `clean_complete` |
| task-result evidence adoption | 0 |
| file / aggregate duplicate ratio | 0.1618 / 0.1401 |
| TP / unmatched | 0 / 11（secondary） |

四个 task 的 completion event 均先于同一 agent 的 `finding_submitted` event；没有 `task_closure_gate_rejected`，因为本次模型都在 gate 需要阻断前主动完成了 task。unit tests 证明若模型再次复现 seed01/02 的 direct-submit 行为，runtime 会拒绝而不伪完成。

## 7. Matched interpretation

相对 seed-01 corrected（旧 policy）：`create/claim/complete=4/4/3`、`claimed_without_completion=agent_001`、174 calls、18 permits remaining；本 replacement 为 `4/4/4`、0、165 calls、27 remaining。两者 finalization 都是 call 161 / remaining 32 / exactly once，说明 intervention 没有改变 team finalization trigger。

这支持的结论仅是：在已解决 sequencing race、prompt 已包含 lifecycle ordering 的条件下，runtime gate + exactly-once board transition 能把旧的“提交成功但 task 仍 claimed”状态从可接受路径中移除，并在一次 matched diagnostic 中建立稳定的 `claim → complete → submit` trace。finding/TP 不用于架构或审计能力排名。

## 8. Remaining confounds and recommendation

- replacement 只有一个有效 live seed；不能据此声称跨 seed 稳定性或最优性。
- 本次没有实际触发 gate rejection，故“阻断 direct submit”的 live 证据来自 mock/unit，而非本条模型轨迹。
- evidence adoption 仍为 0；这是后续 adoption diagnostic，不是 closure gate 的失败。
- TeamCompletionBarrier 仍不独立检查 budget-exhausted agent 的 claimed task；gate 只约束 successful submission ordering，未引入自动清理。

建议：将本次 closure gate 诊断标记为 valid、保留旧三 seed 不变，并在需要更强稳定性时用同一冻结 policy 补 matched seed，而不要改 sequencing/decomposition 或把 finding/TP 重新解释为生命周期结论。
