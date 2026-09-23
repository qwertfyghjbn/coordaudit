# repository-v1.1 / evaluator-v2 final-freeze handoff（待激活）

状态：**freeze gate 未通过，非正式实验授权**。本文件记录拟冻结身份与新实验合同规则，但不宣称 `EVALUATOR_V2_FROZEN=yes`，也不开放新的 S/P/B/T/M formal block。

## 冻结身份核验

| 项目 | 当前身份 / SHA-256 |
|---|---|
| case / evaluator generation | `flowise_3_1_3_repository_v1_1` / `repository_v1_1` |
| evaluator-v2 source | `experiments/emergent_coordination/evaluator/repository_v1_1_score.py` — `4eba861ac4b37102ac514a7197f1bcc8f8e22bb730c724ea9df269a3c79d5817` |
| repository-v1.1 GT | `experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1_1/ground_truth.json` — `4e41103ecbe6d96cb0bbe3cc54c0c4a574ac21d7825bc2adc36c723ee5978da8` |
| v1.1 case/evaluator config candidate | `experiments/emergent_coordination/manifests/flowise_3_1_3_repository_v1_1.json` — `bfaab255256ae63fcd9c307d69b504b160455f64f3c47461f639c31f4540b6f9` |
| threat-model rules TM4/TM6/CR1 | `docs/adr/0007-repository-v1.1-gt-admission-rules.md` — `9f27d1c7e856d7a3929ca4beb8f22472086d8485f814863852ee3528c77a9303` |
| equivalent-anchor rule payload | 30 roots 的 `semantic_invariant_v1_1`、approved equivalent/primary 锚按 root 顺序取出，以 UTF-8、`ensure_ascii=false`、sort keys、紧凑 JSON 编码后 SHA-256：`f3e4adf329cc353cde10a2bbd3a78572181818fa7582e48d9beef5fb91f519df`；共 12 个批准等价锚 |
| evaluator-v1 source（回归基线） | `experiments/emergent_coordination/evaluator/repository_v1_score.py` — `942a6219bcbc1c158714372f3dc523c6749c30a542135d044621d7c9bd96c05c` |
| retrospective manifest | `artifacts/retrospective/flowise_repository_v1_1_evaluator_v2_20260921/manifest.json` — `0ddedba014df9b0e6efdebb4215dbb5e7698ab0ed50cc40c3a6cc6eaa82df430` |

**尚未形成独立可冻结 evaluator config / scoring schema / novel adjudication schema artifact。** 当前约束分别分布在 case manifest、GT 与 evaluator-v2 源码中；源码的 SHA-256 可钉住当前实现，但不能把尚未批准、尚未提交的分散配置称为 final frozen evaluator version。将来正式冻结须物化并版本化这些 schema/config，钉住其摘要，确认 runtime 校验，并在内容变化后重新运行 regression 和 retrospective hash 核验。

## 正式实验合同（待生效）

未来**新**的 matched block 应显式绑定 `case=flowise_3_1_3_repository_v1_1`、`evaluator_generation=repository_v1_1`、固定 GT SHA-256 和 30-root denominator。单一 block 的所有 condition 必须使用同一 evaluator generation；block manifest 与每个 run/result artifact 均记录该 generation。旧 repository-v1 blocks 保持原 evaluator-v1 generation、原 preregistered score 与原 block identity；不得把 v2 retrospective 分数回写。

正式输出分成两视图：canonical benchmark 对冻结 30 roots 计 root-level TP/FN 和 recall；`canonical_tp` 是冻结 canonical / accepted primary 锚满足类别、guard、对象、推理约束，`equivalent_tp` 还须命中批准等价锚及相同 semantic invariant。每 root 每 run 最多计一次；重复 fingerprint/root 只保留 provenance。GT 外的 `validated_novel_tp` 须有 condition-blind、独立代码级 source→sink/guard 证据，且只在 novel view；`false_positive`、`inconclusive`、`unmatched_unreviewed` 各自分流。`gt_overlap_uncredited` 指已裁决关联 GT 但提交证据未满足 formal 匹配，不计 TP，也不伪装成 novel。semantic judge 当前关闭；未来如启用，仅处理 deterministic unmatched，保留输入、输出及 provenance，不能直接授予 formal TP 或写当前 GT。

当前 block 中新 candidate **不得**动态改变 GT/denominator。通过后只能进入未来的 versioned GT/evaluator generation，重新审定 threat-model、批准锚、snapshot applicability、source/sink/guard，赋予新 case/evaluator ID 与哈希，重跑完整 regression，随后才可用于新的 matched block。每条 verification、adjudication 和 agent-run-derived provenance 必须保留。

## 历史比较与 circularity

允许并列展示同一历史 run 的原 v1 score 与独立 retrospective v2 score，附原产物引用、两个 generation、各自分母与 GT hash，仅作描述性 transition。不可直接比较跨 generation 的 recall、TP 总量、precision、topology 排序或所谓“独立泛化提升”。九个 R21–R29 root 来自历史 run；任何参与 GT/等价锚发现的 run 必须标记 circularity，其 retrospective TP 不构成 independent benchmark generalization evidence。新的独立泛化判断只可来自 GT/evaluator 正式冻结后、未参与构造的全新预注册 matched blocks。

## 已验证事项与剩余 gate

`python3 scripts/verify_flowise_3_1_3_repository_v1_1_gt.py`：453 checks、`failures=[]`、30 roots、但 `git_clean=false`、`gt_freeze_complete=false`。相关 evaluator/harness/repository tests：81 passed；retrospective 全量 verify：72 文件及原始输入哈希一致。evaluator-v1 source 与旧 v1 GT 的 `git diff --exit-code` 为 0；原 run/evaluation/block identity 未被重评程序修改。

必须先关闭以下 gate 才能把本 handoff 改为 official/active：

1. GT 文件仍写 `freeze_status=pending_git_clean_and_validation`、version 为 freeze-candidate；case manifest 的 version/activation status 仍为候选，`live_gate=blocked`。GT freeze-gates 文档明确 `GT_FREEZE_COMPLETE=no`。不得只改文字或忽略哈希连锁来宣称 GT 已冻结。
2. 全局工作树存在大量此前及并行的用户改动；不得为满足 git clean 而重置、覆盖或擅自提交无关工作。evaluator-v2 源码、测试和 retrospective 产物当前也未纳入可审计的 final commit/tag。
3. `harness/contract.py` 的 formal contract families 只预注册 repository-v1；v1.1 仍不能冻结新的正式 matched block。必须新建 versioned v1.1 contract，并在 GT gate 关闭、config/schema 身份固定且回归通过后才开放 live gate。

`EVALUATOR_V2_FROZEN = no`。本文件是待激活交接，不是正式运行许可。
