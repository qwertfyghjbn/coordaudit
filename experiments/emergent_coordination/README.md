# Emergent Coordination Pilot

This directory is a **harness-validation pilot**, not a formal multi-agent benchmark.

It exists so later 4/8/16/32-agent comparisons can vary coordination mode without being contaminated by:

- benchmark metadata leakage
- shared working-tree races
- unequal global budgets
- evaluator-private files in the agent sandbox
- judge-LLM variance as the default scorer

The current target is `repository-pilot-v0`.

## Purpose

Build a repeatable, leak-resistant, automatically scored environment for repository-level multi-agent auditing.

The pilot reuses five existing synthetic Python repository cases and recomposes them into **one anonymous application**. Agents see a normal Flask workspace, not five labeled benchmark folders.

## Non-goals

This is **not**:

- a proof that any multi-agent architecture is better
- a formal `repository-v1` benchmark
- a 16/32-agent scaling study
- a knowledge-propagation experiment with engineered shared tricks
- a replacement for `datasets/` or canonical results

Do not write pilot scores into `reports/cross_system/canonical_results.tsv`.

## Source cases

Private provenance, evaluator-only:

| Hidden target | Source case | Role |
|---|---|---|
| `GT-001` | `PT-PY-REPO-001` | positive |
| `GT-002` | `SSRF-PY-REPO-001` | positive |
| `GT-003` | `SSTI-PY-REPO-001` | positive |
| `NM-001` | `PT-PY-REPO-002` | near-miss / false-positive trap |
| `NM-002` | `SSRF-PY-REPO-002` | near-miss / false-positive trap |

Original `datasets/synthetic/*` files are immutable. Provenance lives only under `evaluator_private/`.

## Layout

```text
experiments/emergent_coordination/
  repositories/repository_pilot_v0/   # agent-visible target
  evaluator_private/                  # ground truth + provenance, never mounted into agent tools
  manifests/repository_pilot_v0.json
  harness/                            # S/P/B/T runner
  evaluator/                          # deterministic scoring
  analysis/analyze_run.py
  tests/                              # leak, regression, isolation, mock harness
  runs/                               # generated run directories
```

Agent runtime for a single run:

```text
runs/<run_id>/
  runtime/target/          # clean snapshot
  runtime/private/<agent>/ # private copy + scratch
  runtime/shared/          # empty unless mode = raw_blackboard
  evaluator_private/       # not on the agent search path
  logs/events.jsonl
  run_manifest.json
```

## Harness modes

All modes use the same `AgentRunner`. Mode differences are a `CoordinationPolicy`.

| Mode | CLI | Communication | Shared state |
|---|---|---|---|
| `single` (`S1`) | `--mode single --agents 1` | none | none |
| `parallel` (`Pn`) | `--mode parallel --agents N` | none | none |
| `raw_blackboard` (`Bn`) | `--mode raw_blackboard --agents N` | none by default | raw `/shared` filesystem |
| `structured_team` (`Tn`) | `--mode structured_team --agents N` | typed task state | structured board |

`N` can be `2`, `4`, `8` now. The same runner accepts `16` and `32` without code changes. Do **not** start those expensive runs from this pilot.

### S — Single

One agent, full private target copy, shell/read/test/scratch, no shared communication.

### P — Independent parallel

`N` agents, identical broad audit objective, independent private copies. No shared directory. No scheduler that assigns vulnerability types.

### B — Raw blackboard

Same private copies as P, plus an initially empty `/shared`.

Allowed primitives: `list`, `read`, `create`, `mkdir`. Create-only / append-friendly. No `send_message()`, `claim_task()`, mailboxes, or pre-created `/shared/tasks`.

The B-mode prompt does **not** tell agents they are a team, to cooperate, to elect a leader, or to inspect other agents.

### T — Structured team

The primary N=4 treatment exposes only `create_task`, `list_tasks`, `claim_task`, `release_task`, and `complete_task`. A completed task records its result and evidence references. No pre-assigned team lead, messaging, or artifact channel is exposed.

The interface is intentionally small so later modes (`manager_worker`, `fixed_roles`, `fixed_graph`) can be added as new policies.

## 冻结的 N=4 实验合同

