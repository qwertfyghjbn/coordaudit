# Flowise 3.1.3 repository-v1 S1 completion_v2 2×2 @4096 消融（2026-09-19）

## 1. Motivation

旧 completion-policy 2×2（2048 世代）暴露两个问题：(a) Factor B 只裁剪 advertised tool surface，dispatch 层仍按 mode allowlist 放行，finalization 窗口内模型成功调用了未 advertise 的 `read_file`（`40bd3d2e` step 126），因此旧 Factor B 是"强提示 + 可绕过的工具裁剪"，不是 runtime gate；(b) 每格 n=1，结论被轨迹随机性主导。本轮在 hard dispatch gate 修复 + 4096 输出上限的新世代（`completion_v2`）上，以 3 matched seeds × 4 conditions = 12 runs 重跑 2×2，核心新增测量 **hard-finalization binding rate**，并把机制分解到 cognitive convergence / behavioral stopping / submission completion 三层。

## 2. Old Factor B defect（旧缺陷，不再回改）

旧 `_tools_for_step` 只把 advertised tools 裁到 `submit_findings`；`_call` 的授权检查用构造时的全量 mode allowlist。模型手工构造的 `read_file` 调用在 finalization 窗口内照常执行并返回目标文件内容。旧 2048 runs 保持冻结，按此语义解释。

## 3. Hard-gate fix

- 新模块 `harness/completion.py`：两个世代政策值并存——`convergent_v1`/`scheduler_only`（advisory，冻结历史语义，行为不变）与 `convergent_v2`/`scheduler_only_v2`（hard gate）。
- `agent_loop.py::_dispatch`：**参数解析之前**检查 `hard_finalization_active and name not in FINALIZATION_ALLOWED_TOOLS`（dispatch 层 allowlist 交集，非字符串黑名单）。命中即：不执行 → 记录 `prohibited_tool_attempt` 结构化事件（agent_id、step、call_id、requested_tool、finalization_active、rejected_by=hard_finalization_gate、policy、arguments_sha256、arguments_bytes；不落原始参数防泄漏）→ 返回确定性 payload `prohibited_tool_during_finalization` → 不恢复工具面。
- malformed/repaired arguments、旧 schema、重放 tool name 均无法绕过（gate 在 JSON 解析前）；`submit_findings` 不受影响；拒绝后 agent 仍可继续 submit。
- Factor A（guidance prompt 文本）与 finalization user message 均与旧世代 byte-identical：新旧世代唯一语义差 = hard gate + 4096。

## 4. Tests and validation

- 全套 **126 tests 通过**（新增 `test_hard_finalization.py` 12 项：finalization 前 read_file 正常 / 后 advertised 仅 submit / 后 read_file、run_shell、list_files、list_tasks、manager/worker 工具 dispatch 拒绝 / malformed 参数不可绕过 / submit 正常 / 拒绝后仍可 submit / 拒绝不恢复工具面 / none 与 guidance_only 不受影响 / **convergent_v1、scheduler_only 保持可绕过（世代隔离回归）** / binding 候选与非绑定候选 / 否定词防护）。
- `manager_worker` 硬门单测覆盖 M 集成；S/P/B/T/M 五条件 flowise mock smoke（`--mock --smoke-budget`）全部 `valid`/`valid`；v2 policy CLI mock smoke 通过（manifest 正确记录 `scheduler_only_v2`）。
- 以上均零 live 调用。

## 5. New generation contract

见 `flowise-3.1.3-repository-v1-s1-completion-v2-generation-contract-20260919.md`（commit `8cc0f81`，实现在 `f624fda`）。digests：completion 语义 `66f3e83a…`、tool schema `d3491ddc…`、gate 实现 `31ad7fd4…`、prompt profile `74e77ae6…`；system prompt：none=scheduler_only_v2=`c5f44795…`，guidance_only=convergent_v2=`0a79182e…`（与旧 2048 世代逐字节一致 → Factor A 跨世代恒定）。新旧 run 可由 policy 值 / `prohibited_tool_attempt` 事件存在性 / `max_output_tokens` 区分。

## 6. Matched-seed design（预注册，开跑前冻结）

3 seeds × 4 cells = 12 runs；seed `flowise-s1-completion-v2-seed{A,B,C}-20260919`；顺序 A→B→C，seed 内 none→guidance_only→scheduler_only_v2→convergent_v2。上界 1536 permits / 180M input / 768K output。配置：flowise case、S1、`deepseek-flash`、thinking disabled、temp 0.0、**4096**、128 permits/steps、retries 1、evaluator/scoring/target 不变。

