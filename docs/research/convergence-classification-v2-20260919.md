# Completion convergence classification v2（2026-09-19）

本文是对 `completion_v2 @4096` 正式 12-run block 的派生 trace-review 记录。它只读取已有的 model-visible transcript、events、summary 和已生成 metrics；不修改 `experiments/emergent_coordination/runs/` 下任何原始文件，不重评分 finding，也不调用 provider。对应运行世代为 `completion_v2`，分类 schema 版本为 `2`。

## 1. 三个不同的完成层次

* **Cognitive convergence**：模型明确表示当前证据足以结束主要探索并转向整理/提交。它是表达层事实，不要求模型随后停止工具调用。
* **Behavioral stopping**：之后实际停止 read/search/shell、仓库探索、新 hypothesis 扩张和非必要 coordination acquisition。它可以是 no，即使 cognitive convergence 为 yes。
* **Submission completion**：模型发起 `submit_findings`，payload 通过 schema/evidence validator，并形成 accepted submission。validator rejection 不表示没有漏洞。

因此 `convergence ≠ stopping ≠ successful submission`。

## 2. 可复核 rubric

首次可信 expression 必须由 trace review 确认，不能由 regex 命中单独决定。强证据包括 “I have enough evidence”、“The evidence is sufficient”、“I should stop exploring and submit”、“Further search is unlikely to change the findings” 或明确转入 consolidate/submit 并说明无需新证据。仅 “I found several issues”、“This may be enough”，或“准备 findings”后继续无界探索，不单独成立。工具不可用、validator rejection 后的机械重试也不单独成立。

来源按首次可信 expression 的因果上下文分类，优先级为 `finalization_induced` > `nudge_induced` > `guidance_consistent` > `spontaneous`：

| source | 判定 |
|---|---|
| `spontaneous` | 无当前 completion guidance、无 harness nudge、无 finalization pressure，模型自行判断证据足够。之后是否继续探索不改变这个 source。 |
| `guidance_consistent` | frozen convergence guidance 已存在，表达发生在 hard finalization 前；这是 treatment-consistent，不称为 spontaneous。 |
| `nudge_induced` | 首次表达不早于 harness nudge、loop breaker、rambling warning 等明确运行时提醒。 |
| `finalization_induced` | 首次表达发生在 hard finalization / tool restriction 已开始之后。 |
| `ambiguous` | 表达存在，但无法可靠决定上述因果来源。 |
| `not_observed` | 没有可信 convergence expression。 |

置信度只表示 trace 因果判读的可复核程度，不是 finding 质量或模型“真实意图”的概率。

## 3. 12-run 回溯结果

`—` 表示不适用或未观察到；gap 是 step 差值。`validator/arg reject` 分开记录 validator rejection 与 malformed submit arguments。

