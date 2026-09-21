# Flowise repository-v1 GT / evaluator 覆盖审计（2026-09-21）

> 后续 gate 裁决见 [repository-v1.1 GT freeze gates](../releases/flowise-3.1.3-repository-v1.1-gt-freeze-gates-20260921.md)。本文件记录审计当时的 29-root 提案与未决项；当前 versioned GT 候选为 30 roots，UC41 的独立 flow-execution 链已裁为 positive，TM4/TM6/CR1 已由 ADR-0007 定稿。

> 状态：审计完成。本文件是 `repository-v1` case 的 ground-truth / evaluator 覆盖审计主文档；配套升级提案见 [repository-v1.1 升级提案](flowise-3.1.3-repository-v1.1-upgrade-proposal-20260921.md) 与 [evaluator-v2 设计](flowise-evaluator-v2-design-20260921.md)。所有机器可读 ledger 在 `artifacts/gt_audit/`。
>
> 本审计不修改任何冻结资产：`repository-v1` manifest、evaluator-v1、旧 run 得分全部保持 immutable。

## 0. 审计范围与方法

- 冻结基准：`flowise_3_1_3_repository_v1`，snapshot `flowise@3.1.3` @ `09f099db`（tree `c612819a`），evaluator `repository_v1_score.py`，GT `phase3-draft-1`（20 roots + 5 near-misses），census/advisory inventory as_of 2026-09-16。
- 三路证据源：
  1. **仓库内资产**：manifest、GT/census/advisory inventory/known_unscored/unresolved/validation recipes、63 个 flowise repository-v1 runs 的 `merged_findings.json` + `evaluator_private/verification.json`（含 S/P/B/T/M 全条件）。
  2. **上游 git history**：blobless clone，snapshot→HEAD（`09f099db..9291856d`，2026-06-25 至 2026-08-13，28 commits）全量 diff 分诊 + snapshot 前 36 条 security fix 简表。
  3. **公开情报**：GitHub 官方 security advisories 全量 130 条（含版本范围）、OSV npm 镜像交叉验证、CVE 编号映射，以及已完成的第三方 write-up 有限三角验证（非系统性全网清扫）。GitHub Discussions 不在本轮冻结收集协议内，见 §7。
- 裁决方法：对全部 40 个去重 unmatched cluster 做 condition-blind 独立静态复核（4 个批次；裁决者读 snapshot 代码而非 run transcript），跨批冲突由主裁决人裁定并记录。

## 1. Evaluator-v1 审计（十个问题）

TP 判定链（`evaluator/repository_v1_score.py:49-61`）：`category ∈ spec.categories` 且 source/sink/guard.anchor/variant_coverage 中**任一 anchor** 与 canonical anchor 精确匹配（file 相等 + function 规范化相等 + excerpt 子串）且 `guard.kind ∈ spec.guard_kinds` 且 `affected_object` 含任一 `affected_object_terms` 且 `trust_boundary + reasoning_summary` 拼接文本含任一 `reasoning_terms`。逐问回答：