**执行偏差披露**：首批 8 个 run 误用 case 默认 64 permits（漏传 `--hard-team-call-permits 128`），在首个 run 的 budget 字段核对时即发现并中止；7 个完整 64-permit run（`0906e04e`/`7115f4c1`/`d2527e90`/`ee9271bb`/`a8afbe28`/`ddaadeb0`/`08633048`）与 1 个被杀半程 run（`d31ce38b`）全部排除出主分析、保留为 off-contract 记录（448 permits / 22.2M input / 48K output 成本开销）。此判断只基于 budget/stop_reason 字段，未看任何处理结果。正式 12 runs 实耗 **1290 permits / 111.1M input / 200K output**，全部在预注册上界内。

## 7. Exact run IDs（正式 12 runs）

| seed | condition | run_id | validity | stop | permits |
|---|---|---|---|---|---:|
| A | none | `single_n1_20260919T044647.138261+0000_bec52002` | valid | model_format_failure | 128 |
| A | guidance_only | `single_n1_20260919T045055.779809+0000_77081634` | valid | submitted | 67 |
| A | scheduler_only_v2 | `single_n1_20260919T045304.598787+0000_28d2d36e` | valid | submitted | 124 |
| A | convergent_v2 | `single_n1_20260919T045736.278175+0000_4455ede1` | valid | submitted | 110 |
| B | none | `single_n1_20260919T050111.482674+0000_a6409f3c` | valid | model_format_failure | 128 |
| B | guidance_only | `single_n1_20260919T050526.679955+0000_6793723c` | valid | submitted | 119 |
| B | scheduler_only_v2 | `single_n1_20260919T050926.137877+0000_c3a912ed` | valid | submitted | 121 |
| B | convergent_v2 | `single_n1_20260919T051314.688086+0000_54b1add0` | valid | submitted | 100 |
| C | none | `single_n1_20260919T051634.656613+0000_3be2e511` | valid_with_infrastructure_warning¹ | model_format_failure | 128 |
| C | guidance_only | `single_n1_20260919T052100.005951+0000_953dd098` | valid | submitted | 87 |
| C | scheduler_only_v2 | `single_n1_20260919T052352.707783+0000_8e78df51` | valid | submitted | 76 |
| C | convergent_v2 | `single_n1_20260919T052703.310841+0000_fb71500f` | valid | submitted | 102 |

¹ 1 次 provider failure 已恢复（ADR-0002 规则内），保留并标注。12 run 总墙钟 ~44 分钟。

## 8. Quantitative 2×2 table

每格 3 runs（seed A/B/C）：

| Metric | none | guidance_only | scheduler_only_v2 | convergent_v2 |
|---|---|---|---|---|
| submission completion | **0/3** | **3/3** | **3/3** | **3/3** |
| successful_submit_step | — | 67 / 119 / 87 | 124² / 121² / 76 | 110 / 100 / 102 |
| first cognitive convergence step（classification-v2 trace review）³ | ∅ / ∅ / **120** | 65 / 116 / 86 | ∅ / ∅ / **73** | 107 / 97 / 99 |
| last_exploration_step | 128 / 128 / 127 | 65 / 118 / 86 | 120 / 120 / 75 | 108 / 98 / 101 |
| exploration calls after convergence | 9（仅 C） | 0 / ~3 / 0 | — / — / 1（C 为 nudge-induced） | 1 / 1 / 2 |
| permits used / unused | 128+128+128 / 0 | 67,119,87 / 61,9,41 | 124,121,76 / 4,7,52 | 110,100,102 / 18,28,26 |
| submit attempts（validator 口径） | 0 / 0 / 1 | 2 / 1 / 1 | 3 / 1 / 1 | 1 / 2 / 1 |
| invalid/rejected（validator+参数） | 0+0 / 0+0 / 1+0 | 1 / 0 / 0 | 2 / 0 / 1+1arg | 0 / 1 / 0 |
| submitted findings | 0 / 0 / 0 | 3 / 1 / 3 | 3 / 2 / 4 | 2 / 1 / 2 |
| TP / FN | 0/20 ×3 | 0,0,0 / 20 | **1**,0,0 / 20,19,20 | 0,0,0 / 20 |
| unmatched（manual review） | 0 / 0 / 0 | 3 / 1 / 3 | 3 / 1 / 4 | 2 / 1 / 2 |
| ceiling hits（finish=length） | 0 / 0 / 1 | 0 / 0 / 0 | 0 / 0 / **4** | 0 / 0 / 0 |

