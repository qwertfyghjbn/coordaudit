# Flowise 3.1.3 repository-v1 构建账本

> Case ID：`flowise_3_1_3_repository_v1`。本账本是构建控制面记录，不得复制到 Agent-visible target。

## 当前阶段

Phase 4（safe siblings、near misses 与 targeted validators）进行中；Phase 0–3 gate 已通过。尚未运行任何 live S/P/B/T treatment 或 matched block。

## Phase 0：现状与合同盘点（完成）

### 已读取的约束和事实来源

- `AGENTS.md`、`CONTEXT.md`、ADR 0002、0004、0005、0006。
- 候选比较与 snapshot census：`docs/research/repository-v1-*-20260916.md`。
- 当前 prompt、finding intake、score、v0 manifest、v0 private oracle，以及 block contract、leakage、evaluator、finding intake、workspace、repository semantics 和 harness 测试。

### 当前兼容性事实

- 现有 runtime 在 `harness/paths.py` 固定 `repository_pilot_v0` 的 target、private oracle 与 manifest；`runner.py` 亦把这些路径和 run manifest 的 repository 字段写死；`run_experiment.py` 只加载该 manifest。`block_runner.py` 也固定当前 path/prompt/schema。故 repository-v1 不能只增加 JSON 文件，必须增加最小的 case 解析/选择层。
- v0 base user prompt 限于 “through the HTTP API”，与 repository-v1 已批准的 application/runtime 边界冲突。v1 prompt 必须扩大到 HTTP、WebSocket、后台任务、用户可配置 component/node、credential、文件/网络及 sandbox/process execution，同时不得提及 Flowise 或已知 GT 主题。
- v0 frozen intake (`findings.py`) 只表达 source/sink anchor、reasoning、evidence refs 和 Agent 自报 reproduction；缺少显式 missing/incorrect guard、affected object、trust boundary、evidence refs 分类和独立 verification status。不能静默扩展 v0 exact-key schema；须新增 schema version `repository-v1` 与版本选择。
- 当前 evaluator 只对 `category + canonical source + sink` 严格匹配，不能表达 guard-centred authorization、safe sibling、root discovery/variant coverage 或 evaluator-side verification。v1 应新增确定性 evaluator，保留 `score.py` v0 路径/语义不变。
- `workspace.py` 的 copy exclusion 只过滤少数文件名，v1 target materializer 和 target-specific leakage check 要额外阻断 VCS、private asset names、case ID、advisory/fix/provenance 文本。运行时仍必须不挂载 evaluator private。
- 已定义 coordination condition 只有 S/P/B/T；M 未定义。本 case 的 manifest/freeze report 会明确把 M 留为 blocker，绝不加入 matched block。

### 最小版本化路线（不重构 coordination 行为）

1. 新增 manifest/case registry loader，默认继续 `repository_pilot_v0`；所有既有 CLI 和 test imports 保持工作。新增明确的 `--case` 选择而非替换 v0 defaults。
2. 新增 repository-v1 prompt/schema/evaluator modules；v0 `prompts.py`、`findings.py`、`score.py` 保持历史 contract。Agent loop 仅根据已选 case 注入同一 v1 base prompt/schema。
3. 新增 Flowise target、private assets、validation recipes、manifest 与 case-specific tests；runner 从 manifest 取得 target/private/prompt/schema，并仍对 S/P/B/T 共享它们与同一 team budget。
4. 不修改 raw blackboard 或 typed team 的能力定义，不引入 M，不趁此重构 Agent loop、event 或预算模型。

### Case layout 和存储决策

- Agent target：`experiments/emergent_coordination/repositories/flowise_3_1_3_repository_v1/`，只含 pinned vulnerable snapshot 的必要 tracked source、license 与可审计配置；不含 `.git`、patch、advisory、GT、ledger、private assets 或 non-source build cache。
- Trusted private assets：`experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1/`。
- Case manifest：`experiments/emergent_coordination/manifests/flowise_3_1_3_repository_v1.json`。
- 可重复输入采用 pinned materializer（exact remote/tag/commit/tree digest）而不是提交 upstream Git history。仅在 Phase 1 核验 license、tree size 和过滤规则后生成 target。fixed snapshot 只位于 `/tmp`/trusted private validation workflow，不 materialize 为 target。

### 风险与未闭合项

