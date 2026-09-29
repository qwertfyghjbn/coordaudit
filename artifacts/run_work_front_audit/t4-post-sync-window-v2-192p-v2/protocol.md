# Run-conditioned Work-Front Audit v2：冻结协议

范围只含 `t4-post-sync-window-v2-192p` 的 `matched-seed-01/02/03`。这是一份 run-local 解释性资产，不把 work-front ID 迁入 HOG 或 benchmark。固定输入为 block manifest 的 target digest `c612819a833fc8ab3c58fe5085fb80fc0a6c4cb1d86cbb8ed41b0b431e4a1638`、`deepseek-flash`、192 team permits、每 agent 4 个 POST_SYNC permits，以及各 run 自身日志。

## 顺序和隔离

1. 以每 run 唯一的 `result_sync_triggered` event 时间为截点。定义 work front 时只读更早的 transcript、task create/claim/complete result，以及当时 Agent 可读的 target 源码。每个 bounded security question 需有实际调查证据；仅同文件、同漏洞类别或 broad task 描述不产生 front。完成的阳性与阴性调查都可入表。短暂浏览和未闭合横向扫描不单独成 front；边界不确定写 `boundary_uncertainty`。
2. 写出 `work_fronts.jsonl`、生成同 seed 不同 agent 的 `cross_agent_pairs.jsonl`，再以 `pre_sync_freeze.json` 记录 SHA-256。生成 pair 时排除 same-agent 与跨 seed，双向各算一条。work-front 及 pair 冻结后不为匹配后续行为改定义。
3. 两名独立 reviewer agent 只获得上述冻结文件、pre-sync trace 和 target 源码，各自对全部 pair 判 `actionable` / `non-actionable`，并附 `none`、`thematic-only`、`direct relation`、`actionable cross-check`、`strong dependency` 中的一个 descriptive tag。只有后两者属 actionable。正例必须写 source 最小可转移信息、target 具体 claim、改变判断的方向、最小区分性检查及两端代码锚点。先算 binary agreement；只裁分歧，原始标签保留。二人的访问隔离为任务约束和自报，不是 OS 文件访问审计。
4. 结构边冻结后，逐 actionable edge 核查 source 在同步前产出什么、target 的窗口可见什么、工具 schema、read 次数、预算与生命周期。`operationally realizable` 要求当前合同内可完成该 edge 的最小区分性动作；后来未行动不能倒推不可实现。
5. 逐 realizable edge 检查 source result/snapshot 的精确信息是否进入 target 的 `model_request.messages`，并检查 target 当时仍有行动窗口。只看到 generic RESULT_SYNC 不等于 edge delivered。以 event ID 回连 transcript，严格采用 ADR-0004 的 model-visible 边界。
6. 前五项写盘冻结后，才读取 POST_SYNC response、人工行为判读与 correctness review。行为字段按现有 manual adjudication：direct relation 需具体共同代码/控制及影响方向；actionable lead 需指定目标和区分性结果；verification 需实际执行对应 read/search/test；证据可见与最终判断、strict foreign-ref adoption 分开。

结构机会是源码与实际调查问题之间的关系；可实现性、交付和利用是 run/contract 事实。正确性不由 lead、action 或 judgment change 推出。已有三 seed 的 12/12 窗口、3 direct、2 lead、2 verification、2 evidence-visible、2 judgment 以及 v1 HOG 覆盖结论作为历史事实保留，不进入 work-front 或结构标签判定。审阅者可能知道公开的旧汇总，因此这里的“盲”特指不读取 POST_SYNC 行为记录和旧边标签；无法证明认知层面绝对无先验。
