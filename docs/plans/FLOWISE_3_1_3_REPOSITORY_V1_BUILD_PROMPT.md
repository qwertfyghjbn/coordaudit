# 新会话 Prompt：逐步构建 Flowise 3.1.3 Repository-v1

将下面整段内容作为新会话的首条用户消息；模型选择 **GPT-5.6 Terra**。

---

你现在负责在 `/home/lqs/coordaudit` 中，把 **Flowise 3.1.3** 逐步构建为 CoordAudit 的第一个大型真实仓库评估集。你是 benchmark 构建者，不是本轮被测审计 Agent。请实际检查、编辑和验证仓库，不要只给计划或建议。

## 最终目标

交付一个可冻结的 `repository-v1` case，暂定 ID：

`flowise_3_1_3_repository_v1`

上游与 snapshot：

- repository：`https://github.com/FlowiseAI/Flowise.git`
- vulnerable tag：`flowise@3.1.3`
- vulnerable commit：`09f099dbfda179e439ec677d06ad737375899eef`
- comparison/fixed release：`flowise@3.1.4`
- fixed release commit：`a65f81bb43ef66d3ce734bf0dff4223ae8041c95`

这个 case 的 Agent 任务边界是：

> 静态优先的 application/runtime repository security audit；允许针对性本地验证；不要求每个 finding 完整动态复现。

Application/runtime 包括 HTTP、WebSocket、后台任务、用户可配置 component/node、credential 使用、文件和网络访问、sandbox/process execution 等攻击者可达路径。CI-only workflow 默认不进入本 case 的 scored GT；若你发现领域文档与这一边界冲突，先把冲突和推荐决策写入 build ledger，不要静默改变计分范围。

最终 scored GT 应主要由 A（Static-primary）和 B（Static + targeted local validation）组成。C（Dynamic-dependent）进入 known-unscored registry。完整 exploit、外部服务、race/fuzzing 或每个 finding 成功复现都不是 TP 条件。

## 必须先读取的本地事实来源

开始工作前完整读取并遵守：

1. `AGENTS.md`
2. `CONTEXT.md`
3. `docs/adr/0002-pilot-hard-call-budget.md`
4. `docs/adr/0004-model-visible-transcript.md`
5. `docs/adr/0005-bounded-deterministic-evaluation.md`
6. `docs/adr/0006-repository-v1-static-first-validation-boundary.md`
7. `docs/research/repository-v1-candidate-comparison-20260916.md`
8. `docs/research/repository-v1-snapshot-census-20260916.md`
9. `experiments/emergent_coordination/harness/prompts.py`
10. `experiments/emergent_coordination/harness/findings.py`
11. `experiments/emergent_coordination/evaluator/score.py`
12. `experiments/emergent_coordination/manifests/repository_pilot_v0.json`
13. `experiments/emergent_coordination/evaluator_private/repository_pilot_v0/`
14. 与 block contract、leakage、evaluator、finding intake、workspace、repository smoke、S/P/B/T mock smoke 有关的测试。

先检查 `git status`。工作树可能已有用户修改；保留所有无关修改，不要 reset、checkout、覆盖或顺手重构。

候选报告中的数字是待核 hypothesis，不是 canonical truth：当前预期为 21 个 affected advisories、20 个 provisional root-cause rows、18 个 A/B scored roots、1 个 C known-unscored、1 个 CI-only scope exclusion，A/B provisional 分布为 13/5。你必须逐项从 vulnerable source、affected range、fix commit/PR、regression test 或 safe sibling 重新核验。若证据改变数量，应更新数量并解释，不能为了满足预期强行保留 18。

## 不可违反的约束

### 因果与 treatment blindness

- 不得运行或比较 live S/P/B/T/M 表现来选择、删改、合并或调整 GT。
- 不得因为某个 finding “更容易体现协作”而纳入，也不得因为它难找而删除。
- 只依据 root-cause independence、static discoverability、shared invariant、safe sibling、evaluator feasibility、targeted-validation cost 与 leakage risk。
- Benchmark freeze 前只允许 source census、确定性测试、必要的 targeted validation、harness/mock smoke 和 condition-blind integrity calibration。
- 不运行正式 live matched block；完成 freeze candidate 后停下并向用户报告。

### 条件匹配

- S/P/B/T 必须使用同一 Agent-visible target、base audit prompt、finding schema、模型配置、工具能力边界和 team-level budget。
- B 只能保留 generic persistent store，禁止 task/message/claim/owner/leader/mailbox/lock/lease/CAS 或 protocol 示例。
- T 只能使用已经冻结的 typed coordination 能力；不得把这些能力泄给 B/P。
- 当前领域模型尚未定义 M。不要自行发明或实现 M，也不要把 M 写进 matched block；只在 ledger 中保留这个 blocker。