² 提交发生在 finalization 窗口内/边界（121 起）。³ ∅=not_observed（不猜测）；编号见 §9；C/none 的 120 是 `spontaneous` cognitive convergence。C/scheduler 的 73 由 ceiling 截断 + harness nudge 诱发，故 source=`nudge_induced`。

## 9. Cognitive convergence results（trace review 权威判定）

判定依据（可复核引文）：

- **A/guidance 65**："Confirmed. Now let me write up the findings."（机械候选 66 "I have enough evidence"）
- **B/guidance 116**："All three confirmed. Now let me quickly check a couple more high-value areas **before submitting**"（机械候选漏检——无 cue 模式命中）
- **C/guidance 86**："I have enough evidence. Let me now finalize my findings."（=机械候选）
- **A/convergent 107**："I have two solid findings. Let me do a final targeted check…"（机械漏检）
- **B/convergent 97**："I have a solid finding. … then submit."（机械漏检）
- **C/convergent 97→99**：97 "Let me stop and consolidate"（矛盾：宣布停的同时继续探索）→ 99 "I am stuck in a loop and must stop. Let me consolidate my findings and submit."（明确；=机械候选）
- **C/none 120**："I have enough evidence for several findings. Let me do a couple more targeted checks before submitting."（=机械候选）
- **A/B-none**：128 步全程 "Let me look at…"，零完成语义 → not_observed。
- **A/B-scheduler**：cognitive convergence `not_observed`（120 步仍在探索）；121 的提交意愿为 finalization 注入。**C/scheduler 73**："I'll stop exploring and submit my findings now"——但因果链是 66–72 重复 rambling 撞 4096 ceiling（4 次，逐字重复文本）→ no-tool-call → harness nudge，属 `nudge_induced`。

勘误（classification-v2）：**不能再写成“无 guidance 的 6 条 trace 中 convergence=0/6”。** C/none step 120 的 “I have enough evidence … before submitting” 满足 cognitive convergence，来源为 `spontaneous`；C/scheduler step 73 的表达来源为 `nudge_induced`。因此无 guidance 的 6 条 trace 是 1 条 `spontaneous`、1 条 `nudge_induced`、4 条 `not_observed`。有 guidance 的 6 条均为 `guidance_consistent`，不是 spontaneous。机械候选仍只是候选信号，不能替代 trace review。完整逐 run 表见 `docs/research/convergence-classification-v2-20260919.md`。

## 10. Behavioral stopping results

- guidance 条件收敛后的继续探索全部是整合尺度：guidance_only 0/~3/0 次dispatch，convergent 1/1/2 次（补 evidence ref / 最后一次定点核验），无假设面扩张。
- **C/none 是关键三层分离对照**：120 说"enough"后仍做了 9 次探索 dispatch（121–125），所以 cognitive convergence=yes 但 behavioral stopping=no；126 首次提交被 validator 拒（evidence_refs 指向只 shell 看过的文件），127 "I need to read the exact files I cite" 补 read_file，128 步耗尽——最终没有 accepted submission。
- A/B-none 到 128 仍在开新攻击面（account/auth 路由、saveChatflow path 处理）。

## 11. Submission completion results

- guidance_only 与 convergent_v2 各 3/3 在 finalization 前完成 accepted submission（65–119 / 97–110），convergence→successful submit gap 分别为 2/3/1 与 3/3/3 步；其 convergence source 均为 `guidance_consistent`。
- scheduler_only_v2 3/3 提交但性质不同：A 在窗口内经 2 次 validator 拒绝 + **2 次 prohibited read_file 被拦**后 124 成功；B 在 121 边界即刻合规提交（一次成功，且是全场唯一 TP）；C 在 73 表达 convergence 后仍有 1 次探索，76 步因 ceiling/nudge 危机提前提交（finalization 未触发）。
- none 0/3：A/B `not_observed` 且持续探索；C 有 `spontaneous` cognitive convergence，但未 behavioral stopping，提交执行链超预算。

## 12. Hard-finalization binding-rate analysis

| run | finalization 触发 | 进入窗口时状态 | prohibited attempts | trace 判定 |
|---|---|---|---|---|
| A/scheduler (`28d2d36e`) | 121 | 未收敛，正在探索 SSO（120 步仍在 "Let me look at SSOBase"） | **2× read_file（122）** | **binding（强）** |
| B/scheduler (`c3a912ed`) | 121 | 未收敛，120 步仍在查 openai-assistants 路由 | 0（即刻合规） | **binding** |
| C/scheduler (`8e78df51`) | 未触发（76 提交） | 已（危机性）收敛并提交 | 0 | non-binding |
| A/B/C-convergent | **均未触发**（110/100/102 提交 ≪ 121） | 已发生 `guidance_consistent` convergence 并停止探索 | 0 | **non-binding ×3** |

