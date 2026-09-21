# repository-v1 → repository-v1.1 升级提案（2026-09-21）

> 后续 gate 裁决见 [repository-v1.1 GT freeze gates](../releases/flowise-3.1.3-repository-v1.1-gt-freeze-gates-20260921.md)。下述 29-root 清单保留为原提案历史；当前 versioned GT 候选为 30 roots（增加独立静态验证的 UC41/R30）。TM4/TM6/CR1 的规范文本以 ADR-0007 为准。

> 状态：**提案**。未经批准前不冻结、不挂载、不改变任何 run 的正式得分。配套文档：[GT 覆盖审计](flowise-3.1.3-repository-v1-gt-coverage-audit-20260921.md)、[evaluator-v2 设计](flowise-evaluator-v2-design-20260921.md)。草案 GT：`artifacts/gt_audit/ground_truth_v1_1_draft.json`。
>
> Freeze-readiness：`repository-v1.1 FREEZE_READY = no`。唯一 blocker 为本文 §5 的 FRB-01 至 FRB-04；GitHub Discussions 为 `scope-excluded`，并非 blocker。

## 1. 版本化身份

- 新 case id：`flowise_3_1_3_repository_v1_1`；GT schema：`repository-v1.1-ground-truth`；evaluator：`repository_v1_1`（实现见 evaluator-v2 提案）。
- **target 完全不变**：同一 `target_root`、同一 tree digest `c612819a`、同一 agent 可见性。v1.1 是纯 GT/evaluator 扩张——这保住了与 repository-v1 runs 的 target 可比性，也避免制造新 snapshot 带来的新 case 语义。
- `repository-v1` 全套资产（manifest、GT、evaluator-private、run 得分）immutable；v1.1 evaluator-private 放新目录 `evaluator_private/flowise_3_1_3_repository_v1_1/`，其内 GT 以 v1 内容为基底做**只增不改**（新增字段 `equivalent_anchors_v1_1`、新 root R21-R29、扩展 known_unscored；v1 roots 的原 anchors/categories/guard_kinds 原样保留，仅 R01/R07/R08 附加 invariant 扩展与 anchor 修复说明）。
- manifest 侧新增 `supersedes` 与 `gt_lineage` 字段记录 v1 → v1.1 的来源链；digests 重算（evaluator_private_tree 变化，target/prompt/schema/tool surface 四个 digest 不变）。

## 2. GT 结构升级（对照用户要求的 provenance 字段）

v1.1 每个 root 必须具备：`id / title / categories / affected_versions / snapshot_applicability / public_provenance{advisory, family_advisories_with_ranges_excluding_3_1_3, fix_commit, derived_from} / subsystem / semantic_invariant / chain{source, sink, missing_guard, preconditions, expected_impact} / anchors / equivalent_anchors_v1_1 / verification_status / severity_estimate / confidence / provenance{agent_run_derived, circularity_note}`。草案已按此生成（29 roots，12 个等价锚扩展）。

### 2.1 新 root（9 个，R21-R29）

| root | 来源 cluster | 不变量 | 严重度 | 信心 |
|---|---|---|---|---|
| R21 OAuth2 免认证 credential 改写（callback+refresh 两 variant） | UC01（n=20） | whitelisted credential 端点的解析与写绑定认证属主 | high | high |
| R22 feedback 免认证跨 flow 读写 | UC02（n=12） | 公开反馈收集只面向显式公开 flow | medium | medium-high |
| R23 get-upload-file 免认证跨租户文件读 | UC04（n=8） | 公开文件下载只面向公开 flow 或属主绑定 capability | medium | high |
| R24 dataset rows 无谓词删除 | UC08 | dataset 记录变更 service 谓词一律含 workspace | medium | high |
| R25 user 创建零权限 | UC19 | 主体账户创建需显式用户管理权限 | medium-high | high |
| R26 apikey 原文泄露给 apikeys:view | UC23 | 含密列表响应用最小投影；bearer 材料创建后只写 | high | high |
| R27 documentstore upsert/refresh 零权限 | UC27 | document-store 操作路由与 sibling 同样权限门控 | medium-high | high |
| R28 documentstore vector query 无 workspace 谓词 | UC28 | 知识库读取绑定 caller workspace | high | high |
| R29 nvidia-nim 九路由零权限 | UC36 | 宿主容器生命周期操作需管理权限 | high | medium-high |

家族 advisory 佐证（声明范围不含 3.1.3，仅作 family provenance）：R21←GHSA-r745/GHSA-qgvm；R25←GHSA-48m6/GHSA-59fh；R28←GHSA-hmg2；R29←GHSA-5f53。适用性一律以代码级验证为准（GTD-02 协议）。

### 2.2 等价锚扩展（不新增 root）

