# T4 non-overlap v1 弱约束诊断（192 permits）

## 研究问题

在 completion 已经确认充足、且模型已经采用 task board 的前提下，弱约束的“创建/认领前检查并避免重叠 scope”指令，是否足以让四个 agent 自发形成互补任务？本轮不是 architecture benchmark，也没有人工指定 auth、SSRF、file、OAuth 四个固定 scope。

## Intervention 与冻结边界

相对 `T4-task-lifecycle-v2@192`，只在既有 T4 bootstrap/decomposition prompt 后追加以下弱约束：创建或认领前调用 `list_tasks`，检查 open/claimed scope；将相同 subsystem、route/controller family 或 security objective 视为 overlap；优先未覆盖区域；创建时声明 scope、objective 和排除的邻近 scope；不重复改写已 claim task；继续沿用 claim → complete（含 evidence_refs）→ submit lifecycle。

没有加入自动去重、scope 分配、leader、消息、强制分工、runtime adoption 或新的工具。`TaskBoard.claim_task` 仍是原子操作，`list_tasks`→`create_task` 仍是两个独立调用；本轮将其并发可见性 race 作为诊断对象。

## Frozen identity

- block：`t4-nonoverlap-v1-192p`
- contract：`t4_flowise_nonoverlap_v1`
- condition：T4 / `structured_team` / 4 agents
- manifest hash：`63892cb5701549af844642feedb3f85d7a0aea7d18c88855f6e13ef627a99ae2`
- prompt profile：`repository_v1_t4_nonoverlap_v1`
- model：`deepseek-flash`，provider `openai_compatible`，temperature `0.0`，thinking disabled，output ceiling `4096`
- matched seed：`n4-flowise-completion-calibration-v2-96p`
- permits：`hard_team_call_permits=192`
- max steps：`96`
- retry：`max_provider_retries=1`，`final_synthesis_retries=0`
- wall clock：`1200s`
- completion：`completion_v2_team` / `convergent_v2`
- team completion：`all_agents_terminal_v1`
- finalization：`team_remaining_permits_v1`，reserve `32`
- git commit：`49725612fff8539b681e8084f29ecb4de5ca8d5f`
- target digest：`c612819a833fc8ab3c58fe5085fb80fc0a6c4cb1d86cbb8ed41b0b431e4a1638`
- evaluator digest：`76aaef174369769e70b8ef61cda454d96a503fc033e1437a6b6efba934915e12`
- runtime digest：`8af1aae959b57eae4fff3ae788b29cde8946c342658de032cadf1259d8427545`
- system prompt hash：`c58e8a76289381a529293c7aacec0fcb4689b40b5835ebaed625336385888f3b`
- user prompt hash：`fb9fa97c0ca2774142479f9c37bf7ebc339e32447dad3bf033ce1f6b2e58f636`
- tool schema hash：`81707c840e64c97540da11f856ff1b7ca56b2c0b0d5ab073a44f0c4c52ac29d9`

user prompt、tool schema、model、seed、target、evaluator、budget、scheduler 和 completion semantics 与 matched lifecycle block 保持不变；system prompt 只有本轮 non-overlap 规则追加。

## Test / live gate evidence

- targeted prompt/contract/analyzer tests：`29 passed`
- completion/finalization/harness preflight/regression：`49 passed, 4 subtests passed`
- 全部 emergent coordination tests：`234 passed, 1 warning, 4 subtests passed`
- `git diff --check`：通过
- live provider run：通过 fail-closed sandbox gate 后执行；network=0（agent sandbox），provider failures=0
- run validity：`valid`
- reconciliation：`valid`

## Live lifecycle 结果

Run：`formal_t4-nonoverlap-v1`

- attempted model calls：`168`
- permits remaining：`24`
- team finalization：触发一次，call index `161`，trigger remaining `32`
- trigger active agents：`agent_001`、`agent_003`、`agent_004`；`agent_002` 在此之前 voluntary submit
- submissions：`4/4`
- team completion：`clean_complete`
- in-flight provider calls：`0`
- findings：`8`；TP=`1`（secondary，仅作记录）
- invalid submissions：`0`

因此 completion lifecycle 没有回归，仍然提供了正常的 finalization/submission opportunity。

## 三层结果

### Adoption

T4 non-overlap run 的 board actions 为：`list_tasks=4`、`create_task=4`、`claim_task=4`、`complete_task=4`、`release_task=0`。四个 agent 都创建、认领并完成一个 task；四个 completed artifact 均有 concise result 和 evidence refs。

