# T4 task-lifecycle-v2 diagnostic（192 permits）

## 研究问题

本 block 回答：**模型已经采用 task board 后，明确的 lifecycle instruction 是否足以让 claimed task 转化为 completed artifact？**

相对 `T4-board-bootstrap@192`，保留 192 permits、reserve=32、model、seed、tools、scheduler 和 decomposition/bootstrap prompt；只增加 claimed-task completion-before-submission instruction，并在 team finalization prompt 中加入：

> If you still own a claimed task, close it with complete_task before finishing the run.

为使该提醒可执行，variant 在 finalization 阶段授权了已有的 `complete_task` 工具；没有新增工具，baseline T4 的 finalization authorization 不变。

## Frozen identity

- block：`t4-task-lifecycle-v2-192p`
- contract：`t4_flowise_task_lifecycle_v2`
- manifest hash：`47046f3b611cce36ca8bb75a7c4c55d417779b5cef9ca16b1c82e881e8cd6ebe`
- prompt profile：`repository_v1_t4_task_lifecycle_v2`
- condition：T4，4 agents
- shared permits：192；finalization reserve=32
- model/seed/target/evaluator/tool schema：与 T4-board-bootstrap@192 匹配
- completion：`convergent_v2` + `all_agents_terminal_v1`

Prompt hash 检查：user prompt 与 bootstrap variant 相同；tool schema 相同；system prompt 仅增加 lifecycle instruction。

## Lifecycle validity

Run `formal_t4-task-lifecycle-v2`：

- `run_validity=valid`
- `reconciliation=valid`
- provider failures=0
- attempted calls=170，remaining permits=22
- finalization 在 call index 161、remaining=32 时触发一次
- 4/4 agents submitted，team `clean_complete`

## Matched lifecycle comparison

| 指标 | T4-board-bootstrap@192 | T4-task-lifecycle-v2@192 |
|---|---:|---:|
| `create_task` | 4 | 4 |
| `claim_task` | 4 | 4 |
| `complete_task` | 0 | 4 |
| completed artifacts | 0 | 4 |
| tasks with evidence refs | 0 | 4 |
| claimed task left open | 4 | 0 |
| task completion before finding submission | 不适用 | 4/4 |
| attempted calls | 168 | 170 |
| finalization | call 161 / remaining 32 | call 161 / remaining 32 |
| submitted agents | 4/4 | 4/4 |
| team completion | clean | clean |

四个 agent 的 `task_completed` 事件均先于其 `finding_submitted` 事件。四个最终 task artifact 都是 `completed`，并带有有效 evidence refs（分别为 3、7、8、4 条）。

## 三层结果

### Adoption

bootstrap prompt 已经使四个 agent create/claim task；lifecycle-v2 没有改变这一层，但把 complete rate 从 `0/4` 提高到 `4/4`。

### Coordination quality

任务仍主要集中在 `packages/server/src/routes` 和 controllers，分工互补性没有根本改变。不过相对 bootstrap variant，文件 duplicate ratio 从 0.542 降到 0.483；这只能作为描述性改善，不能单独归因于 lifecycle completion instruction。

### Task effectiveness

这是本轮最明确的变化：claimed task 不再停留在 open/claimed 状态；每个任务都有 concise result 和 evidence refs，并且在 final finding submission 前完成。由 task board 产生了可审计的 completed artifacts。

Finding/TP 仍是 secondary：本轮 7 findings、1 TP；bootstrap variant 为 7 findings、1 TP。不能据此声称审计能力提升。

## 结论

在已经采用 task board 的前提下，明确的 lifecycle contract 足以把“create/claim adoption”转化为“complete artifact”：本轮 4/4 任务完成、4/4 具备 evidence refs、4/4 在提交前关闭任务。

这解决的是 task lifecycle compliance，不等同于已经解决任务互补性、ownership 分工或审计收益问题。后续若继续研究，应针对 task complementarity/ownership，而不是再次调整 completion reserve。