[`manifests/n4_pilot_v0.json`](manifests/n4_pilot_v0.json) 是 S1/P4/B4/T4 的唯一合同来源：四个 condition 共享 `deepseek-flash` 请求别名、显式 non-thinking mode、温度 0、每次最多 1024 output tokens、32 个团队共享调用许可，以及 32-step 非配额安全上限；N=4 不允许 per-agent token cap。non-thinking 是合同的一部分：DeepSeek thinking mode 不实际应用 temperature，不能与温度为 0 的 matched condition 混用。

以下命令只创建不可覆盖的 block manifest，记录 target、private evaluator、runtime、prompt、tool schema 与 Git 状态的 digest；它**不执行模型调用**：

```bash
python3 -m experiments.emergent_coordination.freeze_block \
  --block-id n4-pilot-replicate-01
```

调用前 permit、fail-closed sandbox、模型可见转录/reconciliation、严格 finding intake 与 hidden verification 已按 ADR 0002–0005 实现并有回归测试。`freeze_block.py`/`BlockRunner` 仍是**只冻结、不执行**的合同工具，所以它生成的 `block_manifest.json` 固定标记 `live_gate=blocked`：这不是对上述能力缺失的描述，而是防止把一个未由 block executor 绑定、校验和调度的 manifest 当作 live 运行授权。单条 live run 可由 `run_experiment.py` 在 sandbox 自检通过后执行；正式 matched block 仍必须额外保证四个 condition 绑定同一冻结合同，并在任一 infrastructure-invalid run 后整体停止和重跑。

## Leakage policy

Agent-visible files must not contain:

- `PT-PY`, `SSRF-PY`, `SSTI-PY`
- `CVE`, `VULN`, `FIXED`
- `ground_truth`
- original case IDs
- evaluator provenance

Ground truth, source-case IDs, and canonical reports stay in `evaluator_private/` and are copied only into `runs/<id>/evaluator_private/`, which agent tools refuse to read.

## Shell isolation

每次 `run_shell` 都在独立 bubblewrap namespace 中执行：`target` 只读绑定到 `/work/target`，仅当前 Agent 的 `scratch` 可写绑定到 `/work/scratch`，其余运行目录、其他 Agent、shared/task state 与 `evaluator_private` 均不挂载。namespace 使用私有 PID/IPC/UTS/proc/tmp/dev 与 `--unshare-net`，并以环境 allowlist 启动 `/bin/sh -lc`；不会回退到宿主 shell。live run 在启动前必须通过同一 sandbox 自检，失败即拒绝运行。

## 可重放事件与模型可见转录

每个 run 的 `logs/events.jsonl` 是稳定的事件索引：它含顺序化 `event_id`、父事件引用、outcome、预算进度、内容 hash 和 artifact/转录引用，不内联模型或工具正文。`logs/transcripts/<agent>.jsonl` 以 append-only 方式保存每次模型实际收到的 messages/tool schema、模型响应和进入后续上下文的截断工具结果；`logs/artifacts/<agent>.jsonl` 保存从事件索引移出的参数、命令、结果和错误正文。

写盘前会确定性移除 API 凭证、授权头、敏感 provider 参数与宿主绝对路径。若转录或 artifact 触及 hidden evaluator/private 内容，正文会被替换为脱敏标记，run 在结束 reconcile 时被标记为 `infrastructure_invalid`。reconcile 同时验证事件/转录序号、正文 hash、引用完整性，以及每一个 permit ledger 条目都对应一次 LLM 调用和所需转录。

## Evaluation

finding intake 会在接受前对完整 payload 做原子式冻结 schema 校验。每个 finding 必须使用 canonical category、明确的 source/sink anchor，以及 Agent 自己 `read_file` 得到的一个或多个 `evidence_ref`。T 条件下，Agent 也可在自己调用 `list_tasks` 并收到 `task_result_observed` 事件后引用该已完成任务明确列出的 evidence ref；这保留可审计的结果接收链，而不是把 task board 当作任意证据旁路。无效 payload 会逐字段返回错误，并可在团队 permit 尚未耗尽时重试；结束时仍没有有效 payload 的 Agent 归类为 `model_format_failure`，而非 infrastructure failure。