1. **TP 严格条件**：如上五段合取；anchor 匹配是 file+function+excerpt 三重精确匹配，任何一个规范化差异（函数名、路径别名之外）即失败。
2. **是否只接受 canonical anchor**：是。root 匹配只对照 `spec["anchors"]`；`variant_coverage` 里出现的 anchor 也参与 root 匹配（小漏洞：把 canonical anchor 放进 variant_coverage 可满足匹配），但真正的等价实现（不同函数/文件）不匹配。
3. **等价 source/sink realization**：不允许。R01 有一个 census 指定 variant，但只作 coverage 加分，不满足 root 匹配。GT 未定义 semantic-invariant 约束下的等价锚集合。
4. **unmatched 的含义**：schema 合法、未命中任何 positive/near-miss 标签的 finding，`disposition=unmatched_review`，公开口径 `condition_blind_manual_review_only`，不进任何得分。
5. **unmatched 是否混合**：是。本次审计证实 94 条 unmatched 里同时含 FP（17 cluster）、inconclusive（2）、novel TP（11 + 1 conditional）与既有 root 的等价实现（9）。ADR-0005 的设计意图（不自动断言真伪）正确，但从未做过系统性复核——直到本次。
6. **semantic judge**：不存在任何实现。`semantic_judge_used: false` 是两个 evaluator 里硬编码的常量；设计上是"确定性优先"的取舍（ADR-0005），代价是等价实现全部落 unmatched。
7. **verification 是否参与 formal score**：不参与。GT 侧 `required_for_tp: false`，evaluator 明示 `evaluator_verification: separate_from_agent_verification_claim`；5 个 class-B root 有离线 targeted validation（2026-09-18，jest 断言通过）但只记录在 verification_metadata。agent 的 `reproduction` 字段连统计都不进 repository-v1 evaluator（pilot evaluator 有统计）。
8. **precision/recall 定义**：只有 `positive_recall = tp/(tp+fn)`（分母=20 roots）。没有 precision；pilot evaluator 的 precision bounds 在 repository-v1 evaluator 中被删除。near-miss FP、unmatched、duplicates、invalid 都是独立计数。
9. **是否隐含 GT complete**：得分上隐含（recall 只对 20 roots 定义，GT 外真阳性对得分不可见且不奖励也不惩罚）；但 `unmatched_review` 的存在又显式承认 open world——两者从未闭环。
10. **系统性漏报设计**：(a) canonical anchor 精确匹配使等价实现必然 unmatched；(b) GT anchor 与 snapshot 代码漂移使 root 永不可命中（实证：R07/R08，见 §2）；(c) category/guard_kind/term 匹配的脆弱性；(d) 无 novel-TP 通道 → 历史 94 条 unmatched 从未被 adjudication；(e) recall 分母固定 → 无法随 GT 进化重述。

## 2. 实证发现的 GT/evaluator 缺陷

- **GTD-01（R07/R08 anchor 函数名漂移，两 root 永不可命中）**：GT 要求 `function == 'SSOBase.getUser'`，但两段 excerpt 实际位于 `SSOBase.verifyAndLogin`（SSOBase.ts:38/56/81）。按 schema 如实报告函数名的 agent 必然 `root_anchor_mismatch`。63 个 run 中 R07/R08 命中数 = 0（全历史仅 R04/R10/R12 三个 root 被命中过）。t4 finding-validation（2026-09-21）的 agent_004 即此案例。
- **GTD-02（advisory 声明范围 ≠ snapshot 适用性）**：多条官方 advisory 声明 `<=3.1.1/3.1.2/3.0.12/3.0.13` 已修复，但所述代码模式在 3.1.3 snapshot 仍在（代码级证实：GHSA-r745 OAuth2 refresh id-only lookup、GHSA-5f53 NIM 零权限路由、GHSA-hmg2 vector store 无权限、GHSA-4jpm public-chatbotConfig 等）。census 以声明范围做适用性过滤是合理的第一遍，但会漏掉"声明已修实际仍在"的路径。v1.1 的适用性判定协议改为代码级（已在 GT 草案中固化为 `snapshot_applicability_protocol`）。
- **GTD-03（census 的 fix 字段缺口现已补全）**：R03/R04-06/R07/R08/R09/R15 在 census 中 `fix: null`；patch mining 找到其实际修复 commit（`abe4a860`/`0b74fc07`/`4b805e05`/`754f3d47`/`1939b5f3`/`269a4937`），语义与 root 判定一致，无反向矛盾。
- **GTD-04（unmatched 从未闭环）**：94 条 unmatched 在本次审计前没有任何正式 adjudication 记录；其中 11 个 novel TP 是 benchmark 覆盖的真实缺口。

## 3. 历史 unmatched 审计结果（94 条 → 40 cluster → 裁决）

来源：63 个 flowise runs（S×19、T×8、P×1、B×1 有 unmatched；3 个 M run 无 unmatched）；12 条 formal TP（R04×9 runs、R10×1、R12×1）作为对照不进 ledger。完整数据：`artifacts/gt_audit/unmatched_candidate_ledger.json` + `adjudication_consolidated.json`。

