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
| `structured_team` (`Tn`) | `--mode structured_team --agents N` | tasks + messages + artifacts | structured board |

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

Self-claim task board with atomic `claim_task`, plus messages and artifacts. No pre-assigned team lead.

The interface is intentionally small so later modes (`manager_worker`, `fixed_roles`, `fixed_graph`) can be added as new policies.

## Leakage policy

Agent-visible files must not contain:

- `PT-PY`, `SSRF-PY`, `SSTI-PY`
- `CVE`, `VULN`, `FIXED`
- `ground_truth`
- original case IDs
- evaluator provenance

Ground truth, source-case IDs, and canonical reports stay in `evaluator_private/` and are copied only into `runs/<id>/evaluator_private/`, which agent tools refuse to read.

## Evaluation

Scoring is deterministic first:

- file / function / sink / category aliases
- positive targets `GT-001`..`GT-003` are required hits
- near-miss paths `NM-001`/`NM-002` are **not** required finds
- a finding aimed at a near-miss path is a false-positive penalty

Reported metrics:

- `TP` `FP` `FN`
- precision / recall / F1
- `verified_findings`
- `duplicate_findings`
- `near_miss_false_positives`
- per-finding match explanation

An LLM semantic judge is **not** used in v0.

## Budget model

Every run has a **shared global** budget plus optional per-agent caps:

- `global_input_token_cap`
- `global_output_token_cap`
- `per_agent_token_cap`
- `max_llm_calls`
- `wall_clock_timeout`

Global caps are not `N × per-agent`. This is required so later `P16 / B16 / T16` comparisons keep the same total budget.

Token fields that a provider does not expose are stored as `null`. Dollar prices are not written into run history.

## Reproducibility

Unit / mock tests, no live model:

```bash
python3 -m unittest discover -s experiments/emergent_coordination/tests -t . -v
```

Target-visible smoke tests:

```bash
python3 -m unittest discover -s experiments/emergent_coordination/repositories/repository_pilot_v0/tests -v
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

Analyze a finished run:

```bash
python3 -m experiments.emergent_coordination.analysis.analyze_run runs/<run_id>
```

The analyzer reports evidence (`shared_path_activity`, `cross_agent_reads`, filename prefixes). It does **not** claim that a leader or mailbox emerged.

## Known limitations

- Only five hidden cases.
- Work-front count is small.
- The application is synthetic.
- This is not enough to conclude anything about 16/32-agent scaling.
- Shared helpers are deliberately shallow; there is no engineered cross-vulnerability knowledge-propagation graph.
- The main use is harness validation.

Next technical step, **not executed here**: run 4/8-agent P/B/T pilots and inspect whether `/shared` or the task board produces meaningful cross-agent communication before designing `repository-v1`.