hidden evaluator 只有在 canonical category 与 source/sink anchor 均匹配时才确认 positive。它以 `category + normalized source + normalized sink` 分组重复报告、私下保留全部 provenance，且每组至多计一个 TP。已知 near miss 是确定性 FP；schema 合法但不在冻结标签中的报告归为 `unmatched_review`，不自动断言为 false。

公开 `evaluation.json` 报告：

- positive recall
- known-near-miss false positives, unmatched review, invalid submissions, and duplicates
- closed-world precision lower bound and labeled-only precision upper bound
- Agent reproduction claims separately from evaluator-verified findings

ground-truth assignment、anchors、duplicate provenance 与 verification detail 仅写入 `evaluator_private/verification.json`，不出现在公开评估输出中。v0 不使用 LLM semantic judge。

## Budget model

Every run has a **shared global** resource contract:

- `hard_team_call_permits`
- `wall_clock_timeout`
- provider-reported input/output/cached/reasoning token usage
- optional `token_stop_threshold`

`hard_team_call_permits` is acquired atomically before the provider request. Each attempted call consumes one permit, including timeout and provider-error attempts; the OpenAI-compatible client has SDK retries disabled. The harness-controlled retry policy is frozen in the run manifest, and every retry obtains a fresh permit. The contract is not `N × per-agent`.

`token_stop_threshold`（如配置）只在 provider 回报实际 input/output usage 后阻止后续调用，不退还已发放 permit；为保证最多一次 in-flight overshoot，启用该阈值时只允许一条未结算 provider 请求。它不是精确的 token admission budget。

Token fields that a provider does not expose are stored as `null`. Dollar prices are not written into run history.

## Reproducibility

Unit / mock tests, no live model:

```bash
python3 -m unittest discover -s experiments/emergent_coordination/tests -t . -v
```

Target-visible smoke tests:

```bash
(cd experiments/emergent_coordination/repositories/repository_pilot_v0 && \
  python3 -m unittest discover -s tests -v)
```

Mock harness run:

```bash
python3 experiments/emergent_coordination/run_experiment.py \
  --mode single --agents 1 --mock --smoke-budget
```

Tiny live smoke, only if credentials already exist in the environment:

```bash
python3 experiments/emergent_coordination/run_experiment.py \
  --mode single --agents 1 --live --smoke-budget --max-steps 4
```

Missing credentials is not a failure. Do not start 16/32-agent runs from this tree.

在运行任意 Agent 前，可先执行不挂载 target、不提交 finding 的 provider compatibility probe：

```bash
python3 experiments/emergent_coordination/compatibility_smoke.py --model deepseek-flash
```

它强制一次无副作用的 function call，并验证 tool-result continuation、provider 的 resolved model、fingerprint（若提供）与 usage 字段。probe 不属于任何 coordination condition，也不构成 matched block。

Analyze a finished run:

```bash
python3 -m experiments.emergent_coordination.analysis.analyze_run runs/<run_id>
```

每个完成的 run 会自动写入 `metrics.json`。它包含规范化的文件/search/source→sink hypothesis/test 指纹、跨 Agent 重复工作、permit/token/active-time/并发/Gini、B 的 shared 路径和内容 hash lineage，以及 T 的 claim conflict、未完成任务、重复任务和显式 evidence adoption。

对冻结 block 可显式绑定各 condition 的 run，再生成 `block_comparison.json`：

```bash
python3 -m experiments.emergent_coordination.analysis.analyze_run \
  --block-dir runs/<block_id> \
  --condition-run S1=runs/<s1_run> \
  --condition-run P4=runs/<p4_run> \
  --condition-run B4=runs/<b4_run> \
  --condition-run T4=runs/<t4_run>
```

分析器只报告可观察证据：路径相邻、一次 shared read、任务被列出或时间相邻均不自动解释为协作、采纳、领导或意图。只有后续 finding 显式复用已观察 task result 中的同一 `evidence_ref`，才记为 task-result evidence adoption。

## Known limitations

- Only five hidden cases.
- Work-front count is small.
- The application is synthetic.
- This is not enough to conclude anything about 16/32-agent scaling.
- Shared helpers are deliberately shallow; there is no engineered cross-vulnerability knowledge-propagation graph.
- The main use is harness validation.

Next technical step, **not executed here**: run 4/8-agent P/B/T pilots and inspect whether `/shared` or the task board produces meaningful cross-agent communication before designing `repository-v1`.