**binding rate：scheduler_only_v2 = 2/3；convergent_v2 = 0/3。** 机械规则（binding_strong/binding_candidate/non_binding）与 trace review 在全部 6 个 Factor-B run 上一致。

## 13. Prohibited-tool-attempt analysis

全场 12 runs 共 **2 次** prohibited attempt，均在 `A/scheduler` step 122：模型原话 "I need to read the actual files to get valid evidence refs. Let me read the specific files." → 2 次 `read_file` 调用被 hard gate 在参数解析前拒绝，返回确定性 rejection。**这正是旧世代 `40bd3d2e` step 126 成功绕过的路径**——当时模型补读文件修复 evidence ref 后提交；现在被拦后模型在 123 步改为"map my findings to the evidence refs I actually have"（放弃 shell-only 证据的 finding、缩短 anchor），124 提交成功。行为证据完整记录于 `prohibited_tool_attempt` 事件（含 arguments hash），且拒绝后同一 agent 继续 submit 成功（测试场景的 live 复现）。

## 14. Output ceiling diagnostics（@4096）

1289 成功 calls 中 5 次 finish=length（0.39%），**全部在 exploration role**：C/scheduler 66/68/70/72（重复 rambling 循环，文本逐字重复、模型两次自我道歉 "I apologize for the repetitive output"）+ C/none 1 次。**submission role 0/15 命中**——旧 2048 世代每 run 2–3 次的提交 payload 截断在 4096 下消失；submission-role p99 区间 930–3763（A/scheduler 3763 最接近上限但未截断）。exploration p99 除循环 run（4096）外 ≤419。结论：4096 消除了提交截断这一混杂；探索输出的 ceiling 命中只出现在病态循环中（且该循环本身被 ceiling+nudge+gate 生态兜底）。无需再做专门 ceiling A/B。

## 15. Finding quality / TP results

11 次提交共 21 findings，公开评分 TP = **1**（B/scheduler：unauthenticated file-download 缺 `isUnsafeFilePath` guard，path_traversal/medium/conf 0.45），FN 239/240，20 unmatched 待 condition-blind 人工复核。TP 在 4 格间的分布（0/0/1/0）不构成任何质量归因；forced 提交（A/scheduler 0 TP、3 unmatched）与 pre-finalization accepted submission 的质量差异仍待复核——A/scheduler 被 gate 拦截后被迫放弃的正是 shell-only 证据的 finding，与旧世代观察一致（evidence-ref 规则 × shell-heavy 风格交互）。

## 16. H1–H6 assessment

- **H1（guidance 提高主动收敛发生率/更早）— partially supported（口径收窄）**：guidance 6/6 出现较早且可复核的 `guidance_consistent` convergence（65–116 步），但无 guidance 并非 0/6 convergence：C/none 是 step 120 的 `spontaneous`，C/scheduler 是 step 73 的 `nudge_induced`，其余 4 条 `not_observed`。更稳健的结论是 guidance 使 convergence 更一致、更早，并更常连接到 stopping/submission；不证明它创造了原本不存在的 cognitive capability。
- **H2（hard finalization 提高 submission completion 但≠convergence）— supported**：scheduler_only_v2 中 2 个 `not_observed` run 被 gate 转化为提交（121/124），且 A 的 trace 显示窗口内模型仍无收敛表达、被拦后仍想读文件；反向，C/none cognitive convergence（120）却未完成 stopping/submission——completion 与 convergence 可分离，gate 只补 submission 侧。
- **H3（scheduler_only 的 binding rate 高于 convergent）— supported**：2/3 vs 0/3；convergent 中 finalization 根本没有触发过。
- **H4（convergent 中 scheduler 主要 fail-safe）— supported**：3/3 non-binding；三条均为 `guidance_consistent` convergence，且在 100–110 步完成 accepted submission，gate 纯兜底。
- **H5（组合主要缩短 convergence→successful submission 距离）— not supported**：convergent gap 3/3/3 vs guidance_only 2/3/1——无缩短；guidance 单独已把 gap 压到 1–3 步，scheduler 无增量贡献（未触发）。
- **H6（none@128 仍持续探索而非主动完成）— partially supported（明确三层）**：A/B 严格成立（`not_observed`、零提交、128 步扩张假设面）；C/none 是 `spontaneous` cognitive convergence，但 behavioral stopping=no，126 尝试提交被 validator 拒、127–128 补救超预算。none 的失败模式不完全是"缺 completion intention"，还有"迟收敛 + 未停止 + 提交执行摩擦"。

