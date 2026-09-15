# CoordAudit 迁移文件清单

状态：第一次行为保持迁移已完成；本文仍是范围与验收记录。源文件清理、原仓库 pointer 更新和跨仓链接检查与本次迁移一起完成。

## 1. 必须迁出

### 1.1 Runtime、协调与评估代码

源目录：`/home/lqs/llm_audit_system_learning/experiments/emergent_coordination/`

以下文件属于 CoordAudit 自身实现，应迁入新项目并在迁移提交中改写 `experiments.emergent_coordination` imports 和仓库根路径推导：

```text
README.md
__init__.py
run_experiment.py
analysis/__init__.py
analysis/analyze_run.py
evaluator/__init__.py
evaluator/score.py
harness/__init__.py
harness/agent_loop.py
harness/budget.py
harness/events.py
harness/llm/__init__.py
harness/llm/client.py
harness/paths.py
harness/policies/__init__.py
harness/policies/base.py
harness/prompts.py
harness/runner.py
harness/shared_fs.py
harness/task_board.py
harness/tools/__init__.py
harness/tools/sandbox.py
harness/tools/specs.py
harness/workspace.py
```

建议目标位置：运行代码放入新项目自己的 Python package；CLI 保留一个入口。第一次迁移只改必要 import/path，不同时重新设计 module interface。

### 1.2 Harness tests

以下测试约束 S/P/B/T capability 隔离、并发 claim、hidden metadata 和 repository semantics，必须与实现一同迁出：

```text
experiments/emergent_coordination/tests/__init__.py
experiments/emergent_coordination/tests/conftest.py
experiments/emergent_coordination/tests/test_analyze_run.py
experiments/emergent_coordination/tests/test_datasets_immutable.py
experiments/emergent_coordination/tests/test_evaluator.py
experiments/emergent_coordination/tests/test_harness.py
experiments/emergent_coordination/tests/test_leak.py
experiments/emergent_coordination/tests/test_prompts.py
experiments/emergent_coordination/tests/test_repository_semantics.py
experiments/emergent_coordination/tests/test_scaling.py
```

其中 `test_datasets_immutable.py` 当前直接读取原仓库 `datasets/synthetic/`，迁移后必须改为验证 provenance snapshot/hash，不能制造对兄弟仓库绝对路径的运行时依赖。

### 1.3 Pilot benchmark 与 hidden evaluator

以下资产由 CoordAudit harness 直接消费，应迁出并保持 Agent-visible / evaluator-private 两类目录分离：

```text
experiments/emergent_coordination/manifests/repository_pilot_v0.json
experiments/emergent_coordination/evaluator_private/repository_pilot_v0/ground_truth.json
experiments/emergent_coordination/evaluator_private/repository_pilot_v0/provenance.json
experiments/emergent_coordination/repositories/repository_pilot_v0/README.md
experiments/emergent_coordination/repositories/repository_pilot_v0/requirements.txt
experiments/emergent_coordination/repositories/repository_pilot_v0/app/__init__.py
experiments/emergent_coordination/repositories/repository_pilot_v0/app/config.py
experiments/emergent_coordination/repositories/repository_pilot_v0/app/main.py
experiments/emergent_coordination/repositories/repository_pilot_v0/app/common/__init__.py
experiments/emergent_coordination/repositories/repository_pilot_v0/app/common/http_client.py
experiments/emergent_coordination/repositories/repository_pilot_v0/app/common/http_strict.py
experiments/emergent_coordination/repositories/repository_pilot_v0/app/common/io.py
experiments/emergent_coordination/repositories/repository_pilot_v0/app/common/logutil.py
experiments/emergent_coordination/repositories/repository_pilot_v0/app/common/storage.py
experiments/emergent_coordination/repositories/repository_pilot_v0/app/common/templates.py
experiments/emergent_coordination/repositories/repository_pilot_v0/app/routes/__init__.py
experiments/emergent_coordination/repositories/repository_pilot_v0/app/routes/documents.py
experiments/emergent_coordination/repositories/repository_pilot_v0/app/routes/files.py
experiments/emergent_coordination/repositories/repository_pilot_v0/app/routes/integrations.py
experiments/emergent_coordination/repositories/repository_pilot_v0/app/routes/reports.py
experiments/emergent_coordination/repositories/repository_pilot_v0/app/routes/webhooks.py
experiments/emergent_coordination/repositories/repository_pilot_v0/app/services/__init__.py
experiments/emergent_coordination/repositories/repository_pilot_v0/app/services/document_service.py
experiments/emergent_coordination/repositories/repository_pilot_v0/app/services/fetch_service.py
experiments/emergent_coordination/repositories/repository_pilot_v0/app/services/file_service.py
experiments/emergent_coordination/repositories/repository_pilot_v0/app/services/report_service.py
experiments/emergent_coordination/repositories/repository_pilot_v0/app/services/webhook_service.py
experiments/emergent_coordination/repositories/repository_pilot_v0/tests/__init__.py
experiments/emergent_coordination/repositories/repository_pilot_v0/tests/test_app_smoke.py
```

迁移时还要修改 manifest 中的 `target_root`、`ground_truth`、`provenance`，并把 `supported_agent_counts` 与 N=4 feasibility 解释分开；当前声明支持 8/16/32 不等于 benchmark 对这些 N 有足够 work fronts。

### 1.4 CoordAudit 专属研究文档

```text
/home/lqs/llm_audit_system_learning/docs/research/coord_audit_task.md
/home/lqs/llm_audit_system_learning/docs/research/multi_agent_coordination_prior_art.md
/home/lqs/llm_audit_system_learning/N4_PILOT_PLAN.md
```