| 分类 | 数量 | cluster |
|---|---|---|
| validated_novel_tp | 11 | UC01 OAuth2 免认证 credential 改写（n=20，最高频）、UC02 feedback 免认证读写（n=12）、UC04 get-upload-file 免认证跨租户读（n=8）、UC08 dataset rows 跨 workspace 删除、UC10 Unstructured loader SSRF（R17 不变量同族新 variant）、UC15 organization read IDOR（R01 read 侧）、UC19 user 创建零权限、UC23 apikey 原文泄露给 apikeys:view、UC27 docstore upsert/refresh 零权限、UC28 docstore vector query 无 workspace 谓词、UC36 nvidia-nim 九路由零权限 |
| canonical_tp_overlap | 9 | R01 += UC14/16/17/18/20；R04 += UC03（TTS body credentialId，n=9）；R07/R08 += UC12/13（anchor 漂移所致）；R20 += UC38（predictions isPublic） |
| false_positive | 17 | UC05（webhook 公开为设计+可选签名）、UC06（共享 storage sink 全防御）、UC07（fullFileUpload 显式 opt-in）、UC11（变量名 key 全来自配置方）、UC21（custom MCP 双重 URL 守卫）、UC22（仅 OPTIONS 预检放行）、UC24（前缀匹配属实但无可达绕过链——穷举全部挂载证实）、UC25（需有效 API key 明文）、UC29（域校验本非访问控制边界）、UC30（不在 whitelist 且有 checkDenyList）、UC31（DELETE 是静态 405 桩）、UC32（isInternal 为调用点硬编码参数）、UC33（128 位 capability token + 常时比较）、UC34（sanitize 与路由消费同一改写字符串，无差分）、UC35（skipVariables 在 utils.ts:982 实际执行）、UC37（apiOverrideStatus 默认 false 门控）、UC39（deny list 默认启用 + redirect 逐跳校验 + IP pinning） |
| inconclusive | 2 | UC09（CustomTool NodeVM——KU02 同能力面，dynamic-dependent）、UC40（listenerId capability 错位但无泄露路径） |
| conditional | 1 | UC26（public-chatbotConfig 净化后结构披露，待威胁模型批准） |

**分母边界**：上表只覆盖 `unmatched_candidate_ledger.json` 中的 94 条历史 finding 所聚类出的 40 个 cluster，故分类之和为 `11 + 9 + 17 + 2 + 1 = 40`。UC41 并非历史 unmatched cluster：它来自公开 issue #6687，是收集协议内 issues/PR 来源的额外候选。将 UC41 一并送入 `adjudication_consolidated.json` 后，跨来源候选宇宙为 **41**，分类为 `11 validated novel TP + 9 equivalent implementation + 17 FP + 3 inconclusive + 1 conditional`。不得把 41 写成历史 run 的 cluster 数。

四个用户点名类别的独立复核结论：node-custom-function 变量泄露 = **FP**（维持）；webhook callbackUrl SSRF = **收紧为 FP/hardening**（batch3 推翻"默认关闭"前提：`HTTP_SECURITY_CHECK !== 'false'` 默认启用 deny list，secureAxiosRequest 逐跳校验重定向 + IP pinning）；未认证 TTS 任意 credential = **R04 等价实现**（携带 canonical anchor 的 run 已正式计分，t4 版本只是没带 anchor）；GitHub 未验证邮箱 SSO = **R08 等价实现 + GTD-01 anchor 缺陷实证**。

## 4. 公开情报覆盖

