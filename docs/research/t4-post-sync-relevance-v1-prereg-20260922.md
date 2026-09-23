# T4 post-sync relevance v1 预注册

日期：2026-09-22。实验身份：`t4-post-sync-relevance-v1-192p`。比较对象为已有的 `t4-post-sync-inspection-v2-192p` 三个有效 seed；正式结果与 artifact 见 [v2 三 seed 报告](../releases/flowise-3.1.3-repository-v1-t4-post-sync-inspection-v2-3seed-20260922.md)。

## 问题与 treatment

v2 三 seed 中，12/12 agent 在 RESULT_SYNC 后留下 foreign artifact inspection record；人工复核 5/12 指出具体控制或路径关系，0/12 提出可执行且有判别结果的验证线索。下一实验问：在不改变任务和工具能力的条件下，仅要求模型把“主题相近”和“对自身 finding 直接相关”分开，并说明可验证目标或明确没有目标，能否增加可追溯的直接相关判断与具体线索？

profile：`repository_v1_t4_post_sync_relevance_v1`。它保留 v2 完整的 RESULT_SYNC snapshot 与 inspection 指令，只在消息末尾追加 relevance 判断。初始 system/user prompt 与 v2 逐字一致。模型可以决定结果无直接关联、没有有用验证、无需行动；不要求采用、引用 foreign evidence、修改 finding 或调用工具。

## Matched contract

条件为 T4/4 agents，Flowise repository-v1 target、`deepseek-flash`、thinking disabled、temperature 0、max output 4096、`convergent_v2`、`all_agents_terminal_v1`、`team_remaining_permits_v1`、192 hard team permits、reserve=32、max steps=96、1200s、retry=1、`initialization_lease_v1`、`task_closure_gate_v1`、`result_sync_v1`、同一 scheduler、tool schema 和 evaluator。

顺序使用既有 seed identity：`t4-result-sync-v1-matched-seed-01`、`-02`、`-03`。对应 v2 control 为 seed 01 replacement、seed 02、seed 03。每个 run 必须 valid、4/4 initial task closure、RESULT_SYNC exactly once、provenance 完整、无 deadlock，才进入机制比较。任一 run 无效时保留原 artifact 并单列失效原因；不把未触发同步的机械 R0 当作模型无关性。

## 主要结果与判定

采用已在 v2 seed 02/03 前固定的 [manual adjudication v1](t4-post-sync-inspection-manual-adjudication-v1-20260922.md)，对每位 agent 的同步后 model-visible response 判定：

1. 是否明确选中一个 foreign task；
2. 是否指出具体代码路径、安全控制、不变量或调用关系，以及 foreign 观察对自身候选 finding 的影响（direct relation）；
3. 是否提出一个有目标及判别结果的后续 read/search/test（actionable lead）；
4. 是否明确判断无直接关联或无有用验证目标。

只复述 prompt 术语、同包/同类别相似、没有指向自身 finding 的泛化“加强”不算 direct relation；“应进一步检查”而无目标与判别结果不算 actionable lead。每项肯定判断保留 transcript ID。由于 treatment 本身要求表述，比较的是满足固定实质标准的内容，不将出现关键词视为机制成功。

R0–R4、foreign evidence body read、tool follow-through、foreign refs 进入最终 finding、finding/TP 均作为次要结果。原 runtime 在三个 v2 seed 中均先进入 team finalization 再触发 RESULT_SYNC；因此同一冻结条件下，post-sync search/read 行为受 finalization 约束。R3=0 不能单独归因于 relevance 失败。

## 执行边界

先冻结新的 block identity。live 前校验 hash、case budget 192、reserve=32、初始 prompt/tool schema 与 v2 一致，并做零网络 mock/preflight。正式 run 按 seed 顺序执行，逐 run 复核入选门槛；无效 run 不作 R0–R4 因果解释。此文记录实验设计，不记录尚未执行的结果。
