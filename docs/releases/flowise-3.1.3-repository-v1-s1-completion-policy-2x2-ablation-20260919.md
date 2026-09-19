# Flowise 3.1.3 repository-v1 S1 completion-policy 2×2 消融（2026-09-19）

## 1. Executive summary

四个 matched-seed 128-permit 消融 run 全部找到、全部有效（`valid`/`valid`，provider failure 0），无需补跑。2×2 结果为：

| | 无 runtime finalization | 有 runtime finalization |
|---|---|---|
| **无 prompt guidance** | `none`：128/128 耗尽，0 finding，0 提交意图 | `scheduler_only`：step 105 自发收敛、113 提交（finalization 从未触发） |
| **有 prompt guidance** | `guidance_only`：step 109 自发收敛、116 提交，3 findings，1/20 TP | `convergent_v1`：120 步前未收敛，step 121 被 finalization 强制，127 提交，2 findings，0/20 TP |

最重要的三个发现：

1. **本轮 2×2 中 scheduler 不是 `scheduler_only` 的提交驱动力**。该 run 在 step 104 命中 2048 output ceiling 产生无工具调用的截断回复，触发基础 harness 的 no-tool-call nudge（"If you have finished, call submit_findings…"），step 105 才出现 "I have enough evidence"。提交发生在 step 113，早于 finalization 起点（step 121）8 步。
2. **`convergent_v1`（A+B 组合）是本轮最慢、最混乱的提交路径**：唯一真正进入 finalization 的 run，6 次 submit 调用（2 次 payload 截断、3 次 validator 拒绝）后才在 step 127 成功，仅剩 1 个未用 permit。同一 seed、同一 prompt、同一代码路径的旧 128-permit 诊断 run（`9f6f60b1`）却曾在 step 84–85 自发收敛、step 90 提交、拿 2/20 TP —— 同配置两次运行结果相反，说明**轨迹级随机性在 n=1 下主导结果**。
3. **matched seed 不等于 matched trajectory**：`guidance_only` 与 `convergent_v1` 在 step 121 之前 system prompt、工具面、名义条件完全相同，但两者在 step 3 就分岔——起因是 provider 生成的随机 tool_call ID 进入后续消息。且 LLM client 从不把 seed 发给 API（只传 model/temperature/messages）。因此每个格子都是一次独立随机抽样，A 与 A+B 的格间对比当前由方差而非处理效应驱动。

结论基调：本轮是 diagnostic ablation。方向性观察（none 缺失 completion intention；guidance 可独立促成收敛+提交；finalization 是兜底而非提质机制）有一致的多 run 证据，但任何"policy causes X"的定量主张都需要 replicate seeds 支持。

## 2. 实验问题

此前观察：S1 在较高 permit budget 下可能持续探索而不主动判断"证据已足够"并提交。将 `convergent_v1` 拆为两个因素：

- **Factor A（prompt guidance）**：system prompt 追加 `CONVERGENT_COMPLETION_INSTRUCTIONS`（bounded audit loop / 够用即停 / 优先 supported submission）。
- **Factor B（runtime finalization）**：最后 8 次 call（`max_steps-8` 起）把工具面限制为 `submit_findings`，并注入一条 finalization user message。

| condition | prompt guidance | runtime finalization |
|---|---:|---:|
| `none` | no | no |
| `guidance_only` | yes | no |
| `scheduler_only` | no | yes |
| `convergent_v1` | yes | yes |

## 3. Run provenance

四个主 run（均：case `flowise_3_1_3_repository_v1`；mode `single`/S1；N=1；`deepseek-flash`/`openai_compatible`；thinking disabled；temperature 0.0；max output 2048；permits 128；`max_steps` 128；`max_provider_retries` 1；`prompt_profile` `repository_v1`；finding schema `repository_v1`；git commit `5a01249`；seed `flowise-s1-128perm-diagnostic-20260919`）：

| condition | run_id | 启动时间 (UTC) |
|---|---|---|
| none | `single_n1_20260919T015554.026898+0000_f8b46033` | 01:55 |
| guidance_only | `single_n1_20260919T020929.584601+0000_5e034b57` | 02:09 |
| scheduler_only | `single_n1_20260919T021423.935064+0000_1a6244b9` | 02:14 |
| convergent_v1 | `single_n1_20260919T021948.640024+0000_40bd3d2e` | 02:19 |