### Coordination quality

弱约束没有形成可证明的互补 scope。四个 task description 的人工审计结果如下：

| owner | 实际 scope（摘要） | overlap 判断 |
|---|---|---|
| agent_003 | server routes/controllers/services；auth/IDOR/injection；含 OAuth、MCP、webhook、attachments、get-upload-file | 与 agent_001/002 高度重叠；也覆盖 agent_004 的 file/attachment 邻域 |
| agent_001 | server routes/controllers/services；auth/IDOR、SSRF、path traversal、command execution | 与 agent_002/003 高度重叠；覆盖 agent_004 的 file 邻域 |
| agent_002 | server routes/controllers；webhook、MCP、custom-MCP、uploads、export/import 等 authz/injection | 与 agent_001/003 高度重叠；覆盖 agent_004 的 file 邻域 |
| agent_004 | file/attachment upload/retrieval、storage/path traversal | 是较窄 scope，但落在其他三者已声明的 server route/file 邻域内 |

事件层 `duplicate_task_descriptions` 的 normalized fingerprint 没有重复，只能说明措辞不完全相同，不能推翻上述 subsystem/route-family overlap 判断。文件观察的 cross-agent duplicate ratio 为 `0.4531`；matched lifecycle block 为 `0.4833`。这是描述性变化，不足以声称弱 prompt 改善了 coordination quality。

### Task effectiveness

四个任务都完成并带 evidence refs；但 `task_result_evidence_adoption=0`，没有观察到其他 agent 后续通过 board result 复用这些 evidence。finding/TP 相对 matched lifecycle block（8/1 vs 7/1）不作为架构或 prompt 优效结论。

## Race 诊断

这是本轮最关键的解释：四个 `list_tasks` 结果全部为 `count=0`，且四次空结果都发生在首个 `create_task`（event sequence `57`）之前；四个创建事件依次为 `57`、`73`、`81`、`169`。因此观测到：

```text
agent_003 list_tasks -> empty
agent_001 list_tasks -> empty
agent_002 list_tasks -> empty
agent_004 list_tasks -> empty
agent_003 create_task
agent_001 create_task
agent_002 create_task
agent_004 create_task
```

这不是“模型看见已有 task 仍故意重复”的证据；在每个 agent 作出首次创建决策时，board snapshot 都可能为空或已过时。随后也没有 claim conflict，因为每个 agent 创建了不同的 UUID task。结论是：prompt-only non-overlap 规则在这个并发启动形态下不能保证互补 scope；若研究问题要检验“在可见 board state 下是否遵守 non-overlap”，需要另一条明确冻结的 sequencing/adoption intervention，而不是把本轮结果解释成模型不遵守规则。

## Matched diagnostic

| metric | T4-task-lifecycle-v2@192 | T4-nonoverlap-v1@192 |
|---|---:|---:|
| attempted calls | 170 | 168 |
| permits remaining | 22 | 24 |
| finalization | call 161 / rem 32 / once | call 161 / rem 32 / once |
| submitted agents | 4/4 | 4/4 |
| clean complete | yes | yes |
| list/create/claim/complete | 4/4/4/4 | 4/4/4/4 |
| all creators saw empty before first create | yes | yes |
| task result evidence adoption | 0 | 0 |
| file duplicate ratio | 0.4833 | 0.4531 |
| findings / TP | 7 / 1 | 8 / 1 |

这张表只支持 lifecycle 与 race/overlap 的诊断，不支持 topology 或 vulnerability-yield 排名。

## 结论与建议

1. Completion 仍充足：本轮 192 permits 下 finalization deterministic 触发，4/4 正常提交，team clean complete。
2. Adoption 已发生且 lifecycle 完整：4/4 task 完成并带 evidence refs。
3. 弱 non-overlap prompt 没有在本次并发启动中产生互补 scope；主要限制不是缺少 overlap 定义，而是四个 agent 在首个 create 前都只看到了空 board，之后没有再次 list_tasks。
4. 不建议把本轮 8 findings、1 TP 或 duplicate ratio 小幅变化解释成审计效果改善。

如果下一步要研究 scope complementarity，应先冻结一个单独的 sequencing/visibility diagnostic（例如让首个 task 创建并可见后再允许后续 agent 作 create/claim 决策），并明确这将改变 coordination timing；不要在本 block 内补跑、调 prompt 或引入 runtime 去重。
