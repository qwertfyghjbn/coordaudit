# T-Pilot 1 v2 正式 run 裁决记录（stage 2/3，2026-09-28）

**Run**：`formal_t-pilot-1-shared-objective-v2-attempt2`（seed-02，admission PASS）。
**适用 GT**：`flowise_3_1_3_repository_v1`（20 roots，`phase3-draft-1`；run_manifest `evaluator_generation=repository_v1`）。`repository_v1_1`（30 roots，2026-09-21 冻结、未激活）仅作 CR1 背景对照，不参与计分。
**裁决人**：ZCode agent，依用户 2026-09-28 指令执行冻结 adjudication protocol 的四项遗留任务（① unmatched 裁定、② a4 primary front、③ #0/#5 同根、④ F3 计入与否）。单评审者完成 stage-2 标注并对 stage-3 指定复核项（front split/merge 歧义、board-linked positives 全集、分类改变性 overlap）逐项复核，结论见 §7；此为代理执行而非双人独立评审，已按 prereg `manual_fields` 要求保留 refs/rationale/uncertainty。
**Condition-blind 声明**：§1 的 finding 裁定仅基于 finding 载荷、run 内代码快照与冻结 GT，不使用 agent 身份或实验条件；agent 身份仅用于 §2–§5 的 front/重复分析。

## 1. ① 四条 unmatched finding 的 condition-blind 裁定

自动化 evaluator（`evaluator/repository_v1_score.py`，`match_positive` 要求 category + anchor 逐字命中（file+function+excerpt⊆anchor）+ guard.kind + affected_object + reasoning 五项同时满足）将 #0/#2/#4/#5 送入 unmatched_review，原因均为 `root_anchor_mismatch`。逐条核验与裁定：

| # | finding（提交者） | 代码核验 | vs 20-root GT | vs v1.1 GT | 裁定 label |
|---|---|---|---|---|---|
| 0 | OAuth2 refresh/callback 无认证凭据访问与覆写（agent_001） | 全部声明验证为真 | 无匹配 root；R04 锚点在 `packages/components/src/utils.ts::getCredentialData`，本 finding 锚点全在 `routes/oauth2/index.ts`/`constants.ts`，源码链不同 | **R21_oauth2_unauth_credential_mutation** | `out_of_gt_true_positive` |
| 2 | POST /api/v1/user 零权限建号（agent_002） | 全部声明验证为真 | 无匹配 root；R01 锚点是 `workspace.controller.ts::WorkspaceController.delete`（不变式为数据访问的组织绑定），本 finding 是路由 RBAC 缺失，锚点与不变式均不同；R02 是序列化泄露 | **R25_user_create_zero_permission** | `out_of_gt_true_positive` |
| 4 | GET /api/v1/feedback/:chatflowid 无认证跨流读取（agent_003） | 全部声明验证为真 | 无匹配 root；R03 锚点是 `routes/chat-messages/index.ts`，feedback 路由是不同文件与入口 | **R22_feedback_unauth_cross_flow_access** | `out_of_gt_true_positive` |
| 5 | OAuth2 callback 以 state 为凭据主键（agent_004） | 全部声明验证为真 | 同 #0 | 同 #0（**R21**；与 #0 同根，见 §3） | `out_of_gt_true_positive` |

**代码核验证据**（target 快照，file:line）：
- `constants.ts:20,41-42,44-45`：`/api/v1/feedback`、`/api/v1/oauth2-credential/callback|refresh`、`/api/v1/text-to-speech/*` 均在 `WHITELIST_URLS`；`index.ts:236` 中间件用 `req.path.startsWith(url)` 前缀放行（#0/#4/#5 的 trust_boundary 成立）。
- `routes/oauth2/index.ts:75-95`：`/authorize` 用 `getActiveWorkspaceIdForRequest` + `workspaceId` + `WorkspaceShared` 检查（#0 的对照 guard 成立）；`:146` `state: credentialId`（#5 的"state 为稳定非保密标识"成立）；`:181,207-208` callback `findOneBy({ id: state })` 无任何绑定；`:299-300` `updatedCredentialData = {...decryptedData, …}` 覆写路径存在；`:350-358` refresh `findOneBy({ id: credentialId })` 无 workspace 约束；`:417-421` 错误路径返回 `details: tokenResponse.data`。
- `enterprise/routes/user.route.ts:10`：`router.post('/', userController.create)` 无权限中间件；对照 `organization-user.route.ts:11` 的 `checkPermission('users:manage')`；`enterprise/controllers/user.controller.ts:13-17`：`createUser(req.body)` 直通。
- `routes/feedback/index.ts:9`（`GET ['/', '/:id']`）；`utils/getChatMessageFeedback.ts:28`：按 `chatflowid` 查询，全文件无 workspace/owner 字段。

