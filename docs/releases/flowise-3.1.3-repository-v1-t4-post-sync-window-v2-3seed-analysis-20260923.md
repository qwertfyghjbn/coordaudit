# Flowise repository-v1 T4 POST_SYNC window v2：3 seed 分析与条件转移

日期：2026-09-23。冻结 block：`t4-post-sync-window-v2-192p`。本报告分析 [v2 预注册](../research/t4-post-sync-window-v2-prereg-20260922.md) 所列的三个 matched seed；不改变 contract、prompt、manual definitions 或已完成的 run。seed 01 的完整人工记录见 [seed 01 adjudication](flowise-3.1.3-repository-v1-t4-post-sync-window-v2-seed01-adjudication-20260922.md)。

## Admission 与运行完整性

三次运行均为 valid/reconciliation valid，均 4/4 initial task closure、`RESULT_SYNC` exactly once、4/4 window opened、instruction model-visible 与至少一次 post-sync provider admission。12/12 agent 都收到 runtime guarantee 的首次 POST_SYNC 请求；没有 provider failure，也没有因缺 POST_SYNC opportunity 的 forced completion。

| Run | Team completion | Calls | POST_SYNC admitted / instruction visible | Verification attempted / evidence model-visible | Final submit |
| --- | --- | ---: | ---: | ---: | ---: |
| [seed 01](../../experiments/emergent_coordination/runs/t4-post-sync-window-v2-192p/matched-seed-01/summary.json) | forced_complete；1 model format failure | 178 / 192 | 8 / 8 | 0 / 0 | 3 / 4 |
| [seed 02](../../experiments/emergent_coordination/runs/t4-post-sync-window-v2-192p/matched-seed-02/summary.json) | clean_complete | 172 / 192 | 8 / 8 | 1 / 1 | 4 / 4 |
| [seed 03](../../experiments/emergent_coordination/runs/t4-post-sync-window-v2-192p/matched-seed-03/summary.json) | clean_complete | 182 / 192 | 10 / 10 | 1 / 1 | 4 / 4 |

这验证了 runtime contract：两次自愿 `read_file` 都获得 evidence-consumption model call（seed 02 `evt_00001152` → `evt_00001157` / `evt_00001159`；seed 03 `evt_00001246` → `evt_00001251` / `evt_00001253`）。v2 的 submit-only repair 也使 seed 02/03 保持 clean completion；seed 01 `agent_003` 在个人 4 permits 内仍未形成有效 payload，是模型格式失败而非 reservation 缺失。

## R0–R4 与严格人工字段

机械 analyzer 为 R1×12。冻结 manual definition 要求 `foreign artifact selected` 中模型明确写出 **foreign completed task ID**。v2 prompt 不要求这种记录；12 份首次实质 POST_SYNC 回应都没有 task ID。因此 selected=0/12，foreign evidence body read=1/12，direct relation=3/12，actionable lead=2/12，follow-through=2/12，verification action=2/12，post-verification judgment=2/12，最终 foreign evidence_ref incorporation=0/12。

`selected → direct relation` 的严格条件分母为 0，不能把 direct=3/12 写成严格 selection 转移率；同理，`lead → verification` 只能以实际出现 lead 且 opportunity delivered 的两名 agent 为分母。

| Seed / agent | foreign referent in response | Strict selected | Relation / lead | Verification and judgment | Final foreign adoption |
| --- | --- | --- | --- | --- | --- |
| 01 / 001 | 泛称 synchronized artifacts | no | thematic=`uncertain`；无 lead | 无 action | no |
| 01 / 002 | `agent_001` TTS lookup、`agent_003` workspace guards | no task ID | thematic-only；无 direct/lead | 无 action | no |
| 01 / 003 | 泛称 OAuth2、TTS、webhook topics | no | 无 relation/lead | 无 action | no final finding |
| 01 / 004 | 泛称 enterprise RBAC、OAuth2、TTS | no | 无 relation/lead | 无 action | no |
| 02 / 001 | 泛称 components/server utils/webhook areas | no | 无 relation/lead | 无 action | no |
| 02 / 002 | `agent_001` feedback IDOR；`agent_003` OAuth2 IDOR | no task ID | direct；feedback controller 是明确 lead | 读取 exact foreign-evidence file body；证据可见后确认并形成 finding | no foreign ref；见下文 claim adoption |
| 02 / 003 | 未实质讨论 foreign result | no | 无 relation/lead | 无 action | no |
| 02 / 004 | `agent_002` webhook auth review、`agent_001` public route finding | no task ID | direct：同一 webhook auth control 的 applicability 区分；无 lead | 无 action | no |
| 03 / 001 | 泛称 components/storage/uploads/MCP | no | 无 relation/lead | 无 action | no |
| 03 / 002 | `agent_004` file-storage/upload audit | no task ID | direct；public get-upload-file route 是明确 lead | target read 后下调 reachability、severity/confidence，并提交 | no foreign ref |
| 03 / 003 | `agent_001` routes/controllers task | no task ID | 仅非重复性说明；无 direct/lead | 无 action | no |
| 03 / 004 | 泛称 feedback/node-load/storage findings | no | 无 relation/lead | 无 action | no |

