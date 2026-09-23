# Flowise repository-v1 T4 result-sync-v1 diagnostic

日期：2026-09-21  
冻结 block：`t4-result-sync-v1-192p`  
block manifest hash：`c250aa059cc171394e0f5ec8a8be04f5dad97e70a46898ba4f31f14c8d7722ef`  
唯一 matched live seed：`matched-seed-01`  
seed：`t4-result-sync-v1-matched-seed-01`

## 结论

本轮的 visibility 目标已达成，但未观察到 result-sync 之后的主动检查：

| outcome | agent 数 |
| --- | ---: |
| R0：foreign artifact 不可见 | 0 |
| R1：可见但未检查 | 4 |
| R2：检查但未采用 | 0 |
| R3：检查并改变后续 search/reasoning | 0 |
| R4：foreign evidence 进入 final artifact | 0 |

因此下一瓶颈定位为 `inspection / model-policy`，不是 runtime visibility。该 run 不支持任何 TP 或 security effectiveness 提升结论。

## 1. Pre-run visibility diagnosis

审计了 [`task_board.py`](../../experiments/emergent_coordination/harness/task_board.py)、[`agent_loop.py`](../../experiments/emergent_coordination/harness/agent_loop.py)、[`runner.py`](../../experiments/emergent_coordination/harness/runner.py)、[`sandbox.py`](../../experiments/emergent_coordination/harness/tools/sandbox.py)、事件/trace analyzer 以及既有 T4 trace：

1. `complete_task` 在返回前把 task 原子替换为 `status=completed`，并写入 `result`、`evidence_refs`、`completed_at`，随后记录 `task_completed`。
2. 原有 `list_tasks` 返回完整 task JSON，所以理论上可见字段已经包括 `id`、`owner`、`description`、`status`、`result`、`evidence_refs`、dependencies 和 lifecycle timestamps。
3. 原 profile 没有独立的只读 task-result API；`list_tasks` 是唯一的 task-board 读取面，且旧路径没有稳定的 post-completion observation opportunity。
4. initialization lease 只解决首次 board/create/claim 的 sequencing；task closure gate 只保证 `claim → complete → submit`。二者都没有保证其他 agent 在 submit 前再次读取 completed artifact。
5. 因此旧路径存在 `A complete → B 直接 submit → B 从未看到 A result` 的 timing race；历史 trace 的 cross-agent completed-task evidence reuse 为 0 与此 diagnosis 一致。

## 2. `result_sync_v1` 语义

保持 192 permits、finalization reserve=32、`initialization_lease_v1`、既有 decomposition/non-overlap prompt、task lifecycle、`task_closure_gate_v1`、模型/seed strategy、scheduler、submission 和 finalization semantics 不变。

新 primitive 的确定性条件是：所有 participating agents 都完成自己的 first claimed task 后，在持有 board lock 的状态下只触发一次 `result_sync_triggered`。触发 payload 绑定 `sync_id`、participating agents、initial claims 和 completed initial task IDs。

每个 agent 在其下一次 model turn 前最多观察一次 raw completed-task snapshot，并产生 `result_sync_observed`。snapshot 原样携带 completed task 的 owner、result、evidence_refs 和 lifecycle 字段；runtime 不做 summary、relevance 判断、routing、merge 或 finding 注入。同步后的 raw snapshot 以 model-visible user context 进入 transcript。

submission gate 仅阻止在同步尚未触发或该 agent 尚未观察同步时提交；它不要求采用 foreign result，也不自动消耗或增加 permit。若 agent 未完成 first claim，barrier 不等待它，因此不会为 result sync 引入新的 deadlock 条件。

## 3. 修改与测试

主要修改：

- [`task_board.py`](../../experiments/emergent_coordination/harness/task_board.py)：versioned barrier、raw snapshot、一次性 trigger/observation、owner/result/evidence provenance。
- [`agent_loop.py`](../../experiments/emergent_coordination/harness/agent_loop.py)：同步消息注入和提交前 observation gate；不修改既有 closure gate。
- [`prompts.py`](../../experiments/emergent_coordination/harness/prompts.py)：最小 result-sync prompt；只说 inspect when relevant、adoption optional。
- [`events.py`](../../experiments/emergent_coordination/harness/events.py) 与 [`analyze_run.py`](../../experiments/emergent_coordination/analysis/analyze_run.py)：记录 trigger、observation、inspection proxy、adoption provenance 和 R0–R4。
- [`runner.py`](../../experiments/emergent_coordination/harness/runner.py)、[`contract.py`](../../experiments/emergent_coordination/harness/contract.py) 和新 manifest：注册 `t4_flowise_result_sync_v1`，保持 T4 192/32 合同。
- [`test_result_sync_v1.py`](../../experiments/emergent_coordination/tests/test_result_sync_v1.py)：包含 zero-network scheduler/transcript/team-completion preflight、可见但不采用、closure/permit gate、provenance、finalization surface 和 exhausted-permit 检查。