- **官方 advisory 全量**：130 条（分页拉取，2026-09-21）。声明范围覆盖 3.1.3 的恰好 21 条 = census 已知集合，**advisory 来源在"声明范围协议"下完备**，无 2026-09-16 之后新增。
- **CVE**：21 条中 4 条带 CVE（91935/91937/73603 等）；其余 109 条多为历史版本（≤2.x/3.0.x/≤3.1.1/3.1.2），其中 ~40 条带 CVE 编号，全部记录于 `historical_vulnerability_provenance_ledger.json`。
- **依赖类 vs 第一方**：全部 130 条均为 Flowise 第一方代码 advisory（repo-scoped）；未发现把 package dependency CVE 混入的问题。
- **第三方 write-up 状态**：已完成**有限三角验证**，不是“已完成系统性清扫”，也不是 remaining collection work。已核对 Obsidian、SentinelOne、VulnCheck、Rapid7、CSA（及 NVD 引用）并映射到既有 advisory/family；未产生额外 3.1.3 candidate。这个结论只说明本轮列举来源的三角验证结果，不能外推为互联网来源的完备性声明。
- **issues/PR 结果**：issues/PR sweep 产出**一个**额外候选——issue #6687（open，Host-header SSRF，evaluations 路径），代码级验证 source+propagation 成立（`buildChatflow.ts:1004-1005`、`upsertVector.ts:252-253`）、出站 sink 消费点未定位，归 **UC41 / KU06 inconclusive**，不改变 GT 草案。另：NVD 将 OAuth2 refresh 认证绕过描述为影响 "through 3.1.4"，与 GHSA-r745 声明范围（<=3.1.2）矛盾、与我们的代码级裁决（R21）一致——GTD-02 的第三方佐证。

## 5. Patch-diff mining 结果

snapshot→HEAD（28 commits）全部分诊：15 个已知 fix 前缀全部出现并排除；新增 8 个候选中 6 个实为 R03/R04-06/R07/R08/R09/R15 的 fix commit 补全（GTD-03），1 个（`e816d26a`）是 R10 的后续硬化（snapshot 即 R10 anchor 所述黑名单态，无新 root），1 个（`9d3059fd`）与 UC14（R01 variant）对应。**post-snapshot 修复面 0 个未知新 root**。pre-snapshot 36 条 fix 记录于 `patch_mining_ledger.json`（对 snapshot 均为 fixed/not_present，不入 GT）。已知未修复项现状：`CUSTOM_MCP_SECURITY_CHECK=false` 旁路仍在 main（U02 维持）；KU01 已在 main 修复（snapshot 无 → 维持 known_unscored）；KU02 部分收敛但机制未变。

## 6. Coverage ledger（按来源与子系统）

| 来源 | 审查量 | 新增 candidate |
|---|---|---|
| GitHub 官方 advisories（含范围） | 130 | 0（超出 census 21 之外） |
| OSV npm 交叉验证 | 112 条镜像 | 0（且证明 npm 镜像不可靠：21 条中仅 1 条有 npm 范围数据） |
| NVD / 第三方 write-up（Obsidian/SentinelOne/VulnCheck/Rapid7/CSA） | 已完成的有限 CVE 三角验证，非系统性清扫 | 0 新（CVE-2026-90534=GHSA-hqvm/R04、56271=GHSA-cc4f、31829=GHSA-fvcw、40933=GHSA-c9gw） |
| GitHub issues / security PRs / releases | 标题+security 标签清扫 | 1 个 inconclusive（issue #6687 → UC41/KU06） |
| GitHub Discussions | **scope-excluded**：未列入冻结收集协议，未作深扫 | 不计入本轮经验性饱和；将来若扩展协议，须作为新的、版本化 collection pass |
| post-snapshot git history | 28 commits 全 diff | 0 新 root（8 候选全部映射既有/已裁决项） |
| pre-snapshot git history | 36 条 security fix 简表 | 0（对 snapshot 均 fixed/not_present） |
| 历史 unmatched（63 runs） | 94 条 → 40 cluster | 11 novel TP + 9 等价扩展 + 3 条件/不确定 |

子系统覆盖（audit 触及并给出结论的范围）：server/routes（oauth2、feedback、get-upload-file、attachments、webhook、webhook-listener、documentstore、dataset、nvidia-nim、mcp-endpoint、chatflows、upsert-history、fetch-links、node-custom-functions）、controllers/服务层（predictions、apikey、organization、organization-user、role、workspace-user、user、login-method、text-to-speech、openai-assistants）、auth/SSO（SSOBase、GithubSSO、auth middleware、whitelist 机制、sanitizeMiddleware）、credentials（oauth2 路由、getCredentialData、custom-mcp-servers）、webhooks（controller、dispatcher、listener）、file handling（get-upload-file、attachments、storage providers 全家）、components（MCP core、NodeVM/E2B、Unstructured/Playwright loaders、httpSecurity）、enterprise（organization/role/workspace-user/user/login-method）、CI（jrcq 维持 scope-excluded）。未深入：agentflow 专用链、frontend、marketplace、docker 编排层。

