# Flowise 3.1.3 repository-v1 依赖环境物化记录（2026-09-18）

## 结论

针对 freeze candidate（2026-09-16）"未闭合风险"第 1 条，本记录补齐同级别的 trusted-control-plane 依赖物化步骤：五个 B 类 targeted validator（R10/R13/R14/R16/R17）所需的 snapshot-matched、离线、Node 24 依赖环境已物化并通过完整性校验。`live_gate` 维持 `blocked`：validator 本体尚未执行，且解除需用户明确批准。

## 交付物

- 物化脚本：`scripts/materialize_flowise_3_1_3_repository_v1_dependency_env.py`（SHA-256 `f61c45d21e61f4c9eb27c3c61ce54af8f405a169c66aeb6f7c752898bfe31d90`）。
- 依赖环境：`artifacts/flowise_3_1_3_repository_v1_dependency_env/`（gitignored，含 `node-runtime/`、`pnpm/`、`workspace/` 与 `logs/`；不属于 Agent-visible target，也不进入冻结 evaluator-private 树）。
- 审计元数据：`experiments/emergent_coordination/evaluator_private/flowise_3_1_3_repository_v1/dependency_materialization.json`，随冻结私有树一起被 manifest 摘要覆盖。

## 固定输入与绑定

| 输入 | 值 / 摘要 |
| --- | --- |
| Node 发行版 | `v24.14.1 linux-x64`，tarball SHA-256 `84d38715d449447117d05c3e71acd78daa49d5b1bfa8aacf610303920c3322be`，对 `nodejs.org/dist/v24.14.1/SHASUMS256.txt` 校验通过 |
| Node runtime 树摘要 | `0ee8a17a945a299ceecaa5a64948c29f51683820a16c5ac8dae8f2ee232e00dd` |
| pnpm | `pnpm@10.26.0`（精确 pin），toolchain 树摘要 `4b6bbb6fe70e7d9af5c2b8bed8432a696563f8b91bd8c46454a4064a3db36a4b` |
| 安装命令 | `pnpm install --frozen-lockfile`（lockfileVersion 9.0，SHA-256 `e4b42fbbaaa2e01fb43cf1be4a5739b2501fa58ab5e052d8aca90fd3f959e5f4`） |
| snapshot 绑定 | workspace 安装前树摘要 = 冻结 target 摘要 `c612819a833fc8ab3c58fe5085fb80fc0a6c4cb1d86cbb8ed41b0b431e4a1638` |
| node_modules 树摘要 | `a17cad84f4c8d44bc1bcaf947939586933c151e91aa2936923b71a11cae1ff09` |

构建脚本策略遵循冻结快照自身的 `pnpm.onlyBuiltDependencies` 白名单（`faiss-node`、`sqlite3`），未使用 `--dangerously-allow-all-builds` 扩权。仅有的环境覆盖：`HUSKY=0`（快照为 VCS-free，根 `postinstall: husky install` 无法运行且与验证无关）与 `git http.version=HTTP/1.1`（WSL2 下 faiss-node 源码克隆的 HTTP2 间歇故障）。网络仅用于本次已记录的物化取包；验证阶段离线运行。

## 离线 smoke（全部通过）

- `node --version` → `v24.14.1`。
- 死代理 + `pnpm install --frozen-lockfile --offline` → `Done in 8.2s using pnpm v10.26.0`。
- 模块加载：server 侧 `express 4.18.3`、`zod 4.3.6`、`typescript 5.5.2`；components 侧 `@langchain/core 1.1.20`、`langchain 1.2.18`、`typescript 5.5.2`、`jest 29.7.0`。

## 验证结果

- `scripts/verify_flowise_3_1_3_repository_v1.py`：`status: passed`，新增 `dependency_environment: verified`（校验 target/lockfile 绑定与 node-runtime、pnpm、node_modules 三棵树的摘要；环境缺失时报告 `not_materialized` 而非失败）。
- 摘要更新：manifest `evaluator_private_tree_sha256` → `da07505a4eac2204ba4690540297e11d286bed6f12e67fa3d9ddf26095fa2b2c`；verification result SHA-256 → `f8d71d31f00e1f1b64c0c9c3a31ff0638759f52c3c157549301d9b2f1ac11e22`。target、base prompt、finding schema、tool surface 摘要不变。
- `python3 -m unittest discover -s experiments/emergent_coordination/tests -t .`：95 passed。
- flowise case S/P/B/T mock smoke（single/1、parallel/4、raw_blackboard/4、structured_team/4，`--mock --smoke-budget`）：全部通过。
- `git diff --check`：通过。

## 剩余阻塞

1. 在该环境内执行 R10/R13/R14/R16/R17 的 targeted validator（Phase 4 fixture），并把 `validation_recipes.json` 与 `verification_metadata.json` 的 `not_run` 状态更新为实际结果；`required_for_tp` 保持 `false`。
2. U01/U02 维持 unresolved，不迁入 scored GT。
3. `live_gate` 解除仍需用户明确批准。