测试结果：

- 全套 harness：`260 passed, 4 subtests passed`。
- result-sync 专项：`7 passed`。
- `git diff --check`：通过。
- zero-network mock run：valid、reconciliation valid、trigger exactly once、2/2 observation、2/2 closure、无自动 foreign reuse。
- 覆盖的冻结不变量：sequencing lease 未改；closure gate 仍有效；finalization reserve 仍为 32；sync 不增加 permits；permit exhaustion 下 observation 不等待、不消费 permit；legacy blocks 的回归测试通过。

## 4. Frozen identity 与 live lifecycle

冻结配置为 [`t4_flowise_result_sync_v1.json`](../../experiments/emergent_coordination/manifests/t4_flowise_result_sync_v1.json)，block artifact 为 [`block_manifest.json`](../../experiments/emergent_coordination/runs/t4-result-sync-v1-192p/block_manifest.json)。live run 产物位于 [`matched-seed-01`](../../experiments/emergent_coordination/runs/t4-result-sync-v1-192p/matched-seed-01)。

关键 lifecycle 顺序：

1. 4 个 agent 按既有 initialization lease 完成 create/claim；4 个 initial tasks 均完成，closure valid。
2. team finalization 在 call index 161、remaining permits=32 时 exactly once 触发；之后仍允许完成已 claim task，不因 result sync deadlock。
3. 最后一个 initial task 完成后，`result_sync_triggered` 为 event `evt_00001182`，`sync_id=result_sync_v1_0001`。
4. 4 个 `result_sync_observed` 分别为 `evt_00001183`、`evt_00001194`、`evt_00001202`、`evt_00001220`，每个 agent 恰好一次。
5. 4 个 agent 最终全部 submitted；team completion 为 `clean_complete`，178/192 permits 使用，14 个剩余，无 provider failure、timeout 或 deadlock，reconciliation valid。

## 5. R0–R4 与 provenance

live [`metrics.json`](../../experiments/emergent_coordination/runs/t4-result-sync-v1-192p/matched-seed-01/metrics.json) 的 `result_sync` 为 `triggered=true`、`exactly_once=true`，`outcome_counts={"R1":4}`。

每个 agent 的 observation payload 都包含 4 个 completed task 的 raw records，其中 1 个为 own、3 个为 foreign；foreign record 均带有明确的 `owner`、`result` 和 `evidence_refs`。对应 event 为：

- `agent_001`：`evt_00001220`，foreign tasks `task_1441c909e0`、`task_8663d53788`、`task_a46b057ce4`。
- `agent_002`：`evt_00001194`，foreign tasks `task_1441c909e0`、`task_8663d53788`、`task_ca3959191d`。
- `agent_003`：`evt_00001202`，foreign tasks `task_1441c909e0`、`task_a46b057ce4`、`task_ca3959191d`。
- `agent_004`：`evt_00001183`，foreign tasks `task_8663d53788`、`task_a46b057ce4`、`task_ca3959191d`。

严格的 R1 判定要求同步 observation 之后出现可重放的 foreign artifact inspection。该 run 没有 post-sync `task_result_observed`，也没有 post-sync search/read action；因此不能把 raw context delivery 或先前的 `list_tasks` 当作 R2/R3。4 个最终 finding artifact 的 foreign task evidence refs 均为 0，所以 R4=0。`list_tasks` 本身不计 reuse。

## 6. Secondary outcomes

- task create/claim/complete：4/4/4；unfinished tasks=0。
- initialization lease acquisition/release：4/4，顺序为 agent_001 → agent_002 → agent_003 → agent_004。
- duplicate task description ratio：0.0。
- `result_sync_gate_rejected`：3 次，均为 deterministic pre-observation submission 防护，不是 provider/runtime failure。
- invalid submission attempts：2；4 个 agent 都最终 submitted。
- merged findings：7；evaluator secondary output 的 positive recall 为 0，本轮不解释为 coordination effectiveness。

## 7. 下一瓶颈

本轮已经排除“completed artifact 没有进入其他 agent model-visible context”这一 visibility failure。当前证据支持的下一瓶颈是 inspection/discoverability 与 model policy：artifact 已可见，但在最终提交前没有可重放的同步后检查动作。下一轮若继续，应单独研究如何提高 inspection opportunity 或 model discoverability；不应把本 run 的 R1 结果解释为需要 runtime 自动 reuse，也不应以 TP 变化替代该诊断。