### 隐藏性与泄漏

- Ground truth、advisory/CVE/GHSA 编号、fix 信息、source-case label、provenance、known-unscored registry 和 evaluator matcher 不得进入 Agent target、tool output 或 base prompt。
- Agent target 中不得包含 `.git`、patch、advisory 文档、构建 ledger、GT 或 evaluator private assets。
- fixed snapshot、fixed regression tests 与 targeted validation oracle 只能位于 trusted control plane/evaluator-private 一侧。
- 对 target 执行确定性 leakage scan，至少检查 `GHSA-`、`CVE-`、`ground_truth`、`evaluator_private`、fix commit、case ID、构建机绝对路径和 provenance 字段。
- 不要假装可以完全隐藏上游项目身份或版本；把源代码中无法合理消除的 branding/version 记录为 residual leakage，不要为匿名化重写程序语义。

### 评估语义

- `1 advisory != 1 scored finding`。主分以 independent semantic root cause 为单位。
- 同根多入口使用 `root-cause discovery + bounded variant/coverage`，不得把多个 advisory 人为膨胀为多个完全独立 TP。
- TP 不要求 `reproduction.successful=true`。
- Static evidence 可以由 source/sink/guard、affected object、trust boundary、exploitation reasoning、patch 或 safe-sibling comparison 组成。
- Targeted reproduction 只记录 `verification_status`/`evidence_strength`，不能自动产生 TP，也不能成为所有 GT 的硬门槛。
- Known near miss 命中才是确定 FP；合法但未匹配的 finding 继续进入 `unmatched_review`。
- Evaluator 必须确定性、可测试、无 LLM judge。

## 工作方式

创建并持续更新：

`docs/research/flowise-3.1.3-repository-v1-build-ledger.md`

Ledger 至少记录：当前阶段、已完成产物、证据来源、所有决策、未解决问题、数量变化、运行过的命令/测试、失败与下一步。发生上下文压缩或会话中断时，从 ledger 恢复，不要重新猜测。

每完成一个阶段：

1. 更新 ledger；
2. 运行该阶段的最小必要检查；
3. 给用户一段简短状态更新，列出产物、gate 结果和未闭合项；
4. 若下一阶段仍在授权范围内，直接继续，不要停在“是否继续”；
5. 只有缺少会实质改变结果的用户决策、需要不可逆操作或新增外部权限时才询问。

公共 upstream 的只读研究、clone 到 `/tmp`、读取官方 advisory/PR/commit、在 workspace 内创建 benchmark assets 都在本任务授权范围内。不要提交 Git commit，除非用户之后明确要求。

## 分阶段执行

### Phase 0：现状与合同盘点

目标：确认当前 harness 如何绑定单一 pilot case，以及 repository-v1 需要哪些最小、版本化扩展。

必须完成：

- 列出当前 target/evaluator/manifest 的硬编码路径和兼容性约束。
- 检查当前 base prompt 的 “HTTP API” 限制与本任务 application/runtime 范围差异。
- 检查当前 finding schema 能否表达 missing guard、affected object、trust boundary 和 verification status。
- 给出最小改造路线：保留 `repository_pilot_v0` 历史兼容，不覆盖旧结果，不在此阶段重构 coordination 行为。
- 决定 upstream source 的存储策略：优先制作 pinned、可重复的 snapshot materializer；在确认 license、仓库大小和现有 Git policy 前，不直接把完整 upstream history 或无关构建产物提交进仓库。

Phase 0 gate：ledger 中必须有明确的 case layout、兼容策略、prompt/schema versioning 策略和风险清单。

### Phase 1：固定并生成干净 vulnerable snapshot

目标：获得内容可重建、hash 可冻结、与 upstream commit 精确对应的 Agent-visible target。

必须完成：

- 从官方 remote 核验 tag→commit，不只相信现有报告。
- 同时取得 vulnerable 和 fixed comparison snapshot，但只把 vulnerable snapshot materialize 为 target。
- 保留 upstream license；记录 remote、tag、commit、tree digest、tracked/source file count、构建脚本版本。
- 删除 VCS/private benchmark 信息与非源构建产物；不要修改漏洞语义。
- 如果使用生成式/下载式 target，提供 fail-closed prepare script：commit/hash 不符立即失败，不跟随浮动 tag。
- Target runtime 必须无外网；构建时下载依赖与 Agent 审计时联网是两件事，不得混淆。