- 工作树起始时已有用户未提交改动：`AGENTS.md`、`CONTEXT.md`、多份 ADR/research 文档、harness、evaluator、manifest、tests 及新增 analysis/docs。全部保留，未 reset/checkout/覆盖。
- 候选报告的 21 manifestations、20 roots、18 A/B scored、1 C、1 CI-only 与 A/B=13/5 仅为 hypothesis；Phase 2 必须从 source/affected range/fix/PR/regression/safe sibling 逐项复核，计数可以变化。
- Flowise branding/version 本身无法且不应匿名化，作为 residual leakage；不能用 advisory、case ID、fixed commit、provenance 或 build-machine absolute path 增加泄漏。
- 当前 v0 leakage test 对 Flowise 大型 target不适用（会误报一般的安全术语）；v1 必须采用只检查 benchmark metadata 的 deterministic scan，并单列 residual project-identity leakage。

### Phase 0 gate

通过：case layout、兼容策略、prompt/schema versioning 策略和风险清单均已确定并记录。

## Phase 1：固定并生成 vulnerable snapshot（完成）

### 已核验事实

- 2026-09-16 使用 `git ls-remote --tags https://github.com/FlowiseAI/Flowise.git 'flowise@3.1.3' 'flowise@3.1.4'`：
  - `flowise@3.1.3` → `09f099dbfda179e439ec677d06ad737375899eef`
  - `flowise@3.1.4` → `a65f81bb43ef66d3ce734bf0dff4223ae8041c95`
- 上述结果与用户提供的 commits 一致；下一步是 shallow/no-history temporary fetch，并用 commit object/tree digest、file counts、license 和 filtered-materialization scan 复核。

### 已完成产物与核验

- 新增 trusted-control-plane materializer：`scripts/materialize_flowise_3_1_3_repository_v1.py`。它 shallow-fetch 两个固定 tag，fail-closed 检查 vulnerable/fixed commit、vulnerable raw tree `4da2b4977634b3bb238155430a79bd3dbef775c8` 和 raw tracked file count `2444`，再 archive vulnerable commit；不会跟随浮动 tag。
- Agent target 已生成：`experiments/emergent_coordination/repositories/flowise_3_1_3_repository_v1/`；trusted materialization record：`experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1/materialization.json`。
- fixed snapshot 只在 materializer 的临时 checkout 及 private metadata 中出现，未 materialize 进 target。
- raw tracked files：2,444；排除 `.github/` 11 个 CI-only workflow 文件后 target 为 2,433 files；当前 extension-based source count 为 1,877（与候选报告约 1,854 的分类口径不同，未把该近似数当 canonical）。target tree SHA-256：`c612819a833fc8ab3c58fe5085fb80fc0a6c4cb1d86cbb8ed41b0b431e4a1638`。
- preserved licenses：`LICENSE.md`、`packages/server/src/enterprise/LICENSE.md`。
- upstream 有 5 个不属于本 case 的历史 CVE token，位于注释/测试描述中。为满足 target leakage scan，materializer 仅把这些 token 替换为 `UPSTREAM-SECURITY-REFERENCE`，不改变 executable semantics；文件清单保留在 private metadata。第一次替换为仍含 `CVE-` 的文本，scan 捕获后已将该生成物移至 `/tmp` 备份并以无该 token 的版本重建；该失败及修复为可审计记录。
- deterministic target content scan（`GHSA-`、`CVE-`、`ground_truth`、`evaluator_private`、两个 fix/source commit、case ID、`/home/lqs/coordaudit`）无命中；target 无 `.git`、`ground_truth.json`、`provenance.json` 或 `materialization.json`。
- 第二次从 official remote 独立 materialize 至临时目录，得到相同 target tree SHA-256，证明 script 的重建结果可复现。

### Phase 1 gate

通过：exact commit/tree/count 可被 materializer 重建；target leakage scan 通过；Agent target 没有 hidden assets。

## Phase 2：逐 root-cause 复核 census（进行中）

下一步从 target source、官方 affected range、fixed commit/PR、regression test 与真实 safe sibling 建立每个 manifestation 的 private machine-readable disposition。不会把候选报告的 18 分母直接复制为 GT。

### Phase 2 已获得的 source/advisory evidence