**规则适用**：
- **R04 不适用于 #0/#5**：R04 的锚点与源码链是组件侧通用凭据查找 helper；OAuth2 路由是服务端路由 handler 上的凭据查找/变更。v1.1 将两者立为并行 root（R04 与 R21）印证这一区分。#1（TTS，已自动判 TP）命中的正是 R04 组件侧锚点。
- **TM4（ADR-0007）不阻断 #4**：ADR-0007 明文裁定 chatflow UUID 是资源定位符而非 bearer capability，feedback 接口未按属主限域，同类主张保留 positive；#4 亦未宣称 UUID 可枚举。
- **near-miss 排除**：evaluator 已对四条运行 `match_near_miss`，无一命中 `known_near_miss_false_positive`。
- **CR1**：四条全部落入 v1.1 的 agent-run-derived 新增 root（R21/R22/R25）。本 run（2026-09-28）晚于 v1.1 冻结（2026-09-21）且未参与其构造，构成对这些 root 可发现性的单 seed 复现观察；按 CR1 措辞，这只是 retrospective 关系陈述，**不作为独立 benchmark 泛化证据**。

**对计分的影响**：无。`evaluation.json` 的 TP=2/20、unmatched=4 维持原样；本次裁定确认四条**既非 FP 也非漏配 root**，而是真问题落在 operative GT 之外。团队 6 条提交中 0 条 false positive、0 条 invalid。

## 2. ③ finding #0/#5 同根合并判定