辅助 run（用于方差与历史对照，不进 2×2 主表）：

| run | 角色 | 关键结果 |
|---|---|---|
| `single_n1_20260919T013923.221314+0000_14e9da39` | none，独立 seed（`flowise-s1-128perm-completion-none-20260919`） | 128/128 耗尽、0 finding、无收敛语义 |
| `single_n1_20260919T005712.105877+0000_9f6f60b1` | convergent_v1，同 seed（旧 128-permit 诊断，改代码前） | 90 calls，step 84–85 自发收敛，step 90 提交，4 findings，2/20 TP |
| `single_n1_20260919T004958.035995+0000_2c9edb89` | convergent_v1，96-permit 诊断 | step 74/78 收敛，86/88/89 提交，1/20 TP |
| `single_n1_20260919T003239.655288+0000_bcbf7ec3` | convergent_v1，64-permit 校准 | 无 pre-finalization 收敛语义，step 57（=finalization 起点）提交，0/20 TP |

`none` 主 run 的选择依据：matched seed `flowise-s1-128perm-diagnostic-20260919` 的是 `f8b46033`（上一轮 none-ablation 文档中的 matched-seed replicate）；`14e9da39` 是独立 seed 版本，仅作 replicate 证据。

## 4. Implementation verification

从当前 working tree diff、transcript 内实际 prompt 与事件核验（未重跑任何 live run）：

- **`guidance_only`**：system prompt 含 `CONVERGENT_COMPLETION_INSTRUCTIONS`；无 finalization。transcript 佐证：`guidance_only` 与 `convergent_v1` 的 system prompt 逐字节一致（sha256 前 12 位 `0a79182e3426`）。
- **`scheduler_only`**：system prompt 与 `none` 逐字节一致（`c5f44795d249`，无 completion 指令）；step 121 起工具面限制为 `submit_findings`，注入中性消息 `Finalization phase: the available tool surface is now restricted to submit_findings. Use only evidence already acquired.`（本轮确认已按要求改为中性措辞）。
- **`convergent_v1`**：两者皆有；finalization 消息更强（`Call submit_findings now …`）。与旧 128 诊断 run（`9f6f60b1`）的 system prompt 与 finalization 消息逐字节一致——即旧/新两 run 的 convergent_v1 代码路径无差异，行为差异全部来自随机性。
- **`none`**：两者皆无（manifest 中 `completion_policy: null`）。
- CLI plumbing：`run_experiment.py --completion-policy {none,convergent_v1,guidance_only,scheduler_only}`；`runner.py`/`agent_loop.py`/`events.py` 贯通，新增 `completion_phase_started` 事件。`tests/test_prompts.py::test_completion_policy_is_opt_in` 通过（3 passed）。
- 四条件除这两因素外无 capability 差异；工具面、finding schema、target snapshot、budget 语义一致。
- **事后修正（2026-09-19 补充核验）**：finalization 的工具限制只在请求的 advertised tools 层生效，dispatch 层仍按 mode 级 allowlist 放行。convergent_v1 run 的 step 126（finalization 窗口内）成功调用了未被 advertise 的 `read_file` 补 evidence ref（`evt_00000815`）——即 finalization 是"建议性"约束，模型可绕过。本轮不改该行为；解读 Factor B 时应视其为"强提示 + 可绕过的工具裁剪"，而非硬性沙箱。

两个影响解释的基础 harness 行为（四条件共有，属于既有实现而非本轮改动）：

1. **no-tool-call nudge**：模型回复既无 tool call 又抽不出 findings JSON 时，harness 注入 user message "If you have finished, call submit_findings with your JSON findings."（`agent_loop.py` L130）。
2. **evidence-ref 规则**：只有 `read_file` 产生的 `file_read` 事件 ID 是合法 evidence ref；`run_shell` 输出不产生 ref（`tools/sandbox.py`）。

## 5. 定量结果矩阵