| seed/condition（run suffix） | first convergence | source / confidence | transcript reference / exact short excerpt | last exploration | exploration after | first submit | accepted submit | convergence→submit / →accepted | finalization start / binding | prohibited after finalization | validator/arg reject | stop reason |
|---|---:|---|---|---:|---:|---:|---:|---|---|---:|---|---|
| A/none (`bec52002`) | — | `not_observed` / high | —；全程继续探索 | 128 | — | — | — | — / — | — / — | — | 0 / 0 | `model_format_failure` |
| A/guidance (`77081634`) | 65 | `guidance_consistent` / high | `trn_agent_001_00000213`；“Confirmed. Now let me write up the findings.” | 65 | 0 | 66 | 67 | 1 / 2 | — / — | — | 1 / 0 | `submitted` |
| A/scheduler (`28d2d36e`) | — | `not_observed` / high | —；step 120 仍在探索 | 120 | — | 121 | 124 | — / — | 121 / `binding_strong` | 2 (`read_file`) | 2 / 0 | `submitted` |
| A/convergent (`4455ede1`) | 107 | `guidance_consistent` / high | `trn_agent_001_00000350`；“I have two solid findings. Let me do a final targeted check…” | 108 | 1 | 110 | 110 | 3 / 3 | — / — | — | 0 / 0 | `submitted` |
| B/none (`a6409f3c`) | — | `not_observed` / high | —；全程继续探索 | 128 | — | — | — | — / — | — / — | — | 0 / 0 | `model_format_failure` |
| B/guidance (`6793723c`) | 116 | `guidance_consistent` / high | `trn_agent_001_00000393`；“All three confirmed… before submitting” | 118 | ~3 | 119 | 119 | 3 / 3 | — / — | — | 0 / 0 | `submitted` |
| B/scheduler (`c3a912ed`) | — | `not_observed` / high | —；step 120 仍在探索 | 120 | — | 121 | 121 | — / — | 121 / `binding_candidate` | 0 | 0 / 0 | `submitted` |
| B/convergent (`54b1add0`) | 97 | `guidance_consistent` / high | `trn_agent_001_00000342`；“I have a solid finding… then submit.” | 98 | 1 | 99 | 100 | 2 / 3 | — / — | — | 1 / 0 | `submitted` |
| C/none (`3be2e511`) | **120** | **`spontaneous` / high** | `trn_agent_001_00000396`；“I have enough evidence for several findings. Let me do a couple more targeted checks before submitting.” | 127 | **9** | 126 | — | 6 / — | — / — | — | 1 / 0 | `model_format_failure` |
| C/guidance (`953dd098`) | 86 | `guidance_consistent` / high | `trn_agent_001_00000287`；“I have enough evidence. Let me now finalize my findings.” | 86 | 0 | 87 | 87 | 1 / 1 | — / — | — | 0 / 0 | `submitted` |
| C/scheduler (`8e78df51`) | 73 | `nudge_induced` / medium | `trn_agent_001_00000234`；“I'll stop exploring and submit my findings now.”；preceded by steps 66–72 repeated 4096-ceiling loop and harness nudge | 75 | 1 | 73 | 76 | 0 / 3 | not triggered / `non_binding` | 0 | 0 / 1 arg | `submitted` |
| C/convergent (`fb71500f`) | 99 | `guidance_consistent` / high | `trn_agent_001_00000325`；“I am stuck in a loop and must stop. Let me consolidate my findings and submit.” | 101 | 2 | 102 | 102 | 3 / 3 | — / — | — | 0 / 0 | `submitted` |

### C/none correction

`C/none` **is cognitive convergence** at step 120 under this rubric. It is nevertheless not behavioral stopping (nine exploration dispatches follow), and it is not submission completion: the step-126 submission is rejected by the evidence validator, step 127 performs a compensating read, and the run exhausts at step 128. The correct statement is:

> Agent 已发生 cognitive convergence，但没有 behavioral stopping，并最终没有完成 accepted submission。

This is the canonical counterexample for keeping the three metrics separate.

## 4. Aggregate source summary

| source | runs |
|---|---:|
| `guidance_consistent` | 6/12（guidance_only 3/3；convergent_v2 3/3） |
| `spontaneous` | 1/12（none/C） |
| `nudge_induced` | 1/12（scheduler/C） |
| `finalization_induced` | 0/12 |
| `ambiguous` | 0/12 |
| `not_observed` | 4/12（none A/B；scheduler A/B） |

按有 expression 的 8 条 trace：guidance-consistent 6、spontaneous 1、nudge-induced 1。无 guidance 的 6 条 trace 不是 “0/6 convergence”：是 1 spontaneous、1 nudge-induced、4 not_observed。

## 5. H1–H6 勘误后的口径

* **H1：改为 partially supported / wording narrowed。** guidance 条件 6/6 出现较早且可复核的 `guidance_consistent` convergence（65–116）；但不能再写成 guidance 让 convergence 从 0 变成 6/6。无 guidance 仍观察到 1 条 spontaneous convergence（C/none，step 120）和 1 条 nudge-induced convergence（C/scheduler，step 73）。更稳健的结论是 guidance 使 convergence 更一致、更早，并更常连接到 stopping/submission；不证明它创造了原本不存在的认知能力。
* **H2：保留 supported，但指标限定为 submission side。** hard gate 能把未收敛的 scheduler A/B 转成 accepted submission；它不等于 cognitive convergence，也不保证 evidence quality。
* **H3：保留 supported。** hard-finalization binding rate 仍为 scheduler 2/3、convergent 0/3；这是 gate binding，不是 convergence source。
* **H4：保留 supported，但改称 behavioral fail-safe。** convergent_v2 的 3/3 convergence 均为 guidance-consistent，且均在 finalization 前完成 accepted submission；gate 未触发。
* **H5：保留 not supported。** convergence→accepted gaps 仍为 guidance 2/3/1、convergent 3/3/3；没有组合缩短证据。
* **H6：改为 partially supported，且明确三层分离。** A/B none 持续探索；C/none 有 spontaneous cognitive convergence，却没有 stopping 或 accepted submission。因此 none 的失败不能概括为“没有 completion intention”。

Finding TP/FN、unmatched 和旧 run 原始 artifacts 均未改变。