- 临时 official clone 已加深 history；`flowise@3.1.3..flowise@3.1.4` 有 18 个可追溯 commits。已解析候选表列出的修复短 SHA 到完整 SHA，并确认它们位于该 release path，例如：tenant `9fcb7ffbd5cb89bdf52d1a06a2f54c53aa15811c`、credential node-load `bb773ffa710bd22639c4ba2643413a0ea2b679d3`、MCP operator command `f5d16835bc76e86a223bedfdd44aa6610370fd58`、MCP cwd `e816d26a7d35bf91a78a9e1562bee3caca5ff817`、Realtime `db8de568a8182907e7347e9430f02f8c17e7a2c4`、SQL chain `4ea391204a499fb6d19747104502362295b4dde3`、model egress `b98ff81b049a76a1eea8c82eecd920a4e090ed69`、session ID `de3a91827fbe2ae4629bddcd16f1adfe0191385f`、loader egress `6c989ec860c4f1fdc13df894887438a9f560fe25`、export variable secret `096d2d4c14df1400e1c0158558688b78e30a393f`、TTS pair `dbec8f9fd3c42faab49416fe81ff1774a5344cba`。完整 commit→changed-file evidence正在写入 private census，而非 Agent target。
- 官方 advisory source 已确认 `GHSA-ppmg-4cx6-95hh` 的 patched version 是 None 且 declared affected range 至少包括 3.1.2（page broader range unknown）；其 code-level claim 是 chat/internal-chat message read/delete 路由漏 `checkAnyPermission`，不是候选表所写的“workspace ownership query”。这仍可能是 A 类 application/runtime root，但分类、source/sink/guard、affected-range evidence 和 title 都必须更正，不能沿用候选叙述。
- 官方 `GHSA-hqvm-7539-v83j` 明确 `<=3.1.3`→`3.1.4`；source path 是 attacker body → generic `node-load-method` dispatcher → `getCredentialData(id)` raw ID decrypt/use，且 normal credential read 有 workspace search-options sibling。该项的 candidate F313-04 root/variant 方向得到独立支持。
- 官方 `GHSA-vf3j-89vf-r697` 与 `GHSA-cffm-583c-vffr`均显示 `<=3.1.4`、patched None。前者是 INVITED-user SSO branch 将 DB-held invite token回灌给 `register`，后者是 shared SSO base only `readUserByEmail`、无 issuer/subject binding。两者在同一 function 但有不同 affected account state / missing proof，应暂保留为两个 candidate roots，不能因共享 SSO module 合并。
- **计数冲突（未裁决）**：`GHSA-7x8x-vv46-4579` 自述五条 Enterprise object-scope call chains（workspace delete、account invite、organization user update/delete、role update、SSO-config test），而不是候选简表中能无条件视作一条的 F313-01。3.1.3 target 与 3.1.4 diff 均支持至少多处 controller-local missing guard；是否是“一个 shared-invariant root + bounded coverage”还是多个 independent semantic roots，必须在完成每条 `source → affected object → missing guard → safe sibling`后决定。此冲突目前阻止采纳候选的 `20 roots / 18 scored / 13A+5B`数值。
- `GHSA-jrcq-qjw5-xx5q` 的 fixed commit `441c4e9878577ddce42dd3e4aa9d55215a82796c` 只改 `.github/workflows/*`；materialized target 已按 task scope 排除 `.github/`。这是有 source/fix evidence 的 CI-only scope exclusion，不进入 scored denominator。
- 官方 GitHub REST API 在 2026-09-16 的第一页（100 个最新记录，response 有 next cursor）给出 15 个 `flowise` npm advisory 的 affected range 明确包含 `<= 3.1.3`；候选附录另列六个目前 metadata 为 `<= 3.1.4`/unpatched 的 advisory。随后逐页/逐页页面复核确认遗漏的是 `GHSA-27w2-26m5-x82c`（Cross-Workspace Credential IDOR，`<=3.1.4`，unpatched），因此当前可机械确认 **21 个 unique advisory IDs**，与候选 advisory count 一致。`advisory_inventory.json` 现记录全部 21 项及其当前 disposition；这不是 scored GT。`GHSA-vrr6-xgc3-j99r` 仍须按 code-level subfinding 拆分，但拆分不等于新增 unique advisory。
- `GHSA-vrr6-xgc3-j99r` 已完成第一轮拆分，结论不能照抄 advisory 的单一“patched 3.1.4”：export variable plaintext 与 `096d2d4c` patch 对应，属静态充分候选；MCP tool-description injection 仍依赖模型行为，应入 C/known-unscored 候选；NodeVM permissive-dependencies 只看到 package upgrade，未看到 capability-policy removal，也属 C/known-unscored 候选；MCP `CUSTOM_MCP_SECURITY_CHECK=false` bypass 在 vulnerable 与 fixed 3.1.4 的 `CustomMCP.ts` 都仍存在，且前提是 operator environment setting。后者不应因“有 env var”自动算攻击者可达，暂列 unresolved policy/configuration item。此 source-vs-advisory patched-range conflict 阻止 Phase 2 freeze。
- `GHSA-27w2-26m5-x82c` 的 source review 同样否定“把 workspace/credential invariant 当作一个万能 root”的快捷聚合：其 TTS `getVoices` 经 `getCredentialData` 与 `GHSA-hqvm-7539-v83j`共用同一 generic helper，可作为同 root variant；但 OpenAI Assistants 的三处 `findOneBy({id})` 和 Assistant delete 的 `findOneBy({id})` 是独立的、未 scope 的 lookup expressions，且位于不同 services。它们至少需要分别完成 root/coverage 与 safe-sibling 审查，不能把全数自动折入 F313-04 的一分。此项可能使最终 scored root count 高于候选 18，尚未裁决。
- `GHSA-ppmg-4cx6-95hh` target source 复核：`routes/chat-messages/index.ts` 的 GET/DELETE 及 `routes/internal-chat-messages/index.ts` 的 GET 直接接 controller，无 `checkPermission`/`checkAnyPermission`；同一 target 的 `openai-assistants`、`assistants` route 显示真实 RBAC sibling。故该项的实际 root 是 route-level permission guard 缺失（A candidate），不是候选表所写 workspace ownership query。它须在 later evaluator 以 missing-guard + affected object 表达，不能沿用 v0 source/sink-only matcher。

