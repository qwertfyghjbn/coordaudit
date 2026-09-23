# Common runtime contract: `convergent_v2 @4096`

状态：本文件冻结后续 S/P/B/T/M 实验共用的 completion primitives、边界和日志口径。它不冻结 multi-agent team 的整体结束时机；`team completion trigger = TBD`。

## 1. Purpose

为 S、P、B、T、M 提供同一套可比较的 model-call/output、permit accounting、completion、submission 和 provenance contract。架构之间只能改变 coordination capability / topology；不得改变下列公共 completion semantics。

## 2. Runtime generation identity

* generation：`completion_v2`
* public policy：`convergent_v2`
* output ceiling：4096
* hard finalization：dispatch-level allowlist gate
* historical-only：2048 generation、`convergent_v1`、`scheduler_only`（advisory/bypassable）
* 生成契约参考：`docs/releases/flowise-3.1.3-repository-v1-s1-completion-v2-generation-contract-20260919.md`，prereg commit `8cc0f81`，runtime implementation commit `f624fda`

后续 run manifest 必须记录 generation、policy、implementation commit、prompt profile、model/provider、output ceiling、permit contract 和所有 digests；不能仅依赖目录名推断世代。

## 3. Model-call/output contract

* `max_output_tokens = 4096`，每次 model call 固定；submission payload 截断必须记录。
* provider/model/config 必须冻结并逐 run 记录；当前正式基线为 `openai_compatible / deepseek-flash / thinking=disabled / temperature=0.0`。
* call role 必须记录为 exploration / submission / coordination / manager / worker 等现有 role；记录 `output_tokens`、`max_output_tokens`、`finish_reason` 和 ceiling hit。
* prompt profile 和 finding schema 固定为 `repository_v1`；Agent-visible target、base audit prompt 和可见工具集合在 matched block 内一致。

## 4. Permit/budget contract

继续使用 team-level hard permit accounting：所有 Agent 共享一个不可超出的 permit ledger；每次 provider call（含 retry）占用可审计 permit，不能由 Agent 私自增加配额。`max_steps` 只能作为安全上界，不能替代 team-level ledger。

后续 matched block 必须在 block manifest 中为 S/P/B/T/M 写同一个 hard-team permit policy、retry policy、wall-clock policy，并逐 run 记录 requested/granted/consumed/unused。`completion_v2 @4096` 的 S1 诊断 block 使用 128 permits；这不是未经下一阶段 block preregistration 就对 team N=4 偷渡的 allocation。

## 5. Completion primitives

公共 runtime 只提供以下 primitives：

1. frozen convergence guidance（当前 `convergent_v2` 的 system-prompt guidance）；
2. hard dispatch-level finalization gate；
3. structured `completion_phase_started`、`prohibited_tool_attempt` 和 submit/validator events；
4. convergence classification v2、behavioral stopping 和 submission completion 的独立 metrics。

Guidance 是 treatment；因此 guidance 下的首次 convergence source 只能记为 `guidance_consistent`，不能冒充 `spontaneous`。

## 6. Hard-finalization semantics

当 runtime 明确进入 finalization window 时，dispatch authorization 层只允许 `submit_findings`。read/search/shell、repository exploration、coordination acquisition 和其他工具在参数解析、sandbox 访问之前硬拒绝；拒绝不执行、不泄漏 target 内容、不恢复工具面，并记录 `prohibited_tool_attempt`（agent、step、call、requested tool、policy、arguments hash/bytes、rejected_by）。malformed、旧 schema、手工构造和重放 tool name 都不能绕过 gate。

hard finalization 是 fail-safe，不是 cognitive convergence，也不规定 team 何时开始 finalization。

## 7. Convergence classification v2

首次可信 convergence expression 必须 trace-review；regex 只能生成 candidate。来源枚举和优先级为：`finalization_induced` > `nudge_induced` > `guidance_consistent` > `spontaneous`，另有 `ambiguous` 和 `not_observed`。详细 rubric、expression excerpt、transcript ref 和 12-run回溯见 [convergence-classification-v2-20260919.md](convergence-classification-v2-20260919.md)。schema version=`2`。