seed 02 `agent_002` 的 `trn_agent_002_00000175` 明确把 agent_001 的 feedback IDOR 作为可支持 finding，并读取 `controllers/feedback/index.ts`。该文件正是 `agent_001` task `task_302a70c930` 的 foreign evidence body（其 ref `evt_00000198`）；agent_002 的 post-sync read 产生 `evt_00001154`。在 `trn_agent_002_00000178`，模型根据该结果确认 IDOR 并提交。

seed 03 `agent_002` 的 `trn_agent_002_00000150` 将 agent_004 的 storage-provider guard 结论与自己的 raw-path gap 关联，提出读取 `controllers/get-upload-file/index.ts`。`evt_00001248` 显示该读取；`trn_agent_002_00000153` 据此明确下调“publicly reachable traversal”的判断，保留为 defense-in-depth guard-coverage gap，并在修复 schema 后提交。这个目标与 foreign task 语义对齐，但该 controller 不在 agent_004 的 frozen `evidence_refs` 中，所以不计 foreign evidence body read。

## 条件转移

下表是预注册的、可解释的条件比例。所有 12 位 agent 都有 opportunity delivered；无 action 的十位可归为“模型选择不验证”，不再混入机会缺失。

| Transition | Numerator / denominator | Interpretation |
| --- | ---: | --- |
| strict selected → direct relation | N/A，0 strict selected | v2 没有要求 task-ID inspection record，不能计算该率。 |
| direct relation → actionable lead | 2 / 3 | 两条 direct relation 产生可执行 target；seed 02 agent_004 只完成 shared-control differentiation。 |
| actionable lead + opportunity → target-aligned verification | 2 / 2 | 两条 lead 都被执行。 |
| verification → evidence model-visible | 2 / 2 | 两次都由 reserved followup delivery。 |
| evidence → post-verification judgment | 2 / 2 | seed 02 agent_002 确认并形成 finding；seed 03 agent_002 收窄其原 finding。 |
| post-verification judgment → final foreign evidence_ref adoption | 0 / 2 | 最终 findings 使用各自实际 read 的 evidence refs，没有引用 foreign task refs。 |

对“final adoption”需区分两个事实。严格 provenance adoption 为 0/2，因为没有最终 finding 引用 foreign task 的 evidence_ref。claim-level disposition 则是 2/2：seed 02 agent_002 经独立读取后采用 agent_001 的 feedback IDOR 作为自己的 finding；seed 03 agent_002 经读取后保留但收窄了自己的 candidate。这两个量不能合并。

### Judgment 的正确性复核

上表的 `evidence → post-verification judgment = 2/2` 只记录**模型在看见工具结果后作出了可观察的判断**，不是“2/2 判断正确”。人工沿冻结 target 的路由、controller、service、存储调用链复核了这两份最终 finding；未执行漏洞利用或动态复现。