## 7. Saturation、scope 与唯一冻结 blocker

本轮**冻结收集协议**只包括：官方 advisory 全量、post-snapshot git 全量、63 个历史 agent-run outputs 的全量裁决、issues/PR/release 一轮清扫，以及第三方 write-up 的有限三角验证。GitHub Discussions 未被纳入该协议，状态为 **scope-excluded**；其未深扫不会推翻本轮的**经验性饱和**，因为后者只对上述预先列明的来源和分母成立。若要把 Discussions 纳入，必须启动新的、版本化 collection pass，而不能事后把它伪装成本轮冻结 blocker。

在该协议内，advisory DB、git history、有限 NVD/第三方三角验证、issues/PR 对未知新 TP root 的边际产出为 0（issues/PR 的唯一额外候选 UC41 仍为 inconclusive），历史 agent outputs 已一次性穷尽（11 validated novel TP）。因此，**收集侧经验性饱和已达成（scope-bound）**；这不是对所有互联网来源的完备性声称。

`repository-v1.1 FREEZE_READY = no`。唯一的内容冻结 blocker 如下，除此四项外没有额外 blocker：

1. **FRB-01 — UC41 sink leg**：定位并裁决 Host-header `baseURL` 的默认出站 sink 消费点；在确认前维持 KU06/inconclusive。
2. **FRB-02 — TM4 capability-token rule**：批准“服务端铸造、不可猜且无泄露路径的 capability 不入 canonical GT；仅属主校验错位记 hardening”，并确认其对 R22/R23 前提的解释。
3. **FRB-03 — TM6 sanitized-structure-disclosure rule**：批准 UC26 是维持 conditional/known-unscored，还是满足入 canonical 的阈值。
4. **FRB-04 — agent-run-derived GT circularity policy**：批准所有 R21–R29 的来源标记、历史重评只能是 retrospective adjudication、以及独立泛化证据只来自冻结后未参与 GT 构造的新 runs。

evaluator-v2 实现、manifest 挂载、digest 重算和 retrospective rescore 是 freeze-ready 之后的 activation/validation 工作，不是本次内容冻结 blocker；GitHub Discussions 深扫和新的大规模网络搜索同样不是本轮 blocker。

## 8. 十问总答

1. **evaluator-v1 主要缺陷**：canonical-anchor 精确匹配 + 无等价实现通道 + 无 semantic judge + unmatched 无闭环；叠加 GT anchor 与 snapshot 漂移（R07/R08 永不可命中）。
2. **GT 性质**：是 **canonical benchmark targets**，不是完整漏洞集合——census 本身就只从 advisory 聚类了 20 个 root；审计新增 11 个无 advisory 的 novel TP 证明"完整漏洞集合"的说法不成立也从未成立。
3. **公开资料覆盖度**：advisory 全量 130 条已审（声明范围协议下完备）；CVE 经 advisory 映射覆盖；第三方 write-up 已完成有限三角验证，未声称系统性清扫或互联网完备。
4. **patch mining 新增**：0 个未知新 root；6 个已知 root 的 fix commit 补全；1 个 R10 后续硬化；1 个 UC14 映射。
5. **unmatched/issue 构成**：历史 unmatched 的 40 cluster 为 FP 17、inconclusive 2、conditional 1（UC26）、validated novel TP 11、equivalent implementation 9；额外 issue 候选 UC41 使跨来源裁决宇宙成为 41，inconclusive 增至 3。
6. **应进新版 GT**：9 个新 root（R21-R29）+ R01/R04/R07/R08/R17/R20 的等价锚扩展——全部有代码级静态链与 file:line 证据，且 4 个有家族 advisory 佐证。
7. **不应进**：17 个 FP（多数有明确反证）、UC09/UC40（inconclusive/不可达）、UC26（待规则批准）；依赖类 CVE 一律不进；GHSA-jrcq（CI-only）维持排除。
8. **v1.1/evaluator-v2 设计**：见两份提案文档（等价锚由 semantic invariant 约束、双视图得分、novel adjudication 通道、circularity 标记、retrospective rescore 计划）。
9. **饱和**：在冻结收集协议的范围内是；GitHub Discussions 为 scope-excluded，不影响该 scope-bound 结论。剩余冻结条件仅为 §7 的 FRB-01 至 FRB-04。
10. **未来正式比较用哪个 generation**：在 v1.1 冻结前，正式 P/B/T/M 得分仍用 evaluator-v1（保持历史可比性）；v1.1 冻结后的新 matched block 用 evaluator-v2 并同时报告 canonical（29 roots）与 novel-adjudication 两个视图；同一 block 不得混用两个 generation 得分。