| Metric | none | guidance_only | scheduler_only | convergent_v1 |
|---|---|---|---|---|
| run_id | `…f8b46033` | `…5e034b57` | `…1a6244b9` | `…40bd3d2e` |
| seed | matched | matched | matched | matched |
| validity / reconciliation | valid / valid | valid / valid | valid / valid | valid / valid |
| stop_reason | `model_format_failure`（= 到达上限且无可提交 payload） | `submitted` | `submitted` | `submitted` |
| total permits | 128 | 128 | 128 | 128 |
| calls consumed | 128 | 116 | 113 | 127 |
| unused permits | 0 | 12 | 15 | 1 |
| first convergence statement step | 无（0–128 全程） | 109 | 105（紧跟 harness nudge） | 自愿收敛无；提交意愿首现 121（finalization 内） |
| first submission attempt step | — | 113（payload 截断） | 106 | 121（payload 截断） |
| successful submission step | — | 116 | 113 | 127 |
| submission attempts（validator 口径 / submit 工具调用总次数） | 0 / 0 | 2 / 3 | 3 / 5 | 4 / 6 |
| invalid/rejected attempts（validator 拒绝 + JSON 截断） | 0 + 0 | 1 + 1 | 2 + 2 | 3 + 2 |
| finalization start step | N/A | N/A | 未触发（应为 121） | 121 |
| submitted finding count | 0 | 3 | 3 | 2 |
| TP | 0 | 1 | 0 | 0 |
| known near-miss FP | 0 | 0 | 0 | 0 |
| FN | 20 | 19 | 20 | 20 |
| unmatched / manual review | 0 | 2 | 3 | 2 |
| provider/infra failures | 0 | 0 | 0 | 0 |
| finish_reason=length（output ceiling 命中） | 0 | 2（step 113,114） | 2（step 104,108） | 2（step 121,122） |
| input / output tokens | 11.82M / 12.9K | 9.41M / 25.1K | 8.19M / 26.6K | 12.96M / 26.2K |

口径说明：metrics 的 `invalid_submission_attempts` 只计 schema/evidence validator 拒绝；**submit 参数 JSON 截断（`invalid_tool_arguments`）不计入任何 metrics，只能在 transcript 里看到**——上表单列。公开 evaluator 不披露逐 finding 映射；unmatched 均为 `condition_blind_manual_review_only`，未计 TP。

## 6. 逐条件 trace 分析

### A. none（`f8b46033`）

- 128 步中**零次**收敛/提交语义表达；无 no-tool-call 回复，nudge 从未触发；0 次 submit 调用。
- 探索形态：84×`run_shell` + 63×`read_file`，到最后一步仍在打开**新** route/controller 家族（step 117–128：dataset、evaluations、documentstore service、enterprise `workspace-user`/`tenantRequestGuards`/`user.controller`）；step 119 甚至宣布"换个思路，全库搜索可疑 pattern"——假设面到耗尽为止仍在扩张。
- 判定：**"没有形成 completion intention"**，不是"形成但未执行提交"。独立 seed 的 none run（`14e9da39`）同模式（上一轮文档亦确认其 step 110–119 仍在 workspace/IDOR 探索）。

### B. guidance_only（`5e034b57`）

- 收敛表达首现 step 109：`I've done a fairly thorough review. Let me now consolidate my findings.`（此前 step 66/79 只是单点 candidate 验证，非完成语义）。
- step 100–108 仍在发现新面（nvidia-nim 容器路由、documentstore loader 路径），说明 guidance 没有提前终止探索覆盖，只是把"探索→整合"的转折点固定在预算内。
- step 110–112 是整合性动作：复核 OAuth2 callback、`read_file` 补 evidence ref（`evt_00000757` 等）——read-heavy 风格（93×`read_file`）带来充足证据池，**全程零 evidence-ref 拒绝**。
- 提交路径：113 首次 submit（payload 超 2048 输出上限被截断，`finish_reason=length`）→ 114 试图写文件暂存（同样截断）→ 115 精简 payload 遭 schema 拒绝（`variant_coverage[0]` 缺 `anchor/file/function`）→ 116 修正后成功，3 findings，剩 12 permits。
- 为什么没有 scheduler 也能提交：guidance 文本给出了"够用即停、优先 supported submission"的行为脚本，Agent 在 109 步自换挡，整个提交段自主完成。

### C. scheduler_only（`1a6244b9`）

- **它是自主决定完成，还是被 runtime 剥夺工具后被迫提交？——都不是**：它是被 **harness nudge** 推入提交的。因果链（transcript 证据）：
  1. step 99–103 仍在探索（schedule service、webhook SSRF、`validateWebhookChatflow`）；
  2. step 104 回复命中 output ceiling（`finish_reason=length`），文本被截断、无 tool call（一段连发 7 个 "Let me now look at…" 的 rambling）；
  3. harness 注入 "If you have finished, call submit_findings…"；
  4. step 105 `I have enough evidence for my primary findings.` + 最后两次 targeted check；
  5. step 106 起 5 次 submit 调用（106 schema 拒绝 → 107 截断 → 109 evidence 拒绝 → 110–111 `read_file` 补 ref → 112 截断 → 113 成功）。
