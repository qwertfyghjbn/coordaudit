# Flowise 3.1.3 repository-v1 最终冻结记录（2026-09-18）

## 结论

`flowise_3_1_3_repository_v1` 正式冻结：`live_gate` 由 `blocked` 翻转为 `open`（用户明确批准），case 资产已纳入版本控制（资产化 commit `430efbc`，gate 开启为本记录所属的后续 commit）。此前 freeze candidate（2026-09-16）列出的唯一阻塞条件——五个 B 类 targeted validator 无可运行环境——已完全闭合：依赖环境已物化并验证，五条 validator 全部离线执行并通过（R10/R13/R14/R16/R17，全套 11/11，`required_for_tp` 全部保持 `false`）。

## 冻结输入（与 freeze candidate 一致，未变）

- 上游：`https://github.com/FlowiseAI/Flowise.git`；vulnerable `flowise@3.1.3` / `09f099dbfda179e439ec677d06ad737375899eef`（tree `4da2b4977634b3bb238155430a79bd3dbef775c8`）；comparison `flowise@3.1.4` / `a65f81bb43ef66d3ce734bf0dff4223ae8041c95`。
- 条件：S1/P4/B4/T4，共用 target、repository-v1 base prompt、finding schema、工具能力边界、64 team-level call permits；B 仅 generic persistent store，T 仅冻结 typed task state；M 未定义。

## 冻结摘要（本次最终值）

| 项目 | SHA-256 / 值 |
| --- | --- |
| Agent target tree | `c612819a833fc8ab3c58fe5085fb80fc0a6c4cb1d86cbb8ed41b0b431e4a1638` |
| Evaluator-private tree | `76aaef174369769e70b8ef61cda454d96a503fc033e1437a6b6efba934915e12` |
| Base prompt | `a63820831f9ab8864eb318444cfc8ad0b126043161833f145f8840e68c9581ec` |
| Finding schema | `97ad0335dde33ffd45a2056d7b8e15b79375fbea5a40c2e82d7f774ba7999c48` |
| S/P/B/T tool surface | `3522153c128829670809a62908d356d1a7ce270e9ecb642da8833d35959a013e` |
| Case manifest（live_gate: open） | `b421d20975e7e182fc6b37a2d4e870669f00df96795e598855897400404c220b` |
| Control-plane verifier | `bece9d4954aee9d59a5b3d298b19cfd4c23c65de7a2d53e76e991430c52f3b0a` |
| Verification result | `e39ad0f7d1c727ca855fbd3a81019c19a48fc2b3f4d7fa619400df011eed8f99` |
| 源 materializer | `b57898a8c8315423d743ccf9df2814fb13a06ad6e5bdabcdf7ff35b41e4e5350` |
| 依赖环境 materializer | `f61c45d21e61f4c9eb27c3c61ce54af8f405a169c66aeb6f7c752898bfe31d90` |

计分边界不变：20 scored roots（15 A + 5 B）、2 C known-unscored、1 CI-only 排除、2 unresolved（U01/U02 不计分）、5 known near misses；主分以 independent semantic root cause 为单位。

## B 类 validator 最终结果

五条全部离线（死代理）通过，证据与 log 摘要登记于 `evaluator_private/…/validation_recipes.json`：

| Root | 结果 | 关键断言 |
| --- | --- | --- |
| R10 | passed | 白名单外命令被拒（报错枚举硬编码白名单）；`npx` 裸包名通过 |
| R13 | passed | LLM 生成非 SELECT 语句逐字直达未防护 `datasource.query()` |
| R14 | passed | basePath 逐字成为 `clientConfig.baseURL`；策略 spy 零调用 |
| R16 | passed | 对象型 sessionId/chatId 原样返回，无 scalar 强制 |
| R17 | passed | mock 导航收到攻击者 URL；config 无策略字段；spy 零调用 |

## 重建与验证程序（从仓库检出出发）

1. `python3 scripts/materialize_flowise_3_1_3_repository_v1.py --output <target> --metadata <private>/materialization.json`——从 pinned 上游 tag 重建 target（自验 commit/tree/file count/脱敏/leakage scan）。
2. `python3 scripts/materialize_flowise_3_1_3_repository_v1_dependency_env.py`——物化离线 Node 24.14.1 + pnpm 10.26.0 依赖环境（官方 SHASUMS256 验签、workspace 安装前树摘要 == target、`--frozen-lockfile`）。
3. `python3 scripts/verify_flowise_3_1_3_repository_v1.py`——digest 对账（本表全部摘要）、B 类 validator 状态、leakage scan；期望 `status: passed`、`dependency_environment: verified`、`live_gate: open`。
4. 依赖环境内运行 `evaluator_private/…/validators/` jest 套件（运行命令与 log 摘要见各 root 的 evidence 块）。
5. `python3 -m unittest discover -s experiments/emergent_coordination/tests -t .`——95 passed（本次冻结回归实测）。

target 本体与依赖环境（gitignored）永不提交；本仓库只保留配方与摘要。

## live matched block 之前仍需满足（不因本冻结自动完成）

- 运行级 `live_gate`（block_runner 冻结 manifest）的四个前置：pre-call permit ledger、fail-closed OS sandbox、model-visible transcript 对账、严格 schema 去重与私有验证。
- 真实 provider 凭据与模型配置。
- 运行产物写入 `runs/`，正式结果另存 versioned artifact 并记录 model、prompt、tool schema、budget 与 benchmark digest。

## 残余事项

- 上游 branding 与版本字符串保留为 residual source-identity leakage（freeze candidate 风险 3，不变）。
- U01/U02 维持 unresolved，不迁入 scored GT。