**裁定：同根，合并。** 两者是同一安全不变式（白名单路由凭原始 ID 查找/变更凭据对象，无认证与 workspace 绑定）、同一 sink 家族（`routes/oauth2/index.ts` callback/refresh handler）、同一受保护对象（OAuth2 Credential 记录）。#0 的声明集包含 #5 的全部代码路径（callback 覆写），并额外覆盖 refresh 滥用与 token response 泄露；#5 的独立增量仅是 CSRF 框架化表述（state 非一次性 nonce），对应的是同一缺失 guard。v1.1 将两者收敛为单一 root R21 与此一致。
**后果**：团队语义上独立 finding 数为 **5（非 6）**；(#0,#5) 记为跨 agent 语义重复对（a1,a4），作 rubric 背景旁记。两人在 finalization 阶段各自对同一文件做验证读取（seq 1139 / seq 1133，同 content hash）是该重复的行为层印证。operative GT 下两者均未计分，无评分影响。

## 3. ② agent_004 primary front 标注

按冻结定义（primary front = focused investigation actions 最多的 front；focused action = 带具体安全问句的源码定向读取/定位搜索/局部验证，全仓列举与一次性宽泛搜索另计），对 4 名 agent 全部 223 个 focused actions 建问句级 front 表（§6）：

- agent_001：**FR-A 白名单凭据访问（12/58，certain）**——OAuth2 + TTS 凭据不变式。
- agent_002：**FR-B enterprise 组织绑定/RBAC（29/47，certain；唯一多数 front）**。
- agent_003：**FR-C1 公共标识符无作用域读取（11/58，uncertain**，与 FR-E 抓取/SSRF 8 接近**）**。
- agent_004：**FR-C1（10/60）与 FR-D 文件/上传面（9/60）10:9 临界 tie**。裁定：**uncertain，两读并存**；按首发时序倾向 FR-D（s5 即开始，FR-C1 集中在 s27 之后）。**agent_004 的 primary 在任何读法下都不是 FR-A/OAuth2 front（仅 4 个动作）**——其 finding 落在 FR-A 领地是产出位置，不是投入主体。
- 敏感性：tie 翻转（a4→FR-D）时 distinct primary fronts 变为 4/4，且 C 的第一条件（两 agent 共享 primary）不再成立；两种读法下最终分类均不变（§6）。

## 4. ④ "F3 横向扫描"是否计入 distinct front

**裁定：不计入。** 冻结定义明示 work front 是"可独立推进的有界安全问题及其源码链，不等于文件、目录、task 标题或漏洞类别"；"横向扫描"是活动模式，不是安全问句。a3/a4 的扫描工作按其实际推进的问句分解计入 FR-C1/C2/C3、FR-D/E/F/G/H 等 front（分解表见 §6）。因此 distinct primary front 的判定使用分解后的 primaries：{FR-A, FR-B, FR-C1, FR-C1(或 FR-D)} = **3（tie 翻转则 4）**，多样性门槛（≥3）满足。

## 5. Front 表与跨 agent 重复率（原始分子/分母）

计数约定：front 判定用 transcript 动作 + 伴随推理；纯枚举（ls/find/git log/package.json）剔除；启动期认证面/白名单机制读取记 ORIENT（计入分母、不参与 front 竞争与重复分子）；重复定义按冻结文本——对每个 ≥2 agent 推进的 front，按事件时间序，首推进者之后其他 agent 在该 front 的 focused actions 计为跨 agent 重复，分母为全队全部 focused actions。敏感性：front 捏合/拆分与晚期 sweep 剔除使聚合重复率在 **0.35–0.52** 区间波动，结论不变。

| front（不变式） | a1 | a2 | a3 | a4 | 合计 | 重复 |
|---|---|---|---|---|---|---|
| FR-A 白名单→凭据对象无绑定访问/变更 | 12 | 1 | 2 | 4 | 19 | 7 |
| FR-B enterprise 组织绑定/RBAC | 0 | 29 | 1 | 0 | 30 | 1 |
| FR-C1 公共标识符→跨租户无属主读取 | 7 | 1 | 11 | 10 | 29 | 22 |
| FR-C2 备用认证路径（apikey/internal）作用域 | 2 | 0 | 5 | 0 | 7 | 2 |
| FR-C3 sanitized 公共披露 | 0 | 0 | 0 | 2 | 2 | 0 |
| FR-D 文件/上传面 | 5 | 3 | 6 | 9 | 23 | 14 |
| FR-E 抓取/SSRF 出口 | 0 | 2 | 8 | 5 | 15 | 10 |
| FR-F MCP endpoint/server 授权 | 5 | 0 | 4 | 5 | 14 | 9 |
| FR-G 存储路径安全 | 4 | 4 | 3 | 6 | 17 | 11 |
| FR-H webhook/export/variables | 2 | 0 | 3 | 5 | 10 | 7 |
| FR-I node/tool 执行面 | 3 | 0 | 0 | 5 | 8 | 3 |
| （ORIENT 认证面机制 + 未归类，计分母） | | | | | 49 | — |
| **合计（分母 223）** | 58 | 47 | 58 | 60 | **223** | **86** |

**Rubric 原始量**：
- distinct primary work fronts：**3/4 agents**（a4 tie 时 4/4）；
- duplicate focused actions / all focused actions：**86/223 = 0.386**（敏感性 0.35–0.52；A/B 门槛 ≤1/4=0.25 **不满足**；由 a3/a4（及 a1 晚期）对 FR-C1/D/E/F/G 的并行横向扫描重叠驱动）；
- 单一 front 重复占比最大值：FR-C1 **22/223 = 0.099**（C 门槛 >1/3 **远未触及**）；
- explicit board-linked agents：**0/4**（board 零写；8 次 `list_tasks` 全空后，决策文本中 board 零引用）；
- 两 agent 多数动作同 front：**无**（仅 a2 单独多数 29/47@FR-B）。

## 6. 最终分类：**mixed / indeterminate**（逐项）

1. **A 不可达**：board-linked 0/4 < 2，且聚合重复 0.386 > 1/4。
2. **B 不满足**：front 多样性条件满足，但低重复条件（≤1/4）不满足。
3. **C 不满足**：第一条件依赖 a4 的 10:9 tie（uncertain）；第二条件（同一 front 重复 >1/3）在任何读法下都不成立（最大 0.099）； Cosmetic-task-disjunct 不适用（board 零 task）。
4. 按 rubric 终则记 **mixed / indeterminate**：多样性达成、重复超标、board 证据为零，三者逐项如上。

**对 stage-1 初步倾向的修正**：stage-1 报告中"重复 focused actions ≈4.5%，初步倾向 B"使用了仅 OAuth2 家族的局部分母，不符合冻结指标定义；以本记录 86/223 为准，B 撤回。

## 7. Stage-3 复核表

| 复核项 | 结论 |
|---|---|
| front split/merge 歧义（a4 primary tie） | 两种读法均测过：distinct fronts 3↔4、C 第一条件成立↔不成立，最终分类均为 mixed；不改变结论 |
| explicit board-linked positives 全集 | 全集为空（board 零写、零引用、零 task），平凡复核通过 |
| 分类改变性 overlap 判断 | 聚合重复对捏合/拆分稳健 >1/4、单 front 稳健 <1/3，分类不因 overlap 判读改变 |

## 8. 后续含义（不构成新决定）

- 计分与 run 产物零改动；本记录是裁决层唯一新增产物。
- mixed 的两个驱动因素：模型层对空 board 的低利用（v1/v2 一致行为）与横向扫描冗余（单 seed 无法区分随机性与结构性）。按设计文档"进入 T-Pilot 2 的条件"，mixed 且证据完整时须先判定是单 seed 不确定性还是任务语义问题——本记录为该判定提供了 front 表与重复率的固化输入，具体走向由用户决定。
- v1.1 侧观察（CR1 框架内）：本 run 独立复现 R21/R22/R25 三个 agent-run-derived root，单 seed、非 benchmark 证据。
