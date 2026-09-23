# T4 sequenced-bootstrap v1（192 permits）

## 研究问题

在保持 T4 task-board bootstrap、prompt、工具、模型、seed、预算和 completion semantics 不变的前提下，增加 runtime-only 的 deterministic initialization lease，消除 `list_tasks → create_task` 的并发可见性 race 后，agent 是否形成更互补的 task decomposition？本轮不人工指定 auth/SSRF/file/OAuth scope，也不加入自动分工或 runtime 去重。

## 实现

新增 versioned policy：`task_board_sequencing_policy=initialization_lease_v1`。

- `harness/task_board.py`：按 canonical `agent_001..agent_N` 顺序授予首次 board 初始化 lease。当前 agent 的首次 `list_tasks`、`create_task`、`claim_task` 处于同一 initialization turn；成功 claim 或 agent terminal 时释放 lease。lease 不创建任务、不选择 scope、不改变 claim 的原子性。
- `harness/runner.py`：将 policy 和 canonical agent IDs 传入 board，并在 agent terminal path 释放未完成 lease。
- `harness/events.py` / `analysis/analyze_run.py`：记录并汇总 lease wait/acquire/release、hand-off 顺序和首批 board visibility。
- contract/profile：新增 `t4_flowise_sequenced_bootstrap_v1` / `repository_v1_t4_sequenced_bootstrap_v1`。新 profile 的 system/user prompt hash 与 `T4-task-lifecycle-v2@192` 完全一致；仅 runtime sequencing policy 改变。

## 首次 block 的语义回归与排除

第一次冻结的 `t4-sequenced-bootstrap-v1-192p` 在 live 后发现新 profile 没有接入既有 finalization `complete_task` authorization 集合，导致四个 claimed task 均未完成。该 block 的 infrastructure validity 虽为 `valid`，但不满足 preregistered lifecycle identity，因此不进入科学比较。修复后以新 identity `t4-sequenced-bootstrap-v1-corrected-192p` 重新冻结和运行，没有复用污染 identity。

## Corrected frozen identity

- block：`t4-sequenced-bootstrap-v1-corrected-192p`
- contract：`t4_flowise_sequenced_bootstrap_v1`
- manifest hash：`1f1780996da420d5504efd3ed98fd97536f73abbe8f4da7d68df879a7e431fb5`
- condition：T4 / `structured_team` / 4 agents
- model：`deepseek-flash`，thinking disabled，temperature `0.0`，output ceiling `4096`
- seed：`n4-flowise-completion-calibration-v2-96p`
- permits：`192`
- max steps：`96`
- retry：`1` normal provider retry，final synthesis retry `0`
- wall clock：`1200s`
- completion：`completion_v2_team` / `convergent_v2`
- team completion：`all_agents_terminal_v1`
- finalization：`team_remaining_permits_v1`，reserve `32`
- sequencing：`initialization_lease_v1`
- git commit：`49725612fff8539b681e8084f29ecb4de5ca8d5f`
- target digest：`c612819a833fc8ab3c58fe5085fb80fc0a6c4cb1d86cbb8ed41b0b431e4a1638`
- evaluator digest：`76aaef174369769e70b8ef61cda454d96a503fc033e1437a6b6efba934915e12`
- runtime digest：`dda3e156ae6ff4722f3c9e39f43c1be7b2a855489e09dd3d2c38db78ee5e4a3d`
- system prompt hash：`25d192a845e62aa885fceb74ea60cf8d7fc61e35cc5fefe6f2619f76915ef0bc`
- user prompt hash：`fb9fa97c0ca2774142479f9c37bf7ebc339e32447dad3bf033ce1f6b2e58f636`
- tool schema hash：`81707c840e64c97540da11f856ff1b7ca56b2c0b0d5ab073a44f0c4c52ac29d9`

## Test / live gate

- targeted lease/contract/prompt/analyzer tests：`61 passed`
- 全部 emergent coordination tests：`238 passed, 1 warning, 4 subtests passed`
- `git diff --check`：通过
- corrected live run：通过 fail-closed sandbox gate；provider failures `0`
- run validity：`valid`
- reconciliation：`valid`

## Corrected live 结果

Run：`formal_t4-sequenced-bootstrap-v1-corrected`