建议目标位置：

```text
docs/research/coord_audit_task.md
docs/research/multi_agent_coordination_prior_art.md
docs/plans/N4_PILOT_PLAN.md
```

文档中的 `/home/lqs/llm_audit_system_learning`、`experiments/emergent_coordination`、`reports/systems/coordaudit` 和 `datasets/` 引用需在迁移后逐项重写。

## 2. 选择性保留或归档

### 2.1 已有 mock runs

当前有四个 N=1/2 mock 生命周期 run：

```text
experiments/emergent_coordination/runs/single_n1_20260913T054415.552034+0000_73efdef3/
experiments/emergent_coordination/runs/parallel_n2_20260913T054415.677224+0000_7c3d6893/
experiments/emergent_coordination/runs/raw_blackboard_n2_20260913T054415.823167+0000_a655fa1f/
experiments/emergent_coordination/runs/structured_team_n2_20260913T054415.976893+0000_e96e8702/
```

这些不是 live pilot 结果，也没有 findings。默认不迁入正式 `runs/`；如需保存，只压缩为 `artifacts/legacy_mock_smoke/` 并附 `NON_RESULT.md`，防止被误当实验数据。

### 2.2 来源 benchmark

`repository_pilot_v0` 的 provenance 引用了以下原始 case：

```text
datasets/synthetic/PT-PY-REPO-001/
datasets/synthetic/PT-PY-REPO-002/
datasets/synthetic/SSRF-PY-REPO-001/
datasets/synthetic/SSRF-PY-REPO-002/
datasets/synthetic/SSTI-PY-REPO-001/
```

这些 case **保留在原仓库，不整体迁出**。新项目保留已经重组且自包含的 pilot repository、来源 case ID、原仓库 remote/commit 和内容 hash。后续若需要重新生成 composite benchmark，应通过显式 import/export 流程，而不是运行时访问 `../llm_audit_system_learning/datasets`。

## 3. 明确不得迁出

```text
datasets/                                      # 原仓库 benchmark corpus
scripts/                                       # DeepAudit/IRIS/OpenAnt 与旧归因实验脚本
artifacts/architecture_attribution/            # 已收口的另一条实验线
reports/systems/architecture-attribution/      # 已收口的另一条实验线
reports/cross_system/                          # 原仓库 canonical scope
artifacts/deepaudit_*/
artifacts/iris_*/
reports/systems/openant/
reports/systems/deepaudit/
reports/systems/iris/
.agents/
.codex/
.env_deepseek
任意 API key、auth artifact、__pycache__、*.pyc
```

`Architecture Attribution Experiment` 研究的是 static-tool constraint strength；CoordAudit 研究的是多 Agent runtime coordination adapter。二者名称接近，但实验变量、运行 harness 和结果线不同。

## 4. 迁移时必须修改的代码/配置

| 位置 | 当前耦合 | 迁移修改 |
|---|---|---|
| `run_experiment.py` | 把原仓库根加入 `sys.path`；导入 `experiments.emergent_coordination.*` | 使用新 package/CLI 入口 |
| `harness/paths.py` | 通过 `parents` 假定嵌套在原仓库 `experiments/` 下 | 从新项目根或显式 config 解析 benchmark/run 路径 |
| 全部 Python imports | package 前缀为 `experiments.emergent_coordination` | 一次性机械改名，避免双 package |
| `harness/runner.py` | `git_commit(REPO_ROOT)` 指向原仓库 | 记录新项目 commit、dirty state、benchmark content hash |
| `harness/tools/sandbox.py` | blacklist 含 `datasets/synthetic` 等原仓库词条 | 改为基于允许挂载的 OS sandbox，不能只换字符串 |
| `test_datasets_immutable.py` | 读取原仓库 source cases | 验证冻结 provenance/hash；可另做显式上游一致性检查 |
| `repository_pilot_v0.json` | 写死旧相对路径 | 改成新项目内路径并补 config hash |
| `.gitignore` | 原仓库专用 runs 规则 | 在新项目建立 `runs/*` + `!runs/.gitkeep` |
| provider 配置 | 当前依赖原仓库 `.env_deepseek` | 只新增无密钥 `.env.example`；真实 secret 留在用户环境 |

## 5. 建议迁移顺序

1. 冻结原文件清单、SHA-256、原仓库 commit/dirty 状态。
2. **复制**必须迁出的代码、benchmark 和文档到新项目；暂不删除源文件。
3. 只修改 package imports、路径、manifest 和 provenance；不同时实现 N4 P0 加固。
4. 在新项目运行现有 35 项 harness tests、6 项 repository smoke tests及 S/P/B/T mock smoke。
5. 比较迁移前后的 evaluator、events 和 mock summaries，确认行为等价。
6. 在新项目形成第一个可复现 commit。
7. 再修改原仓库 docs/config，并删除原仓库 CoordAudit 副本。
8. 原仓库保留稳定的跨仓链接或简短 tombstone，避免已有引用静默失效。

## 6. 迁移验收

- 新项目不读取原仓库绝对路径即可运行全部测试。
- `rg 'experiments\.emergent_coordination|/home/lqs/llm_audit_system_learning'` 只在历史 provenance 中出现。
- Agent-visible workspace 无 hidden ground truth/source case 标签。
- 原仓库不再包含 CoordAudit runtime；旧 Architecture Attribution 结果完整保留。
- 两个仓库分别拥有可解释的 commit/hash，manifest 不再把未跟踪实现记成旧 HEAD。