| Seed / agent | 证据支持的判断 | 未被证实或过度延伸之处 | 人工结论 |
| --- | --- | --- | --- |
| 02 / 002 | 对 feedback IDOR 的**核心确认正确**：`GET /feedback/:id` 到 controller；默认 `WHITELIST_URLS` 包含 `/api/v1/feedback`，认证中间件按前缀放行；controller 将路径中的 chatflow ID 原样交给 service，查询仅按 `chatflowid`（及可选筛选项）过滤，没有 workspace/ownership 条件。 | 最终 finding 的“`public-chatbotConfig/:id` 使 ID 可公开发现”并不由该路由证明：它要求请求者**先提供** ID，并非列举 ID 的接口。“可枚举任意 chatflow”也超出了按已知 ID 查询的静态证据。`DENYLIST_URLS` 可移除 whitelist 项，因此“无认证”以默认配置为条件。未动态验证攻击可达性。 | **核心决策受代码支持，但利用便利性和 ID 枚举的措辞被放大**；不能计作整份 finding 无保留正确。 |
| 03 / 002 | **下调公开路由可达性正确**：所读 `get-upload-file` controller 检查 `fileName` 并调用带路径 guard 的 `streamStorageFile`，没有调用 raw-path `getFileFromUpload` / `removeSpecificFileFromUpload`；这份证据不支持原先对该公开路由的 traversal 推断。保留两处 helper 直接 `readFileSync` / `unlinkSync` 的 guard-coverage 不一致，也符合代码。 | 一处公开路由的阴性结果不能证明这些 helper 对所有入口都不可达；反过来，仅有无 guard 的 helper 也不能证明攻击者能控制传入 `filePath`。已见其他 upload/assistant 调用者传 `file.path ?? file.key` 或 `file.filePath`，但本次 verification 没有建立从不可信请求字段到任意本地路径的完整链。最终 finding 已自述“defense-in-depth gap rather than demonstrated traversal”，其 `path_traversal` 类别不应被解读为已证实漏洞。 | **局部纠偏正确、未被所读证据误导；最终风险仅为条件性 guard gap，攻击可达性未证实**。 |

因此，两个 verification 都完成了 evidence-consumption 和 judgment update/keep，但质量结果不是“2/2 正确发现漏洞”：seed 02 的核心安全判断成立、附带 exploitability 论断过强；seed 03 正确排除了所检路由并降低置信度，却没有闭合另一条可利用路径。这个正确性复核是事后人工解释，不改动冻结的 R0–R4、strict adoption 或运行有效性计数。

## 与前一轮的比较

| Treatment / analyzable population | Task-ID inspection | Direct relation | Actionable lead | Lead → action | Evidence-visible after action | Strict foreign-ref adoption |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| verification-permission v1，seed 02/03，permission delivered 8 agents | 8 / 8 | 1 / 8 | 1 / 8 | 0 / 1 | 0 / 0 | 0 / 8 |
| POST_SYNC window v2，3 seeds，opportunity delivered 12 agents | 0 / 12 | 3 / 12 | 2 / 12 | 2 / 2 | 2 / 2 | 0 / 12 |

v2 证明当模型形成具体 lead 时，reservation、窄 read 与 evidence-consumption followup 足以让这两条轨迹闭合到**可见** judgment 和 final submission；正确性复核则显示两条判断均有边界，不能将闭环率直接当成正确率。它没有证明 v2 提高了 inspection 或 overall reuse：prompt 移除了旧版的强制 inspection record，task-ID selection 因而从 8/8 降到 0/12；同时 v2 改了 prompt、执行窗口和收尾 guard，且只有三个 stochastic matched runs，不能将条件差异归因于任一单独因素。

目前最稳健的结论是：runtime opportunity 缺失不再解释 action 缺失；在实际出现的两个 actionable lead 上，模型均执行了 verification 并看到了证据。瓶颈转移到模型是否自发形成可归因、可计数的 foreign inspection/relevance record，以及是否把 foreign provenance 写入 final finding。若后续要测这两点，应作为新的、独立冻结的 prompt/instrumentation treatment，而不是修改 v2 的已冻结结果。

## Supporting artifacts

- seed 01：[summary](../../experiments/emergent_coordination/runs/t4-post-sync-window-v2-192p/matched-seed-01/summary.json)、[metrics](../../experiments/emergent_coordination/runs/t4-post-sync-window-v2-192p/matched-seed-01/metrics.json)
- seed 02：[summary](../../experiments/emergent_coordination/runs/t4-post-sync-window-v2-192p/matched-seed-02/summary.json)、[metrics](../../experiments/emergent_coordination/runs/t4-post-sync-window-v2-192p/matched-seed-02/metrics.json)
- seed 03：[summary](../../experiments/emergent_coordination/runs/t4-post-sync-window-v2-192p/matched-seed-03/summary.json)、[metrics](../../experiments/emergent_coordination/runs/t4-post-sync-window-v2-192p/matched-seed-03/metrics.json)