## 9. 术语与分母

- **canonical benchmark targets**：冻结 GT 中用于正式 canonical recall 的 root 集；v1 是 20 个，提案中的 v1.1 是 `20 old roots + 9 proposed new roots = 29 proposed roots`。它不是完整漏洞集合。
- **validated novel TP**：不匹配当前 canonical root、但经独立静态裁决确认具有 source→sink、缺失 guard 与 file:line 证据的候选；本轮历史 unmatched 中为 11 个 cluster。它是候选 GT 扩张证据，不能自动改写旧分母。
- **equivalent implementation**：满足既有 root 同一 semantic invariant、但锚位在不同实现位置的候选；历史 unmatched 中为 9 个 cluster。它扩展既有 root 的匹配位置，不新增 root。
- **historical vulnerability set**：本轮实际裁决的候选集合，而非产品完整漏洞集；严格说包括 94 条历史 finding → 40 个 historical cluster，及来自 issue #6687 的 1 个额外候选（跨来源合计 41）。
- **empirical saturation**：在冻结收集协议已列来源内，未知新 TP root 的边际产出趋近零的 scope-bound 观察；不等于全网完备性，且不包含 scope-excluded 的 GitHub Discussions。
- **retrospective rescore**：冻结后只读地以 v1.1 规则重述历史 run finding 与新 GT 的关系；不改写 v1 产物或历史正式得分。
- **independent generalization evidence**：冻结后、未参与 GT 构造的全新 seed / matched block / 新 snapshot case 上的结果；历史参与构造 R21–R29 的 runs 不属于此类证据。

## 10. 资产索引

| 资产 | 路径 |
|---|---|
| 本审计 | `docs/research/flowise-3.1.3-repository-v1-gt-coverage-audit-20260921.md` |
| repository-v1.1 升级提案（含威胁模型纳入规则、circularity 规则） | `docs/research/flowise-3.1.3-repository-v1.1-upgrade-proposal-20260921.md` |
| evaluator-v2 设计提案（含 retrospective rescore 计划） | `docs/research/flowise-evaluator-v2-design-20260921.md` |
| GT v1.1 草案（29 roots，未冻结） | `artifacts/gt_audit/ground_truth_v1_1_draft.json` |
| 历史 unmatched candidate ledger | `artifacts/gt_audit/unmatched_candidate_ledger.json`（+ `.md` 摘要） |
| 裁决合并表（41 个跨来源候选 = 40 historical cluster + UC41 issue） | `artifacts/gt_audit/adjudication_consolidated.json`（+ `.md`） |
| 裁决批次明细 ×4 | `artifacts/gt_audit/adjudication_batch{0_core,1_whitelist,2_enterprise,3_sandbox_ssrf}.{json,md}` |
| 公开情报 provenance ledger（130 advisories + 范围矩阵） | `artifacts/gt_audit/historical_vulnerability_provenance_ledger.json`、`github_advisories_with_ranges.json` |
| patch mining ledger | `artifacts/gt_audit/patch_mining_ledger.json`（+ `.md`） |