- finalization（step 121 起）从未触发——**本 run 对"Factor B 单独效果"没有提供任何直接证据**。
- 2 次 validator 拒绝的成因：1 次 schema（`variant_coverage` + 不允许的 `note` 字段）、1 次 evidence lineage（`findings[2]` 引用的 documentstore 文件只用 shell 看过，必须 `read_file` 过才算数）。根因是 shell-heavy 风格（98 shell / 27 read）导致证据池薄。
- **0/20 TP 不能直接归因于 scheduler 降低质量**：guidance 臂也只有 1/20，公开评分稀疏；其 3 条 finding 均进 unmatched 人工复核，质量判断 pending。

### D. convergent_v1（`40bd3d2e`，matched seed 新 run）

- 与 `guidance_only` 同 system prompt，但轨迹在 step 3 就分岔（随机 tool_call ID 进入后续消息），此后各自演化——这是"同条件两次抽样"的直接展示。
- step 95–114 系统性扫 controller/route（dataset→marketplaces→evaluators→pricing→stats→oauth2→node-icons→templates），覆盖扩张、无整合意图；step 112–120 转入对既有候选（get-upload-file、webhook SSRF、TTS `getCredentialData`）的验证，但**始终没有跨过"停止验证、开始提交"的门槛**，step 120 还在验证新组件时 finalization 到点。
- step 121 finalization 触发（`completion_phase_started` 事件，唯一出现的一次）：工具只剩 `submit_findings`。随后：121 截断 → 122 截断 → 123 schema 拒绝（payload 被包进多余 `arguments` 键）→ 124 evidence 拒绝（`findings[1]` 引用未 `read_file` 的文件）→ 125 同样拒绝 → 126 `read_file` 补 ref（`evt_00000815`）→ 127 成功，2 findings，剩 1 permit。
- 8 步 finalization 预算被 payload 截断烧掉 2 步、validator 拒绝烧掉 3 步；最终提交的 2 条（feedback routes、get-upload-file）不含它此前重点验证的 TTS 候选——**候选在 evidence-ref 与截断的拉锯中被丢弃**。
- 与同 seed 旧 run（`9f6f60b1`：84/85 收敛、90 提交、4 findings、2 TP）对照：prompt/代码路径一致而结局相反，scheduler 在新 run 是 binding constraint、在旧 run 从未触发。

## 7. Cognitive convergence vs behavioral stopping vs submission completion

| condition | 认知收敛（判断证据已足够） | 行为停止（停止 read/search/shell 扩张） | 提交完成 |
|---|---|---|---|
| none | ✗（128 步内从未表达） | ✗（至 128 仍开新攻击面） | ✗ |
| guidance_only | ✓ step 109 | ✓ step 109–112 仅整合性读取 | ✓ step 116（经 1 截断 + 1 schema 拒绝） |
| scheduler_only | ✓ step 105，但由 ceiling 截断+nudge 诱发 | ✓ step 105–106 | ✓ step 113（经 2 validator + 2 截断） |
| convergent_v1 | ✗ 自愿收敛；提交意愿仅在 121 被 finalization 注入后才出现 | ✗（被 runtime 在 121 强制截停） | ✓ step 127（经 3 validator + 2 截断） |

本轮出现的分离形态：none = "无收敛意图且不停"；conv 新 run = "runtime 被迫停止探索，但认知上未收敛"；guidance/scheduler = "收敛→停止→提交"三段完整，但 scheduler 的收敛由 harness 文本 nudge 诱发，非纯自发起。

## 8. Finding-quality 对比

| run | 提交 findings（severity） | TP | unmatched |
|---|---|---:|---:|
| guidance_only | TTS 任意 credential 使用（high）；NVIDIA NIM 容器路由缺鉴权（high）；OAuth2 callback 无 workspace 绑定（medium） | 1 | 2 |
| scheduler_only | TTS credential 使用（high）；get-upload-file IDOR（medium）；documentstore 缺 RBAC（low） | 0 | 3 |
| convergent_v1 | feedback routes 未认证读写（high）；get-upload-file 未认证下载（high） | 0 | 2 |

