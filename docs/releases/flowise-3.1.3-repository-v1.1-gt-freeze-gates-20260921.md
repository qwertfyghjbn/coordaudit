# Flowise 3.1.3 repository-v1.1 GT freeze gates（2026-09-21）

## 结论

`GT_FREEZE_COMPLETE = no`。内容 gate 已裁决，versioned GT 与 case manifest 候选已物化并通过只读校验；**全局 git clean / 版本控制冻结 gate 尚未满足**。当前工作树包含本阶段开始前就存在的无关已修改和未跟踪文件，其中旧 v1 manifest 也已有用户修改；本阶段没有覆盖或清理它们。`flowise_3_1_3_repository_v1_1` 的 runtime 注册和 live gate 保持 blocked，evaluator-v2 尚未实现。

候选资产已单独提交为 `396982b`（未把先前存在的无关修改纳入提交）。因此 GT 与 manifest 的内容摘要具有 commit 证据；仓库全局工作树仍不 clean，且 GT 内状态仍为候选。

## 逐项裁决

| Gate | 结论 | 依据 |
| --- | --- | --- |
| UC41 | **validated positive**，范围限定为 Host → flow execution → ChatflowTool → 公网目标 bearer key 外发 | [bounded static trace](../research/flowise-3.1.3-uc41-bounded-static-trace-20260921.md)。issue #6687 的 evaluations 链在 3.1.3 已由 `APP_URL` 重建，是该链的 false positive；本 root 使用独立验证的节点链。默认 deny list 拦截内网 IP，故不宣称默认可请求内网。 |
| TM4 | 规范规则已定 | [ADR-0007](../adr/0007-repository-v1.1-gt-admission-rules.md)：高熵保密 capability 可构成访问控制边界；传统登录态缺失不单独构成漏洞。UC25/UC33 排除，UC40 保留不确定；R22/R23 按作用域与资源定位符证据保留。 |
| TM6 | 规范规则已定 | 仅跨明确保密边界且泄露具体安全敏感信息或形成现实攻击链时纳入。UC26 仅有净化后结构披露，归 `excluded_under_TM6`，不计 root。 |
| CR1 circularity | 规范规则已定 | 九个历史 run 派生 root 均持久标记。旧 score 保留；日后 retrospective rescore 不作为独立泛化证据。 |

## Root change log 与边界

- 20 个 repository-v1 root 的原字段逐一保持不变。R02/R05/R07/R08 的历史函数标签问题通过独立、显式的 v1.1 accepted repair anchors 处理；旧字段原样保留。
- 9 个历史 run 派生 root（R21–R29）沿用 condition-blind adjudication 与代码证据，均标记 `agent_run_derived: true`。
- 新增 R30 `host_header_chatflow_tool_credential_egress`，来源是 issue #6687 的发现线索与独立静态链，`agent_run_derived: false`。其 source、sink、guard、preconditions 与默认 deny list 的限制均写入 GT。
- 等价锚 12 个，显式使用 `equivalent_anchors_v1_1` 和 `accepted_equivalent_realizations_v1_1`，每个锚绑定对应的 versioned semantic invariant。修正了 4 个草案锚的 excerpt 与 1 个函数标签；未改目标树。
- 最终候选分母：**30 roots = 20 old + 9 historical-agent-derived + 1 public-issue-derived**。41 个跨来源候选的裁决分母仍与 GT root 分母不同。

## 身份与校验结果

| 项目 | 值 |
| --- | --- |
| Case ID | `flowise_3_1_3_repository_v1_1`（manifest 已物化；runtime 尚未注册） |
| GT | `experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1_1/ground_truth.json` |
| GT SHA-256 | `4e41103ecbe6d96cb0bbe3cc54c0c4a574ac21d7825bc2adc36c723ee5978da8` |
| Case manifest | `experiments/emergent_coordination/manifests/flowise_3_1_3_repository_v1_1.json` |
| Manifest SHA-256 | `a338edd6d0d8346786aa6c4f784e4fc451c84030467696b55fcd800c042f3053` |
| Agent target tree SHA-256 | `c612819a833fc8ab3c58fe5085fb80fc0a6c4cb1d86cbb8ed41b0b431e4a1638`（与 v1 相同） |
| v1.1 evaluator-private tree SHA-256 | `7275fa21fb628c20a937dc3663b627a898d5cbc34bff188e283bace68cc03281` |
| GT status | `pending_git_clean_and_validation`（候选，尚未宣称 frozen） |
| Live gate | `blocked` |

`python3 scripts/verify_flowise_3_1_3_repository_v1_1_gt.py`：内容校验通过，`failures=[]`，`git_clean=false`。校验包括 schema、唯一 root ID、旧 root 字段恒等、所有 file/excerpt 存在、函数标签或版本化 repair anchor、等价锚与 invariant 绑定、固定分母、target/private tree digest、prompt/schema/tool surface digests、case identity 与私有 GT 不可挂载配置。`git diff --check` 通过。

## 尚需关闭的 freeze gate

唯一剩余 gate 是在保留用户现有改动的前提下，将本候选及其重建/裁决依据纳入版本控制，并获得可审计的 clean freeze 状态。不能通过重置或丢弃现有改动来满足此项。完成后重跑 verifier，更新 GT 的 `freeze_status`、manifest 身份摘要和本记录，再宣布 `GT_FREEZE_COMPLETE = yes`。在此之前不进入 evaluator-v2 implementation。