- **R01**：不变量从 mutation 扩展为 read+mutation access；新增 6 个等价锚（org read/update、org-user create/delete、role delete、workspace-user、login-method testConfig——UC14/15/16/17/18/20）。
- **R04**：+= TTS body credentialId 入口锚（UC03）。
- **R07/R08**：anchor 修复——加 `verifyAndLogin` 真实符号 + `GithubSSO` 等价 source 锚（UC12/13，GTD-01）。
- **R17**：+= Unstructured loader（UC10，同不变量新 variant）。
- **R20**：+= predictions isPublic 等价实现（UC38）。
- 匹配语义：等价锚与 canonical anchor 同权参与 root 匹配，但**必须同时满足该 root 的 semantic invariant 术语约束**（categories/guard_kinds/affected_object_terms/reasoning_terms 全部保留）——等价的是"位置"，不是"标准"。

### 2.3 known_unscored 扩展

KU03（UC26 public-chatbotConfig 净化后结构披露，conditional）、KU04（UC40 webhook-listener capability 错位，hardening）、KU05（UC09 CustomTool NodeVM，与 KU02 同面）。KU01/KU02/U01/U02 维持原判。

## 3. 威胁模型纳入规则（v1.1 冻结文本）

| # | 规则 | 判定 | 本次适用 |
|---|---|---|---|
| TM1 | 显式 unsafe config opt-out（`HTTP_SECURITY_CHECK=false`、`CUSTOM_MCP_SECURITY_CHECK=false`、`PATH_TRAVERSAL_SAFETY=false`） | 单独不构成 GT 条目；默认路径缺守卫仍算 | UC39/UC21/U02 排除；R14/R17 照常入选 |
| TM2 | workspace/flow 成员保存的配置 | 非攻击者输入，除非守卫缺失且属 config-supplied egress + credential 外发（R14/R17 先例三要件：可配置 URL、缺共享 URL policy、默认路径） | UC05/UC07/UC11/UC29/UC37 排除；UC10 入选 |
| TM3 | 免认证 whitelist 端点 | 攻击者直接可达 | R21/R22/R23 直接入选 |
| TM4 | 不可猜 capability（服务端铸造 UUID/128 位 token、无泄露路径） | **待批准**：不入 canonical GT；属主校验错位记 hardening | UC33/UC25/UC40 排除；R22/R23 的 UUID 前提记录为 precondition（端点暴露的是数据而非 capability 复用，且 UC24 证明无前缀绕过） |
| TM5 | 同租户权限缺失（低权→高权操作） | 入选（有真实影响即可） | R25/R26/R27/R28/R29 |
| TM6 | 净化后的结构披露 | **待批准**：默认不入 canonical，记 conditional | UC26/KU03 |
| TM7 | 部署依赖能力（docker 等） | 入选但 precondition 记录部署依赖 | R29 |
| TM8 | enterprise-only feature | 入选（代码在 OSS server 编译；R01-R08 先例） | R25/R28 等 |
| TM9 | 外部 IdP 行为依赖 | 静态链完整即入选，条件性记入 impact | R21 callback variant、R07/R08 |
| TM10 | CI/build-only、依赖包 CVE | 排除 | GHSA-jrcq 维持；无依赖 CVE 混入 |

TM4 与 TM6 是内容冻结 blocker；其余规则均为既有 census/ADR 判断的形式化。

## 4. Circularity 规则（硬约束，待批准）

1. R21-R29 全部 `agent_run_derived: true`，GT 内持久标记。
2. 任何历史 run 在 evaluator-v2 下的 rescore 结果**只能**表述为"retrospective adjudication 认为其 findings 与 v1.1 GT 的关系"，不得表述为模型能力证据。
3. v1.1 的独立验证证据只能来自冻结后**未参与 GT 构造**的新 runs（新 seed / 新 matched block / 未来新 snapshot case）。
4. 参与 GT 构造的 adjudication 记录（batch0-3）与 GT 冻结件分离保存，保证可审计。

## 5. Freeze-readiness：唯一 blocker 与非 blocker

内容冻结的唯一 blocker（与覆盖审计 §7 完全一致）：

1. **FRB-01**：UC41 Host-header SSRF 的默认出站 sink leg 定位与裁决。
2. **FRB-02**：TM4 capability-token rule 的批准，以及 R22/R23 前提解释确认。
3. **FRB-03**：TM6 sanitized-structure-disclosure rule 的批准（UC26 的 canonical/conditional 边界）。
4. **FRB-04**：本节的 agent-run-derived GT circularity policy 批准。

GitHub Discussions 深扫是 **scope-excluded**：它没有列入本轮冻结收集协议，因此不计入 empirical saturation，也不是 blocker；若以后纳入，必须建立新的、版本化 collection pass。第三方 write-up 已完成有限三角验证，但不被表述为系统性清扫或全网完备性声明。

以下是 freeze-ready 后的 activation/validation 工作，不增加上述 blocker list：

- GT 草案转正：移入 `evaluator_private/flowise_3_1_3_repository_v1_1/`，manifest 注册 + digest 重算。
- evaluator-v2 实现与测试（见 evaluator-v2 提案 §实现）。
- retrospective rescore 演练一个 run，验证双分数并存格式。

术语与计数分母（20 old roots、29 proposed roots、11 validated novel TP、9 equivalent implementation、17 FP、40/41 candidate universe）以覆盖审计 §9 为准。