- 跨 run 重叠：TTS 候选出现在 guidance+scheduler；get-upload-file 出现在 scheduler+conv。
- 1/20 vs 0/20 在公开评分下不可归因（差 1 个 TP）；全部 unmatched 待 condition-blind 人工复核，本报告不把 manual-review findings 算 TP。
- 质量相关的机制性发现：evidence-ref 只认 `read_file`，探索风格（read-heavy vs shell-heavy）直接决定可提交集合；conv 的 TTS 候选、scheduler 的 documentstore finding 都因此额外消耗提交窗口步骤，甚至丢失候选。这是 harness 政策×探索风格的交互，不是 completion policy 本身的效应，但会污染"finalization 降低质量"的解读。

## 9. Hypotheses 评估

### H1：prompt guidance 单独能显著提高主动收敛并提交的概率 — **partially supported**

正证据：guidance 臂 4 条 trace 中 3 条自主收敛+提交（guidance 109→116；旧 128 conv 84/85→90；96-run 74/78→86–89），且无需 scheduler；none 臂 2 条 trace 0 次收敛。guidance run 提交后仍余 12 permits，说明是"提前主动收敛"而非"拖到没预算"。反证：conv 新 run 同 prompt 却 120 步不收敛。n=1/格 + 评分稀疏，无法给"显著"定量背书。

### H2：runtime finalization 单独能保证/促进 submission，但不保证质量 — **partially supported（本 2×2 内未被直接检验）**

本 2×2 的 scheduler_only run finalization 根本没触发（113 < 121），因此 Factor B 单独效果在本矩阵中**零直接证据**。"保证 submission attempt"的间接证据来自 convergent_v1 家族内 finalization 实际触发的 run：64-run 在零收敛语义下于 finalization 首步（57）提交；conv 新 run 在 121–127 内被兜底成交付。"不保证质量"方向一致（两次 forced 提交均 0/20、validator 拒绝率高），但 0/20 也出现在自主提交的 scheduler_only，且 1/20 vs 0/20 在噪声范围内——质量主张 unsupported，待复核与 replicate。

### H3：convergent_v1 主要效果来自 guidance，scheduler 是 fail-safe — **partially supported**

2×2 内：guidance 单独即可完成（guidance 臂）；conv 臂反而是靠 scheduler 兜底的（121 强制）。历史 4 条 conv-policy run：2 条自发收敛（旧 128、96）、2 条被 finalization 兜底（64、新 128）。图像与"guidance 主驱动、scheduler 兜底"一致；但"主要效果"的定量分解在 n=1/格 下不可能——conv 新 run 证明 guidance 效应本身不稳定。

### H4：guidance×scheduler 存在明显正交互，只有组合才有稳定早停 — **not supported**

本轮组合是最慢、最坎坷的提交路径（127/128、1 剩余、6 次 submit、3 validator 拒绝）；guidance 单独反而干净利落（116、12 剩余）。观察到的更像替代/冗余而非协同；没有任何 trace 显示"只有组合才早停"。

### H5：none 在 128 不提交是 capacity 问题而非 completion-policy 问题 — **not supported（就已观测区间）**

两条 none trace（matched + independent seed）都 128/128 耗尽、零收敛语义、最后 10 步仍在新开 route 家族。若是容量瓶颈，应看到尾部出现收敛苗头（整合、复述候选、收敛语言）——完全没有。缺失的是 completion intention；同预算下任何注入完成机制的条件都产出了提交。 caveat：不能排除"极大预算下探索饱和→自发收敛"的存在，但 128 步内的轨迹没有任何朝该方向的趋势。

## 10. Threats to validity