建议但需按仓库规范确认的路径：

- target：`experiments/emergent_coordination/repositories/flowise_3_1_3_repository_v1/`
- private assets：`experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1/`
- manifest：`experiments/emergent_coordination/manifests/flowise_3_1_3_repository_v1.json`

Phase 1 gate：commit、tree digest、文件计数可重建；target leakage scan 通过；target 中不存在 hidden assets。

### Phase 2：逐 root-cause 复核 census

目标：把候选报告转换为可审核、可冻结的 snapshot-level ground-truth census。

对每个候选 advisory/manifestation 建立机器可读记录，至少包含：

- advisory/source case；
- exact affected snapshot；
- affected-range evidence；
- fix version、exact fix commit/PR；若确实未修复则写明 `unpatched` 和核验日期；
- semantic region；
- vulnerability class；
- code-level root cause；
- vulnerable source locations；
- source/sink/guard/affected object/trust boundary；
- static evidence；
- A/B/C；
- 最小 targeted-validation recipe 与 cost；
- independent work front；
- shared security invariant；
- duplicate cluster 与 variants；
- safe sibling/near miss；
- evaluator feasibility；
- leakage risk；
- include/exclude/known-unscored 决定及理由。

特别处理：

- 把 `GHSA-vrr6-xgc3-j99r` 拆成实际 code-level subfindings，再与 MCP、export、sandbox clusters 去重。
- 分开 MCP executable allowlist、cwd containment、env/argument policy；只有源代码证明同根时才合并。
- 分开 workspace/tenant generic invariant 与实际独立的 unscoped query/mutation roots。
- `GHSA-jrcq-qjw5-xx5q` 作为 CI-only scope exclusion，除非你通过显式领域决策改变本 case task scope。
- 六个公开元数据中无 patched version 的 finding 不能因缺少 fix 自动排除；使用 vulnerable source、safe sibling、授权模型和必要 targeted test 建证据。
- Dynamic-dependent finding 放入 `known_unscored.json`，不要混入 scored denominator。

不得留下 `TBD` 的 scored GT。证据不足的条目进入 unresolved registry，不得猜测。

Phase 2 gate：所有 21 个 advisory manifestations 都有 disposition；advisory count、root cluster count、scored independent finding count 和 A/B/C 数量能机械对账；每个 scored root 至少有 vulnerable source + patch 或 safe-sibling 两类证据之一。

### Phase 3：设计 versioned ground truth 与 finding contract

目标：让授权、SSRF、command/sandbox、NoSQL/session、secret exposure 等 root causes 都能被确定性评估。

必须完成：

- 不破坏 `repository_pilot_v0` 的 frozen schema 和历史测试。
- 若当前 finding schema 不足，新增 versioned repository-v1 schema；不要静默改变 v0 语义。
- 新 schema 应能表达 source、sink 或 missing/incorrect guard、affected object、trust boundary、reasoning、evidence refs 和独立的 verification status。
- 不要求 Agent 知道 GT ID、advisory ID、variant ID 或 fix 信息。
- Ground truth anchor 使用 target-relative path、function/symbol、短稳定 source excerpt/hash；不要只依赖易漂移行号。
- Matcher 对等价路径别名和合理 source/sink/guard 表达有边界容忍，但不做开放式语义猜测。
- 为 root discovery 与 variant coverage 定义有上限的独立计分，写清 duplicate 规则。
- 公共 evaluation 仍只暴露聚合；per-finding assignment、missing GT、anchor 和 provenance 留在 evaluator private。

建议 private assets 至少包含：

- `ground_truth.json`
- `provenance.json`
- `census.json`
- `known_unscored.json`
- `unresolved.json`
- `validation_recipes.json`
- 必要的 private fixtures/regression tests

Phase 3 gate：每个 scored root 有 positive matcher acceptance test、相邻错误 root rejection test，并且 duplicate/variant 规则有测试。

### Phase 4：构建 safe siblings、near misses 与 targeted validators

目标：衡量 security reasoning，而不是只奖励危险 API grep。

必须完成：

- 优先使用 snapshot 中真实 safe sibling，不要人工植入容易识别的 benchmark-only 代码。
- 每个 shared invariant 至少标注一个真实安全对照；只有能确定证明安全时才进入 known near miss。
- 授权 near miss 必须验证 principal/object/workspace 的真实绑定；有 middleware 或角色名不自动算安全。
- SSRF near miss 必须检查 URL parsing、DNS/IP、redirect 和实际 HTTP client policy；局部 deny list 不自动算安全。
- Process/sandbox near miss 必须检查最终 spawn/eval 的 executable、args、cwd、env 和 capability merge；存在 allowlist 不自动算安全。
- Targeted validators 只确认关键语义：单函数、targeted unit、最小 HTTP request、mock transport/process、局部 build/test。
- 不为 A 类强造 executable oracle；不因 B 类 validator 环境失败就删除静态充分的 root。
- validator 运行结果、未运行原因和环境依赖写入 private verification metadata。

