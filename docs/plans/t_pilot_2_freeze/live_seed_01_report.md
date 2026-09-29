# T-Pilot 2 单 seed 正式实验报告（2026-09-28）

**结果：`mechanism_pass_useful`（单 seed、代码级 primary adjudication）。** C_raw 有 3 条候选、2 个语义根；C_final 有 2 条、2 个语义根。finalizer 正确合并了 OAuth2 callback 的同根两条，保留了独立的 TTS 根。最终文本仍有两处限定问题，见下文；本结果不声称一般化效果或统计显著性。

## 合同与运行身份

- 唯一 seed：`t-pilot-2-final-synthesis-seed-01`；run ID：`formal_t-pilot-2-final-synthesis-v1`。[run 目录](../../../experiments/emergent_coordination/runs/t-pilot-2-final-synthesis-v1-192p/formal_t-pilot-2-final-synthesis-v1/)默认不提交；无追加 seed。
- [最终 prereg](final_prereg_v1.json) SHA-256 `e1abf3cc6d34098db3dbf70a72afc48e3d6a13102a2db088ee2c476be4836cd5`；[block manifest](t_pilot_2_final_synthesis_v1/block_manifest.json) canonical hash `447e4d41a9e17aae5a7d7bcc89382a3930906d1770698969ab2fa9b7e7811a08`；runtime tree digest `710af3b6a8c6a1a6d216bc961b404526e8187c73acefea72b3d613aba57b64f4`，target tree digest `c612819a833fc8ab3c58fe5085fb80fc0a6c4cb1d86cbb8ed41b0b431e4a1638`。
- 模型：`deepseek-flash` / `openai_compatible`，thinking disabled，temperature 0，max output 4096。search prompt profile `repository_v1_t_pilot_1_shared_objective`；四个 agent 的首次 model request messages/tools 与 Pilot 1 冻结 packet 逐字一致，search tool schema hash `81707c840e64c97540da11f856ff1b7ca56b2c0b0d5ab073a44f0c4c52ac29d9`。[finalizer prompt packet](finalizer_prompt_packet_v1.json) SHA-256 `cb3246c7cc75cd6ab750e6520194e80ff2e80ccf0503b4a664626f93d9894390`。
- 团队预算 192 permits、search 截止 1140s、synthesis 预留 R=3 与 W=60s、read cap=1；总墙钟上限 1200s。总运行约 81.3s。

## Admission（先于效果判断）

| 检查 | 实测 |
| --- | --- |
| search team | 4/4 `submitted`，`clean_complete`；search 使用 168 permits，raw freeze 时余 24。 |
| 冻结与可见性 | `team_completion` seq 1127 → `raw_candidate_set_frozen` seq 1128 → `synthesis_input_model_visible` seq 1132 → `team_findings_submitted` seq 1146；首个 finalizer transcript 含冻结 model snapshot SHA-256 `8eaa59d57e18dba1311bbd2d7ca5228f619f82b0974de8ce0b6dff2f834fb2a6`。 |
| 来源与 decisions | 每条 final finding 有非空 `derived_from`；3 个 raw ID 各有一个显式 decision，merge 双向一致；无 accepted 新 finding。 |
| 预算与运行完整性 | 171/192 model calls，其中 finalizer 3/3 permits，1 次 read，0 provider failure，reconciliation `valid`（1147 events、562 transcripts、171 permits），run validity `valid`。 |
| 降级与 schema | 未降级。第二次 synthesis call 的 payload 因 `verification.status` 不合法被 intake 拒绝；错误回显后第三次 call 提交成功，实际走过预注册的 `read → invalid → submit` 路径。 |
| 双口径产物 | [C_raw](../../../experiments/emergent_coordination/runs/t-pilot-2-final-synthesis-v1-192p/formal_t-pilot-2-final-synthesis-v1/artifacts/raw_candidate_set.json)、[C_final](../../../experiments/emergent_coordination/runs/t-pilot-2-final-synthesis-v1-192p/formal_t-pilot-2-final-synthesis-v1/artifacts/team_final_findings.json)、[显式 raw disposition](../../../experiments/emergent_coordination/runs/t-pilot-2-final-synthesis-v1-192p/formal_t-pilot-2-final-synthesis-v1/artifacts/raw_disposition.json)、[Δ](../../../experiments/emergent_coordination/runs/t-pilot-2-final-synthesis-v1-192p/formal_t-pilot-2-final-synthesis-v1/synthesis_delta.json)俱全；`evaluation.json` 与 `evaluation_raw.json` 字节相同，manifest 明示 alias。 |

Admission **PASS**（[15 项机器检查](live_seed_01_admission.json)全部通过）。raw artifact SHA-256 `b563b692b191c4819c3ded308fbeaea155fa9660e430d2815d9fa5261e0e7fb2`；final artifact SHA-256 `00751ca8acd377cf1c63205dddf373df9b8b7274c84d1ee05c23dc7c6235161b`；run manifest SHA-256 `d018138ffb5c7b99b38157a9ca7b39d32ba4634cc7e24ae10c68b456c7b4d93a`。