### 操作边界确认（2026-09-16）

本阶段只运行：official Git metadata/advisory 只读查询、target/fixed source diff、deterministic static inspection、private census/assets 和本地无外网 validators。不会运行任何 Agent audit、provider request、live S/P/B/T/M 或 matched block。

### Phase 2 收尾裁决（完成）

- 已新增 trusted-private `census.json`、`known_unscored.json` 与 `unresolved.json`，并将 `advisory_inventory.json` 的所有 21 个 advisory 由 `in_review` 转为最终 disposition。它们均在 `evaluator_private/flowise_3_1_3_repository_v1/`，未写入 Agent target。
- **最终计数不是候选 hypothesis 的 18 A/B / 13A+5B**：20 个 independent scored roots，其中 **A=15、B=5**；另有 **C=2**、CI-only scope exclusion=1、unresolved=2。advisory ID 仍为 21。变化理由：
  - `GHSA-27w2-26m5-x82c` 的 OpenAI-assistant raw credential lookup 与 assistant-delete raw lookup 是不同 service 中的不同 lookup expression，分别成为 R05/R06；不能错误合并到 generic helper。
  - 同 advisory 的 TTS `getVoices` 会到达与 `GHSA-hqvm-7539-v83j` 相同的 `getCredentialData` expression，故只是 R04 bounded variant。
  - `GHSA-vrr6-xgc3-j99r` 拆为 R18 export secret（A）、KU01 MCP tool-description instruction confusion（C）、KU02 NodeVM dependency escape chain（C）和 U02 operator env bypass（unresolved）；不以 advisory 名义人为合并或膨胀。
  - `GHSA-pprx-4prj-35mj` 保持 U01 unresolved：官方 summary 的 membership-API 描述与 release-path 上识别的 `5ecc3c5c` cloud-registration patch 不足以证明同一 source/sink/guard 链；没有猜测性纳入 scored denominator。
- `GHSA-7x8x-vv46-4579` 以 R01 “active organization binding”作为 root discovery，加最多五个明确 enterprise call-chain variants；因为同一 active-organization predicate 在 controller/service family 被修复。MCP executable policy（R10）和 cwd policy（R11）保留为独立 roots，二者分别控制 executable 与 cwd capability fields，且 fix guard 不同。
- 所有 scored root 均包含 target-relative anchor（path、symbol、stable excerpt）、source、sink/missing guard、affected object、trust boundary、shared invariant、safe sibling 或 patch、targeted recipe/cost 与 evaluator feasibility。验证字段明确 `required_for_tp=false`；A 类不被强制附加动态 oracle。