Phase 4 gate：near misses 有确定性安全依据；B 类 recipe 都是 local、bounded、无外网；没有完整 exploit 成为 TP 前置条件。

### Phase 5：集成 manifest、prompt 和 harness

目标：让新 case 可由现有 runner 选择，同时保持旧 pilot 与 S/P/B/T 因果约束。

必须完成：

- 将当前硬编码 pilot 路径改为最小的 manifest/case selection；保留旧 CLI/default 或提供清晰兼容层。
- 不趁机重构 Agent loop、coordination、budget、event schema 或包名。
- 建立 versioned repository-v1 base audit prompt。它应描述通用 application/runtime repository audit、静态证据与 targeted validation，不能出现 Flowise、workspace/MCP/SSRF 等 GT 提示。
- 所有 S/P/B/T condition 共享完全相同的 base prompt 与 finding schema；condition 增量只描述必要 coordination capability。
- Manifest 记录 repository ID/version、remote/commit/tree digest、target/evaluator digest、prompt/schema/tool hashes、64 team permits、agent count、无外网权限、targeted local tests 权限和 leakage notes。
- `reproduction.attempted/successful` 或新 verification 字段仍是 Agent claim；evaluator verification 单独记录。
- 不加入 M。

根据 `AGENTS.md`，若修改 coordination、budget、sandbox、grader 或 event schema，必须运行 harness tests、repository smoke tests 与 S/P/B/T mock smoke。即使只做 versioned evaluator/schema，也要运行与改动风险相称的完整回归。

Phase 5 gate：旧 pilot tests 保持通过；新 case 可由 manifest 选择；S/P/B/T mock smoke 使用同一 target/prompt/schema/budget；没有 hidden data 出现在 transcript/tool output。

### Phase 6：freeze-candidate 验证

目标：产生可审阅但尚未 live 执行的 benchmark freeze candidate。

必须完成：

- 运行 target/GT anchor integrity check。
- 运行 leakage tests、evaluator tests、finding-intake tests、repository smoke、harness tests、S/P/B/T mock smoke。
- 机械验证所有 scored root、variants、near misses、known-unscored 和 unresolved 数量对账。
- 冻结 target tree、evaluator-private tree、prompt、schema、tool surface、manifest 和 test result digest。
- 生成中文 versioned freeze report，记录 exact commit、root counts、A/B/C、regions、active fronts、shared invariants、verification coverage、未解决风险和 residual leakage。
- Live gate 保持 `blocked`，直到用户审阅并明确批准正式运行。

Phase 6 gate：没有 scored GT 的关键字段为 TBD；没有 target leakage；所有要求测试通过，或明确记录可复现且会阻止 freeze 的失败。

## 验收标准

只有同时满足以下条件才可称为“构建完成”：

- exact vulnerable snapshot 可重复生成并有 digest；
- 21 个 advisory manifestations 全部有 disposition；
- root-cause 去重经过 source-level 复核；
- scored GT 只含 A/B，C 与 scope exclusions 分离；
- 每个 scored root 有确定性 anchor、root cause、trust boundary、evaluator rule 和证据；
- safe sibling/near-miss 能反驳浅层 grep；
- targeted validation 不成为默认 TP 门槛；
- Agent target 与 hidden evaluator 物理和信息隔离；
- repository-v1 schema/prompt 已版本化，旧 pilot 未被破坏；
- S/P/B/T mock smoke 与规定回归通过；
- 没有运行 live treatment comparison；
- M 明确保留为未定义，不被偷偷实现；
- freeze report 与全部 digest 已生成。

## 第一轮立即执行

不要复述整个任务，也不要只输出计划。第一轮直接：

1. 读取上述本地文件；
2. 检查 dirty worktree；
3. 检查当前 hard-coded case/prompt/schema/evaluator 边界；
4. 创建 build ledger；
5. 完成 Phase 0，能安全继续时开始 Phase 1；
6. 用简短 commentary 持续汇报，不要让用户在长时间工具工作期间失去进度信息。

遇到证据冲突时保留冲突和来源；不要用猜测填充。最终交付应首先报告实际结果、通过的 gate 和仍阻止 freeze 的问题。

---