## Stage 1：raw 与 final 独立代码级核验

原始 3 条及最终 2 条均未命中 operative repository-v1 的 20 个 GT root；两次 evaluator pass 的 GT TP 均为 0。**GT-unmatched 不等于 FP**。逐条核心 claim 的代码核验结果为 `novel_valid_gt_unmatched`，但两条 final 文本有下述限定。机器可读的逐条标签和 root 分组见 [adjudication JSON](live_seed_01_adjudication.json)。

1. **OAuth callback 根（raw_00/raw_02、final fin_00）**：`/api/v1/oauth2-credential/callback` 在 [WHITELIST_URLS](../../../experiments/emergent_coordination/repositories/flowise_3_1_3_repository_v1/packages/server/src/utils/constants.ts#L41)，[全局鉴权中间件](../../../experiments/emergent_coordination/repositories/flowise_3_1_3_repository_v1/packages/server/src/index.ts#L224)对它直接 `next()`；[callback](../../../experiments/emergent_coordination/repositories/flowise_3_1_3_repository_v1/packages/server/src/routes/oauth2/index.ts#L181)用请求的 `state` 按 `id` 单独找 credential，解密后使用 `clientSecret`，成功交换 code 才更新 credential。相邻的 `/authorize/:credentialId` 用 `workspaceId` 查找。因此缺少 tenant scoping 的核心 claim 成立。代码没有把 plaintext secret 回给请求者；token 覆写须有 provider 接受的 code。fin_00 的“read/abuse secret”仅可按**服务端代用**理解，不能读成直接泄露。
2. **TTS generate 根（raw_01、final fin_01）**：`/api/v1/text-to-speech/generate` 同样在 whitelist；[controller](../../../experiments/emergent_coordination/repositories/flowise_3_1_3_repository_v1/packages/server/src/controllers/text-to-speech/index.ts#L10)在无 chatflowId 时直接取 body 的 `credentialId`；[convertTextToSpeechStream](../../../experiments/emergent_coordination/repositories/flowise_3_1_3_repository_v1/packages/components/src/textToSpeech.ts#L33)调用 `getCredentialData`，[后者](../../../experiments/emergent_coordination/repositories/flowise_3_1_3_repository_v1/packages/components/src/utils.ts#L651)仅按 ID 查询并解密。由此可使用已知 ID 的其他 workspace 存储密钥。其附带的“`/voices` 也在同一 whitelist”说法不成立：[路由](../../../experiments/emergent_coordination/repositories/flowise_3_1_3_repository_v1/packages/server/src/routes/text-to-speech/index.ts#L9)确有 `/voices`，但 whitelist 没有该路径；该分支经过全局 API-key 鉴权。fin_01 原样保留了此不准确文字。

## Stage 2/3：来源解盲与转换判断

| raw | 显式动作 | final | 判读 |
| --- | --- | --- | --- |
| raw_00 | merge with raw_02 | fin_00 | 与 raw_02 同一缺少 workspace 约束的 callback、同一 credential 查询/写回路径、同一受保护对象。 |
| raw_01 | retain | fin_01 | TTS 路由、credential 使用 sink 与受保护密钥均不同；作为独立根保留。附带 `/voices` 文本错误未被修正。 |
| raw_02 | merge with raw_00 | fin_00 | 同上；合并后的条目覆盖两条 raw 的共同不变式。 |

**Δ_synthesis**：1 个 true duplicate merge group（2 条 raw → 1 条 final），0 false merge，0 valid-root drop，0 duplicate retained；2/2 valid unique roots 保留。没有单来源 correction 或 drop。finalizer 的成本为 3/192 permits（1.56%）、18,983 input tokens、4,348 output tokens、1 次 read。`evaluation_raw.json` unmatched=3，`evaluation_final.json` unmatched=2；这是待代码核验队列数的变化，不把它当作 FP 减少 1。

依据设计 §11，有真实同根机会且至少一次正确转换，因此结果标签为 **`mechanism_pass_useful`**。这个标签只表示本 seed 的机制成功和一次正确去重；fin_00 的 secret-reading 语义需收窄，fin_01 的 `/voices` 附带主张不准确，不能据此宣称最终文本所有字段均改善。

## 解释边界

本次是一次 T4 mechanism smoke，没有 S/P/B 或 M 的同步对照；不据此推断架构优劣或统计效果。真值核验是源码级，没有对目标运行真实 OAuth provider 或 TTS 服务。primary reviewer 知道 run 身份；虽先分别查看 raw/final claim 再查显式 disposition，但没有独立第二人盲评。上述文本限定已原样保留在裁决中，没有追加 seed、改动冻结合同或改写 live 产物。