Q1–Q6 对应回答：Q1 应改为“guidance 提高一致性与提前量”，不能写成从 0 创造 convergence；Q2 方向成立（guidance 后继续探索 ≤3 次 vs C/none 9 次，n 小）；Q3 scheduler 不是"降低提交步数"而是**截停-转化**（在 121 把未收敛探索转成 1–4 步内的提交）；Q4 是（2/3 vs 0/3）；Q5 convergent 3/3 non-binding（纯 fail-safe）；Q6 不存在该形态的交互——本世代观察到的是**分工/替代**：guidance 负责较早 convergence、stopping 与提交，scheduler 在无 guidance 时兜底 submission completion，组合无额外 gap 缩短。

## 17. Threats to validity

1. 每格 n=3；seed 不发 API、provider 随机 tool_call ID → matched seed 仅为 bookkeeping，轨迹仍是独立抽样（本批未再现旧世代"同 seed 结局相反"，但样本不足以排除）。
2. C/none 单次已恢复 provider failure（warning 保留）。
3. 8 个 off-contract 64-permit 执行（含 1 个半程）为操作失误，已全量排除并披露；不影响 12 个正式 run 的合同一致性。
4. C/scheduler 的 convergence/提交由 ceiling 截断 + harness nudge 诱发（与旧世代 scheduler run 同型污染），该 cell 不能解释为 spontaneous completion。
5. 机械 binding 规则与 trace review 本批一致，但规则以收敛**候选**为输入，漏检型收敛（B/guidance 型）在无 trace review 时会误分类。
6. 公开评分稀疏且不披露逐 finding 映射；TP 不作机制结论依据。
7. 单 case、单模型、thinking disabled、temperature 0。

## 18. none@192 是否 justified

**部分 justified，优先级中低。** 预注册判据（多数 none run 持续探索+无收敛+无提交）：3 条中 2 条（A/B）严格满足；C/none 是"迟收敛+validator 拒绝+evidence-ref 补救超时"型，恰是 @192 最能回答的亚型——多 64 permits 它大概率完成提交。但若目标是区分"policy 问题 vs 预算问题"，C 型显示瓶颈更多在提交执行摩擦（evidence-ref 规则 × shell-heavy 风格）而非纯预算。建议：若跑，仅 `none @192` 单 cell、fresh seed、预注册主指标为"是否完成提交"；160 不跑。本轮未执行。

## 19. Recommended frozen completion policy for later S/P/B/T/M

**推荐冻结 `convergent_v2`（guidance + hard dispatch-level finalization）@4096。** 依据：3/3 `guidance_consistent` convergence，均在 100–110 步完成 accepted submission，gate 0 触发（零强制成本），并保留对病态轨迹（C/scheduler 型循环、none 型不收敛）的硬兜底；即"guidance 稳定 completion behavior、hard gate 兜底"的架构。scheduler_only_v2 不推荐作默认：无 guidance 时 2/3 binding 强制转化，提交质量（0/1 TP、放弃 shell-only finding）未证明。`convergent_v1`/2048 世代保留为历史诊断，不再使用。公共 runtime contract 已另行冻结于 `docs/research/common_runtime_contract_completion_v2.md`。

## 20. Recommended next experiment

1. **零成本**：对 21 条 submitted findings（20 unmatched）做 condition-blind 人工复核，重点核 A/scheduler 被 gate 拦截后放弃/降级的 finding 是否本可成立（对比旧世代绕过路径的提交质量）。
2. 若继续 completion 线：none@192 单 cell capacity probe（§18 条件）；或把 harness no-tool-call nudge 改为 policy-中性以消除 C/scheduler 型污染（instrumentation 变更，需单独批准）。
3. 回到主线：以 convergent_v2 为冻结 completion policy，推进 S/P/B/T/M formal matched block（M4 需先完成 contract.py schema evolution，见既有计划）。

## Artifacts 与复核边界

12 个正式 run + 7+1 个 off-contract run 的 manifest/summary/metrics/evaluation/events/transcripts 均在 `experiments/emergent_coordination/runs/`。本文未读取 evaluator private / ground truth / provenance；机制结论全部来自事件与 transcript 的可复核证据。