强 expression 必须表达“证据足够且转向结束/提交”；弱的“找到几个问题”“可能够了”或 validator rejection 后机械重试不算。无 guidance、无 nudge、无 finalization 的可信 expression 即使后续继续探索，也仍是 `spontaneous`。

## 8. Behavioral stopping definition

从首次 convergence 起，单独记录是否实际停止 read/search/shell、repository exploration、新 hypothesis 扩张和非必要 coordination acquisition；记录 `last_exploration_step` 与 `exploration_calls_after_convergence`。`cognitive=yes, behavioral=no` 是合法且必须保留的状态，C/none step 120 是 canonical example。

## 9. Submission completion definition

submission completion 仅在 `submit_findings` attempt 的完整 payload 通过相同 finding schema 和 evidence validator，并生成 accepted submission 时成立。记录每个 attempt、validator rejection、malformed arguments、first attempt、accepted step 及 convergence→attempt/accepted gaps。rejection 不等于“没有漏洞”，也不重评分 finding。

## 10. Logging requirements

每次 run 至少记录：`call_role`、`output_tokens`、`max_output_tokens`、`finish_reason`、ceiling hit、first convergence（step/source/confidence/transcript ref/excerpt/rationale）、last exploration、exploration-after-convergence、submission attempts、accepted/rejected reasons、finalization start、hard-finalization binding、prohibited attempts、evidence refs/lineage、provider/infrastructure outcomes，以及 generation/policy/prompt/schema/tool/runtime digests。

日志必须保持 Agent-visible 与 hidden evaluator/provenance 隔离；hidden ground truth、source case labels 和 evaluator private data 不得进入 mount、tool output 或 prompt。

## 11. Generation isolation

旧 2048 / `convergent_v1` / `scheduler_only` / 可绕过 finalization 的 runs 只作 historical diagnostic，不改原始 events/transcripts/artifacts，不混入新 generation 的主指标。新 run 必须使用 `completion_v2`、4096、hard finalization；跨世代比较必须显式报告 output ceiling、policy value 和 gate event 差异。

## 12. Frozen digests and references

| component | reference |
|---|---|
| completion policy / gate payload | `66f3e83ae3e2dbaa988a36f6a55a325d60f8e0200e2dcef6912c3a54b42f4e44` (`harness/completion.py`) |
| dispatch gate implementation | `31ad7fd49353dde98c935749c2b63986845a38440da86d3c41f1eacc64e002ad` (`harness/agent_loop.py`) |
| frozen prompt profile | `74e77ae6d5de1a8f202a4563306b70dc51ba6d81b46ff818d3cc0d9b87ed8a2e` (`harness/prompts.py`) |
| repository-v1 finding schema module | `72b3e8968f12178bfbf83817df188010507d93f15ae47f7cc4d58875ec5f2e5d` (`harness/findings.py`) |
| canonical tool schema | `d3491ddcc5ad36ee9303d3cabb7d1e90fc8912d6e21dcb604fc812d27129cdb2` |
| convergence-classification-v2 implementation | `d978f5cd0583741b4214b6089f64636d0c96665acabc1709a00c0178cc49922a` (`analysis/convergence_classification.py`) |
| runtime generation contract | prereg `8cc0f81`; implementation `f624fda`; this contract is a documentation freeze layered on them |

The schema module digest covers both legacy and repository-v1 exports; the frozen schema identity is explicitly `repository-v1` and must be recorded in every manifest.

## 13. Known limitations and unresolved team semantics

The 12-run source review is one case, one model, thinking disabled, and n=3 per condition. Source classification is causal trace review, not a claim about hidden cognition. Harness nudge instrumentation and provider output ceilings can be confounded and must remain visible in reports.

This contract intentionally does **not** define `team completion trigger`. It does not implement or imply: simultaneous finalization at max-step reserve, “any Agent submit ends team”, or “manager submit kills workers”. P4/B4/T4/M4 task lifecycle, waiting, manager-report state, and whole-team completion are next-stage research questions.