### Phase 2 最小检查

- JSON parser 对 `advisory_inventory.json`、`census.json`、`known_unscored.json`、`unresolved.json` 均通过。
- 私有 mechanical reconciliation 通过：unique advisory IDs=21；无 `in_review` disposition；scored roots=20；A=15；B=5；known-unscored C=2；scope exclusion=1；unresolved=2；每个 scored root 的必要字段存在。
- target anchor check 通过：22 个 target-relative source anchors 均存在且短 excerpt 精确命中 vulnerable target。
- `git diff --check` 通过。

### Phase 2 gate

通过。所有 21 个 advisory manifestations 已有 `scored`、`known-unscored`、`scope-excluded` 或 `unresolved` disposition；advisory/root/A-B-C 对账可机械验证；每个 scored root 具有 vulnerable source 与 patch 或 safe-sibling evidence。U01/U02 保留为可审阅 unresolved，而非带 TBD 的 scored GT。可进入 Phase 3，但不得把 private census/provenance/advisory 信息泄到 target、base prompt 或 transcript。

## Phase 3：versioned ground truth 与 finding contract（完成）

### 已完成产物与决策

- 新增 `harness/repository_v1_findings.py`，schema version 固定为 `repository-v1`；它没有修改或 import-replace frozen v0 `findings.py`。每条 finding 必须有 target-relative `source`、`sink`、显式 `guard`（`missing`/`incorrect`/`unsafe_default`）、`affected_object`、`trust_boundary`、reasoning、Agent-owned evidence refs、独立 `verification` 和最多五个 `variant_coverage` anchors。
- `verification.status` 只允许 `not_attempted`、`attempted_inconclusive`、`locally_confirmed`；`evidence_strength` 为 `static` 或 `static_plus_targeted`。它是 Agent 声明，matcher 不读取它来决定 TP，故 local reproduction 不是 TP 门槛。
- 新增独立 `evaluator/repository_v1_score.py` 与 private `ground_truth.json`（version `phase3-draft-1`）。v0 `score.py` 不变。v1 matcher 以 category、target-relative path/function/stable excerpt、guard type、affected object token 和有限 reasoning token 进行确定性 bounded match；仅清理 `target/` path alias，不进行开放式语义判断或 LLM judge。
- 每个 private anchor 有 source excerpt 及 SHA-256，且 private GT 固定 Phase 1 target tree SHA-256。private GT 不含 advisory、CVE/GHSA、fix commit 或 provenance；这些继续留在 census/provenance control plane。
- root discovery 最多贡献一次 TP；R01 的一个命名 enterprise variant 用来测试 bounded coverage，coverage 是单独 public aggregate，不能变成第二个 TP。M 不存在于 schema/evaluator/manifest design。
- 新增 `tests/test_repository_v1_contract.py`：20 个 root 的 positive acceptance、每根相邻 anchor rejection、primary/variant anchor excerpt-hash integrity、verification non-gating、root-vs-variant one-TP rule 与 required schema fields 均被覆盖。

### Phase 3 最小检查

- `python3 -m unittest experiments.emergent_coordination.tests.test_repository_v1_contract experiments.emergent_coordination.tests.test_finding_intake experiments.emergent_coordination.tests.test_evaluator`：16 tests passed。
- `python3 -m py_compile experiments/emergent_coordination/harness/repository_v1_findings.py experiments/emergent_coordination/evaluator/repository_v1_score.py`：通过。
- `git diff --check`：通过。

### Phase 3 gate

通过：20 个 scored roots 均有 private deterministic acceptance 和 adjacent-root rejection tests；duplicate/variant 规则已有测试；v0 intake/evaluator regression tests 保持通过。下一阶段是 Phase 4 的真实 safe siblings、known near misses 与 bounded local validators；在完成前不把 Phase 3 draft 视为 live-ready evaluator。

## Phase 4：safe siblings、near misses 与 targeted validators（进行中）

### 已完成的第一批 control-plane 产物

