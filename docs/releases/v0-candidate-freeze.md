# CoordAudit v0 候选冻结记录

状态：`candidate`。本记录只在全部本地 gate 与 DeepSeek compatibility probe 成功后才可转为正式冻结记录。

## 候选范围

- Agent-visible target：`repository_pilot_v0`。
- Hidden evaluator、runtime、prompt、tool schema、N=4 合同与 ADR 0002–0005 的实现均由同一 Git commit 和冻结 digest 共同定位。
- 模型请求别名：`deepseek-flash`；thinking mode：`disabled`；temperature：`0`；每调用 output ceiling：`1024`。

禁用 thinking 是 v0 模型合同的一部分。DeepSeek 在 thinking mode 下不会实际应用 `temperature`，而 N=4 合同把 `temperature=0` 作为可比配置。因此候选配置显式使用 non-thinking mode。

## 完成条件

1. harness 全量单测、target-visible smoke 与四个 mock mode smoke 通过；
2. 工作树没有未记录的变更，且没有仓库凭证；
3. `compatibility_smoke.py --model deepseek-flash` 成功，记录 provider 的 resolved model 与 system fingerprint（若提供）；
4. 生成的单条件 live harness smoke 标记 `run_validity=valid` 且 `reconciliation=valid`；
5. 只在上述条件全部满足后，创建不可变 Git tag、block manifest 和正式 release record。

`compatibility_smoke.py` 与单条件 live smoke 都不是 matched block，不产生 S/P/B/T 效果结论。
