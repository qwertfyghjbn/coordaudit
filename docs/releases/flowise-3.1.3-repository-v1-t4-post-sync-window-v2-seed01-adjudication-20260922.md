# T4 POST_SYNC window v2：matched seed 01 逐 agent 人工判定

日期：2026-09-22。运行：[matched-seed-01](../../experiments/emergent_coordination/runs/t4-post-sync-window-v2-192p/matched-seed-01/summary.json)。本报告只判定既有运行；不修改 frozen contract、prompt、manual definitions 或运行产物。方法沿用 [manual adjudication v1](../research/t4-post-sync-inspection-manual-adjudication-v1-20260922.md) 和 [v2 预注册](../research/t4-post-sync-window-v2-prereg-20260922.md)。

## Admission 与边界

运行 `valid`、reconciliation `valid`（1281 events、618 transcripts、381 artifacts、178 permits）；4/4 initial task closure，`RESULT_SYNC` 恰好一次（`evt_00001197`）；4/4 POST_SYNC window opened、instruction model-visible、首次 provider request admitted。总共 178/192 permits，POST_SYNC 8 次 provider calls，0 次 verification action。不存在因缺 POST_SYNC opportunity 导致的 forced completion。

Team completion 是 `forced_complete`：`agent_001`、`agent_002`、`agent_004` 成功提交；`agent_003` 在本 agent 的 4 个 POST_SYNC permits 用完后仍未形成有效 submission，终止为 `model_format_failure`（`evt_00001277`、`evt_00001279`）。这与机会交付失败是两种不同原因。

## 逐 agent 证据与判定

`selected` 的冻结条件是模型明确给出 **foreign completed task ID**。仅说“同步结果”“其他 agent”或漏洞主题，不满足该条件。`body read` 要求同步后实际 `read_file` 读取 foreign evidence_ref 对应的文件正文。表中的“主题陈述”描述可见文本；没有 task ID 的主题陈述不进入 `selected → relevance` 条件分母。

| Agent | POST_SYNC 首次回应与可见机会 | Manual adjudication | 终局 |
| --- | --- | --- | --- |
| `agent_001` | `trn_agent_001_00000187` 收到 snapshot；`evt_00001217` window、`evt_00001220` admission、`evt_00001221` instruction visible。`trn_agent_001_00000188` 只说 foreign artifacts 与自己的 TTS credential finding 一致，未指明 task、证据或影响结论的关系。 | selected=否；body read=否；thematic=`uncertain`（“一致”未说明具体共同模式）；direct=否；actionable lead=否；follow-through=否。 | 首次提交因 `variant_coverage` schema 被拒（`trn_agent_001_00000189`），第二次 `post_sync_submit` 请求 `trn_agent_001_00000190` 后成功提交 1 finding（`evt_00001241`）。最终 refs 全为本人 file-read events；foreign incorporated=否。 |
| `agent_002` | `trn_agent_002_00000173` 收到 snapshot；`evt_00001208` window、`evt_00001211` admission、`evt_00001212` instruction visible。`trn_agent_002_00000174` 提及 `agent_001` 的 TTS lookup 和 `agent_003` 的 workspace guards，称存在共同的 missing tenant scoping pattern，并明确选择不再读取。 | selected=否（没有 foreign task ID）；body read=否；有主题关联陈述，但未绑定所选 task；direct=否（没有指出 foreign 观察通过哪个具体路径、控制或调用关系改变自己的 OAuth2 callback finding）；actionable lead=否；follow-through=否。 | 直接提交 1 finding（`evt_00001229`）。最终 `evt_00001155`、`evt_00000819` 均是本人的 file-read refs，与 foreign task refs 无交集；foreign incorporated=否。 |
| `agent_003` | `trn_agent_003_00000117` 收到 snapshot；`evt_00001245` window、`evt_00001248` admission、`evt_00001249` instruction visible。`trn_agent_003_00000118` 将 OAuth2 callback、TTS、webhook signature 概称为 foreign topics，判断自身两项 finding 独立，未给 task ID 或相关代码关系。 | selected=否；body read=否；thematic=否（只列出不同主题并声明独立）；direct=否；actionable lead=否；follow-through=否。 | 四次 POST_SYNC 调用（首次 + 三次 submit-only 修复）均未成功提交：无效 JSON、`variant_coverage` schema、无效 JSON、第二项 finding 的 evidence_refs 不匹配。最后 `trn_agent_003_00000128` 仍为拒绝结果，`evt_00001277` 个人 reservation exhausted；没有 final finding，foreign incorporated=否。 |
| `agent_004` | `trn_agent_004_00000121` 收到 snapshot；`evt_00001199` window、`evt_00001202` admission、`evt_00001203` instruction visible。`trn_agent_004_00000122` 概称其他 agent 研究 enterprise RBAC、OAuth2、TTS，判断不影响自己的 webhook findings，未给 task ID。 | selected=否；body read=否；thematic=否（明确说是不同 surface，未提出共同模式）；direct=否；actionable lead=否；follow-through=否。 | 直接提交 2 findings（`evt_00001227`）。全部最终 refs 为本人的 file-read events；foreign incorporated=否。 |

聚合：严格的 foreign artifact selected 0/4；foreign evidence body read 0/4；有一条未绑定 task ID 的主题关联陈述（`agent_002`），一条主题关系证据不足（`agent_001`）；direct relation 0/4；actionable lead 0/4；verification action 0/4；成功提交者的 final foreign evidence incorporation 0/3（按全部 agent 为 0/4）。机械 analyzer 为 R1×4。`selected → direct relevance`、`lead + delivered opportunity → verification action` 与 `verification → post-verification judgment` 的条件分母均为 **0**，应记为 N/A，不能报告“0% follow-through”。成功 final submission 为 3/4，与 R0–R4 行为级别分别报告。

## 解释

v2 的中性提示允许模型直接提交。四名 agent 都在获得 POST_SYNC 请求后选择不验证；这次轨迹可以将“模型未验证”与“没有验证机会”区分开。四份回应都概括提到了 foreign 内容，但没有符合冻结 selected 定义的 task ID，因此不把泛化提及上调为 formal inspection、direct relevance 或 reuse。

与 v1 同 seed 的 4/4 selected、1/4 direct relevance、1/4 verification 相比，本次没有观察到可计数的行为链。v1 含强制 inspection/relevance 文本；v2 同时修正了该提示和提交收尾 guard，且每次 live 轨迹有模型随机性。单个 matched seed 只能支持上述描述，不能把差异单独归因于某一项修改，也不能推断稳定 reuse 率。按冻结计划，下一步是在同一 v2 contract 下运行 matched seed 02/03，再作条件转移比较。