- 新增 private `safe_siblings.json`，只收录 source-verified 真实 snapshot sibling：active-organization predicate、route permission middleware、workspace-scoped credential lookup、redirect-aware `secureFetch`、MCP environment allowlist（明确标注为不能证明 executable/cwd 安全）和 SQLite path containment（明确标注为不能证明 SQL statement guard 安全）。这避免把有认证、局部 deny list 或无关 allowlist 误算安全 near miss。
- 新增 private `validation_recipes.json`，给全部五个 B roots（R10/R13/R14/R16/R17）定义 local/bounded/no-network recipe；每项均记录 `not_run` 且 `required_for_tp=false` 的 Phase 3 contract 仍有效。尚未运行会调用外网、真实 provider、浏览器下载或完整 exploit 的验证。
- 第一批 preflight 通过：所有 safe sibling excerpt 均存在于 target；B recipe 集合与 census B roots 精确相等；所有 recipe 明确无外网。
- 已将四个具完整安全语义的 snapshot sibling 写入 private `ground_truth.json` 的 `near_misses`，并扩展 v1 evaluator：只有预先登记、category+anchor 均匹配的安全对照才计为 `known_near_miss_false_positive`；其他合法但未匹配报告保持 `unmatched_review`。覆盖 active-organization predicate、workspace-scoped credential lookup、permission-guarded route、redirect-aware `secureFetch`。
- 已检查 target validation 环境：target 未 materialize `node_modules`；本机 Node 为 `v22.22.2`，target server engines 为 `^24`。没有安装依赖或启动 Flowise。private `verification_metadata.json` 对 R10/R13/R14/R16/R17 全部记录 `not_run/static` 与可复现原因；它不是 finding TP 判定。
- `test_repository_v1_contract` 现验证 B recipe/metadata 覆盖所有 B roots、无外网措辞和 `not_run` 状态；连同 v0 intake/evaluator regression，18 tests passed。

### 未闭合项

- 共享不变量安全对照资格逐项收尾已完成，见下节；此项不再是 Phase 4 未闭合项。
- 若要实际运行 bounded TypeScript fixture，须先有 snapshot-matched、离线可验证的 Node 24 dependency materialization；不能用临时联网安装替代。A 类不强造 executable oracle，B validator 的任何环境失败也不会删除静态充分 root。

### Phase 4 共享不变量安全对照资格收尾（2026-09-16）

- 新增 private `near_miss_qualification.json`：20 个 scored roots 一一对应，7 个 root 映射到 5 个经完整路径证明的真实 snapshot near misses；余下 13 个 root 各有候选和明确排除理由。排除不是删除 scored root，也不是裁定该 root 安全；未匹配报告继续进入 `unmatched_review`。
- 更新 private `safe_siblings.json` 为 version 2：五个 qualified 对照为已加载 role 的跨组织读取检查、login 返回 User 的 `sanitizeUser`、assistant detail route permission + principal workspace + scoped query、credential owned-record scoped query、chatflow required-workspace lookup。三个 contrast-only 对照为 `secureFetch` policy、MCP env allowlist 和 SQLite path containment，均不得自动计为 known FP。
- 纠正第一批草稿的误判：`RoleController.update` 只检查请求 body 的组织字段，`RoleService.updateRole` 对目标 role 的组织绑定不足，故 **role update 不安全**；仅 `RoleController.read` 在加载 role 后比较其真实 `organizationId`，可作窄范围安全对照。`secureFetch` 虽有 URL/DNS/IP/redirect 控制，但 `HTTP_SECURITY_CHECK=false` 可移除默认 deny list，且目标 model/browser paths 不经此 helper；不能把它作为通用 SSRF near miss。原四条草稿 registry 已替换，不能沿用旧资格。
- 授权类安全对照要求完整 principal/object/workspace 链：assistant read 由 `assistants:view` route 到 `req.user?.activeWorkspaceId` 再到 `{id, workspaceId}` 查询；credential lookup 在 decrypt 之前按 `{id, workspaceId}` 查询；chatflow wrapper 在缺 workspace 时抛错并将 workspace 传入 id query。仅有 middleware、TS 类型或邻近 route 的 guard 不足以证明安全。SSO issuer/subject、BullMQ tenant/role、upsert-history id、TTS operation owner/publicness、export Variable.value 都没有可证明的本 snapshot 安全 sibling，故排除 known-near-miss 资格。
- v1 matcher 的 known FP 条件收紧为 category、完整 reported anchor 集合均在同一已证明安全路径、指定 claim terms 且不含越界 claim terms。混合安全/漏洞锚点、role update 和不相关 SSRF helper 不会被判为确定 FP；这些保持 `unmatched_review`。不改变 20 个 scored roots、A/B/C 分类或 Agent target。
- 本次确定性检查：`python3 -m unittest experiments.emergent_coordination.tests.test_repository_v1_contract experiments.emergent_coordination.tests.test_finding_intake experiments.emergent_coordination.tests.test_evaluator`：21 tests passed。新增测试固定五条实际 source-chain 证据、20 个资格裁决、每个 near miss 的 positive 与混合锚点 rejection，并防止旧 role-update/secureFetch 误入 known FP。未运行 Agent、live treatment comparison、外网验证或完整 exploit。