- attempted calls：`174`
- permits remaining：`18`
- finalization：call `161` / remaining `32` / exactly once
- submissions：`4/4`
- team completion：`clean_complete`
- in-flight calls：`0`
- findings：`4`；TP=`0`（secondary）
- evaluator 记为 invalid submissions：`2`；trace 中实际有 `3` 次失败的 submit tool call（2 次 schema rejection，1 次 invalid-JSON），随后均完成合法重试，未导致 infrastructure invalid

### Visibility / sequencing

lease 事件显示：

```text
acquire: agent_001 → agent_002 → agent_003 → agent_004
release: agent_001 → agent_002 → agent_003 → agent_004
```

三名后继 agent 在等待 lease；`list_tasks` 返回计数严格为：

```text
agent_001: 0
agent_002: 1
agent_003: 2
agent_004: 3
```

因此首个 create 前只有 agent_001 观察到空 board；上一轮 non-overlap run 的四个 agent 全部观察到空 board 的 race 已消失。

### Decomposition quality

四个 task 自发形成了明显的 subsystem/layer 分层：

| owner | task scope |
|---|---|
| agent_001 | server-side HTTP/API routes，authz/SSRF/path/injection |
| agent_002 | server security-primitive utilities 与 guard call sites |
| agent_003 | server services layer，webhook/MCP/SSRF/export-import 等 |
| agent_004 | enterprise SSO/auth/RBAC paths |

相对 `T4-task-lifecycle-v2@192`，文件 cross-agent duplicate ratio 从 `0.4833` 降到 `0.1912`；aggregate duplicate ratio 从 `0.4531` 降到 `0.1699`。这与 lease 让后继 agent 看到已有 claimed scope 的机制一致，是本轮 decomposition diagnostic 的主要正向证据，但不是 architecture effectiveness 结论。

相对上一轮 `T4-nonoverlap-v1@192`，差异更直接：上一轮四个 `list_tasks` 都是空、task scope 集中在相互覆盖的 server routes/controllers，文件 duplicate ratio 为 `0.4531`；本轮变为 `0,1,2,3` 的可见性阶梯，scope 分散到 routes、security utilities、services、enterprise SSO/RBAC，文件 duplicate ratio 降至 `0.1912`。

### Task effectiveness / lifecycle

- `create_task=4`、`claim_task=4`
- `complete_task=3`
- `release_task=0`
- 3 个 completed artifacts 带有 evidence refs，并在各自 finding submission 前完成
- agent_001 保留一个 claimed task 到提交，说明 lifecycle instruction 仍可能被模型忽略；这不是 lease visibility failure
- `task_result_evidence_adoption=0`：没有观察到后续 agent 复用 completed task evidence

## Matched diagnostic

| metric | T4-task-lifecycle-v2@192 | T4-sequenced-bootstrap-v1 corrected@192 |
|---|---:|---:|
| attempted calls | 170 | 174 |
| permits remaining | 22 | 18 |
| finalization | call 161 / rem 32 / once | call 161 / rem 32 / once |
| submitted agents | 4/4 | 4/4 |
| clean complete | yes | yes |
| `list_tasks` result counts | 0,0,0,0 | 0,1,2,3 |
| initialization lease hand-off | none | 001→002→003→004 |
| tasks completed | 4/4 | 3/4 |
| task-result evidence adoption | 0 | 0 |
| file duplicate ratio | 0.4833 | 0.1912 |
| findings / TP | 7 / 1 | 4 / 0 |

作为 race 对照，`T4-nonoverlap-v1@192` 的 file duplicate ratio 为 `0.4531`，且四个首批 board 结果均为 `0`；它不是本次 corrected run 的 comparison denominator，只用于解释 sequencing intervention 的可见性变化。

Finding/TP 只作 secondary 记录，不能从单次 calibration 推断审计能力或架构优劣。

## 结论

1. 初始化 lease 成功消除了首次 `list_tasks → create_task` race，并提供了可验证的 deterministic visibility/sequencing：后继 agent 依次看到前序 claimed tasks。
2. 在不人工规定 scope 的情况下，四个 agent 形成了比 baseline 更互补的 subsystem/layer decomposition，重复工作显著下降。
3. 这不是完整的 task lifecycle success：只有 3/4 task 在提交前完成，agent_001 的 claimed task 留存是模型遵循问题，而不是 board visibility 问题。
4. completion lifecycle 没有回归；192 permits 下仍正常 finalization、submission 和 team completion。

下一步若继续，应单独研究 task lifecycle compliance（例如为何 agent_001 在已有 finalization reminder 下仍未 `complete_task`），不要把该问题与 decomposition sequencing 混为一谈。