1. **轨迹级随机性主导**：seed 只记录在 manifest、从不发给 API；provider 随机 tool_call ID 进入后续请求 → 同 prompt 同 seed 的 guidance 与 conv 在 step 3 分岔；新旧 conv run 同 seed 同代码路径结局相反（90 vs 127 calls）。每个格子是 n=1 随机抽样。
2. **guidance_only 与 convergent_v1 在 step 121 前是同一条件**：2×2 的 A vs A+B 格间对比在该窗口内由方差驱动；正式说法只能是"两个同条件抽样 + finalization 介入"。
3. **Factor B 并非纯 runtime**：finalization 消息本身点名 `submit_findings`（即便中性措辞），是文本提交线索；且本轮 scheduler_only 的实际触发者是基础 harness 的 no-tool-call nudge（由 output ceiling 截断诱发）——"runtime-only"臂受到双重文本污染，方向都是促提交。none/guidance/conv 每步都带 tool call，nudge 从未触发，故该污染只在本 run 内偏置 scheduler 臂。另：finalization 工具裁剪可被绕过（conv run step 126 在窗口内成功调用 `read_file`），Factor B 的强制力弱于设计意图。
4. **2048 output ceiling × 大 payload**：5 次 JSON 截断分布于三个 run，消耗提交窗口步骤；submit 成败部分取决于 payload 尺寸管理，与 policy 无关但与之交互（conv 的 8 步 finalization 被 fire 掉 2 步）。
5. **evidence-ref 只认 read_file**：探索风格差异（shell-heavy 的 scheduler/conv vs read-heavy 的 guidance）直接决定证据池与可提交集合，形成与 completion policy 无关的质量混杂。
6. **公开评分稀疏且不披露逐 finding 映射**；1/20 vs 0/20 不可归因；unmatched 未复核前不能当 FP。
7. 单 case、单模型、thinking disabled；temperature 0 未带来可复现性。

## 11. 是否需要更多 seeds

**需要，这是当前最大的信息缺口。** 理由：H1–H4 的任何定量结论都压在 n=1/格 上，且本轮已直接观测到同条件两次抽样结局相反（guidance vs conv 前 121 步；新旧 conv）。若继续，建议每格 2–3 个**不同 seed**（fresh seed 而非复用 matched seed——后者已证明不控制任何东西），主指标用"首次收敛表达步数/是否自主提交/提交尝试无效率"，TP 只作次级参考。本轮不要执行。

## 12. none@160 / none@192 capacity extension 是否仍有信息价值

**当前证据下信息价值低，优先级低于 replicate seeds。** 两条 none trace 到 128 步都在扩张假设面、零收敛语义——失败模式是缺失 completion intention，不是探索容量不足。160/192 唯一能回答的预注册问题是"更大预算下是否出现饱和诱发的自发收敛"；鉴于 Flowise server 端 route/controller 面积（none 到 128 步仍在进入 enterprise/documentstore 等未扫区域），先验预期是继续探索。若之后仍要跑，建议作为 replicate 轮的附带项（例如 none 新 seed @128 与 @192 各一条）而不是独立主实验。本轮不执行。

## 13. 建议的下一步实验（待批准，均未执行）

1. **先零成本**：对本轮 8 条 submitted findings（含 7 条 unmatched）做 condition-blind 人工复核，重点核 TTS/get-upload-file 两条跨 run 重复候选的 evidence lineage；这决定"0/20 是质量问题还是评分映射问题"。
2. **主实验**：2×2 replicate 轮——每格 ≥2 个 fresh seed，128 permits，其余配置与本轮完全一致；预注册主指标（自主提交率、首次收敛步、validator 拒绝率、截断次数），TP 为次级。
3. **instrumentation 小改（非 policy 改动）**：把 submit 参数 JSON 截断计入 metrics（当前 `invalid_submissions` 漏掉它们），并记录每次 attempt 的 payload 长度与 `finish_reason`，使"finalization 窗口被截断消耗"可量化。**已实施（2026-09-19，经批准）**：`agent_loop.py` 新增 per-agent `invalid_submission_arguments` 计数（submit_findings 参数无法解析为 JSON object 时递增，含 output-ceiling 截断与其他 malformation；截断归因仍靠 `llm_call` 的 `finish_reason`），`summary.json` 的 `agent_results` 透出该字段；不进入 evaluator/scoring。配套测试 `test_unparseable_submit_arguments_are_counted`；全套 107 tests 通过，S/P/B/T mock smoke 通过。按本计数回溯本轮四 run 应为 none 0 / guidance 1 / scheduler 2 / conv 2。
4. 不修改 frozen formal block、不改 scoring、不改 target、不改 completion policy 实现。

## 14. Artifacts 与复核边界

四个主 run 的 `run_manifest.json`、`summary.json`、`metrics.json`、`evaluation.json`、`logs/events.jsonl`、`logs/transcripts/agent_001.jsonl` 全部保留于 `experiments/emergent_coordination/runs/<run_id>/`，本报告不替代原始 evidence。本文不读取、不披露 evaluator private、ground truth 与 provenance。本文写作期间未重跑任何 live run、未修改任何 harness 代码与既有 artifacts。