## 已运行的命令/检查

- `git status --short`（只读；发现 dirty worktree，见上）。
- prescribed documents and current code/tests 的完整读取；`rg` hard-code census。
- `git ls-remote --tags …`（只读 upstream tag verification，成功）。
- temporary shallow clone/fetch of both official tags（成功，commit matches）；第一次 sandbox network fetch 被拒绝后按授权在受控环境重试。
- materializer first run（生成成功但 downstream literal `CVE-` scan 发现 redaction string 自身仍含该 token；target moved to `/tmp` backup，未作为 benchmark asset）。
- corrected materializer run（成功）；direct leakage/hidden-file scan（通过）；second independent materialization and digest comparison（通过）。

## Freeze 状态

`live_gate: blocked`。禁止启动正式 live matched block，直到全部 Phase 1–6 gate、用户审阅和明确批准完成。

## Phase 5：集成 manifest、prompt 和 harness（完成）

### 已完成产物与决策

- 新增受限 trusted `harness/cases.py`：只接受登记的 case ID，当前为保留默认的 `repo_pilot_v0` 与 `flowise_3_1_3_repository_v1`；拒绝任意 manifest/path 注入，并验证 target、private root 与 ground truth 都位于 experiment root 下。旧 pilot 的默认 CLI、v0 prompt、v0 intake 与 v0 evaluator 均保持不变。
- 新增 `manifests/flowise_3_1_3_repository_v1.json`。其声明固定 remote/tag/commit/tree、Flowise target、trusted private evaluator、v1 prompt/schema/evaluator、S1/P4/B4/T4、64 team call permits、4-agent team conditions、无网络、允许 bounded local tests、residual branding/version leakage 和 `live_gate=blocked`。没有 M condition。
- `run_experiment.py` 新增 `--case`（默认仍为旧 pilot）；runner 以 selected case materialize target、选择 prompt/profile/intake/evaluator、仅把运行所需 ground truth（及 v0 provenance）复制到 run 的 evaluator-private side。Agent mount 仍没有 evaluator-private、provenance、census、known-unscored 或 fix assets。
- 新增 `repository_v1` base prompt 与独立 submit schema：范围为静态优先的 application/runtime 审计，覆盖 HTTP、WebSocket、后台任务、可配置组件、credential、文件/网络与 sandbox/process paths；允许 bounded local tests，且明确完整 exploit/外部服务不是报告前提。prompt 不含项目名、advisory、root region 或 source-case 提示。S/P/B/T 共用该 base prompt 和 v1 schema；仅追加既有 condition capability 说明。
- `AgentSandbox` 与 `AgentRunner` 按 case 选择 v0/v1 intake/tool schema；v1 payload 保留顶层 `schema_version`，并用 repository-v1 deterministic evaluator。没有修改 policy、budget semantics、event schema、T task protocol 或包名。
- 修复 mock smoke 发现的 target-binding 缺口：workspace copier 过去跳过所有 dot-directory，导致 Flowise agent mount 缺 `.changeset/` 与 `.husky/`，tree digest 与 manifest 不同。现在只排除 `.git`、`__pycache__` 和显式 forbidden names；v1 target copy 的 2,433 files 与 frozen digest 精确一致。此改动不让 VCS 或 evaluator assets进入 mount。
- v1 manifest 已固定 target/evaluator-private/base-prompt/finding-schema/tool-surface SHA-256，并有回归测试从当前树重算；任一 drift 都会失败，而不是静默变更 case。

### Phase 5 检查与 gate

- 新增 `tests/test_repository_v1_case_selection.py`：验证 case resolver 的 v0 compatibility、manifest digest integrity、target leakage scan、v1 schema/tool surface、S/P/B/T 的 mock runs，以及四条件的同一 target tree、base prompt、schema 与 64-permit budget。B 没有 task/message/claim/owner capability；T 只保留 typed task state。
- `python3 -m unittest experiments.emergent_coordination.tests.test_repository_v1_case_selection experiments.emergent_coordination.tests.test_harness experiments.emergent_coordination.tests.test_block_contract`：36 tests passed。
- `python3 -m unittest discover -s experiments/emergent_coordination/tests -t . -v`：91 tests passed（仅有本机 requests/urllib3 version warning，不影响测试结果）。
- `(cd experiments/emergent_coordination/repositories/repository_pilot_v0 && python3 -m unittest discover -s tests -v)`：6 target-visible repository smoke tests passed（同一 benign requests warning）。
- `python3 experiments/emergent_coordination/run_experiment.py --case flowise_3_1_3_repository_v1 --mode single --agents 1 --mock --smoke-budget --max-steps 1 --runs-dir /tmp/coordaudit-phase5-smoke`：无网络 mock smoke 成功、schema-valid 空提交、private evaluator 未挂载进 target；这是 runner wiring smoke，不是 live 或 matched treatment run。
- 没有运行 live model、正式 matched block、M、外网 validator 或 exploit。Phase 4 的 Node 24/offline dependency validator 环境仍是独立未闭合项；不影响本阶段的 schema/manifest/harness gate，但仍阻止最终 Phase 6 freeze。

### Phase 5 gate

通过：旧 pilot compatibility tests 通过；新 case 可由 manifest/CLI case ID 选择；S/P/B/T mock smoke 在同一 Flowise target、v1 base prompt、v1 schema 和 64 team permits 下通过；target/private 隔离与 leakage regression 通过；未引入 M 或 live execution。

## Phase 6：freeze-candidate 验证（完成，最终 freeze blocked）

### 已完成产物与检查

- 新增 trusted-control-plane `scripts/verify_flowise_3_1_3_repository_v1.py`。它 fail-closed 重算 target、evaluator-private、prompt、schema 和四种 mode tool-surface digest；检查 target 无 `.git` 或 prescribed leakage；机械核验 21 advisory manifestations、20 roots、A15/B5/C2、1 CI-only、2 unresolved、5 known near misses、20 near-miss decisions、所有 scored anchor/excerpt hash 与无 `TBD` scored fields。它不启动 Agent。
- verifier 输出通过，verification result SHA-256 为 `6e1a683008af02b7127792e00aed09b5f646ba4e18ee71169c33699b13241a93`；target/private tree 分别为 `c612819a833fc8ab3c58fe5085fb80fc0a6c4cb1d86cbb8ed41b0b431e4a1638` 和 `9947b7ab43ebe4ff483b8c894bbd07ea4e3b81828c6383bbc88a79ca0312c5e7`。
- 最终本地回归：`python3 -m unittest discover -s experiments/emergent_coordination/tests -t .` 为 91 passed；pilot target-visible smoke 为 6 passed；`git diff --check` 通过。requests/urllib3 的本机版本 warning 不影响任一测试结果。
- 新增 versioned 中文报告：`docs/releases/flowise-3.1.3-repository-v1-freeze-candidate-20260916.md`，记录 exact snapshot、全部冻结 digest、count/region/invariant、validation coverage、residual leakage、风险与 test-result digest `73b4a87849aba06a3739c91ee60a19ce24f45267339deca676363e9d09ba4178`。

### 结论与 blocker

- 完整性、泄漏、evaluator、finding intake、repository smoke、harness 和 S/P/B/T mock smoke 均通过；没有运行 live S/P/B/T/M、treatment comparison 或 condition-informed GT calibration。
- **最终 freeze 不通过/保持 blocked**：五个 B root 的 local validator 需要 snapshot-matched、离线的 Node 24 dependency materialization；当前 target 无 `node_modules` 且本机 Node 22 不能替代。该问题已在 private verification metadata、freeze-candidate report 与本 ledger 记录。它不撤销静态 A/B evidence 或改变 TP semantics，但按 Phase 4/6 build gate 尚未闭合。
- `live_gate: blocked` 继续有效，直至该 blocker 被解决、全部 digest 和回归重新生成，并由用户明确批准 live execution。
