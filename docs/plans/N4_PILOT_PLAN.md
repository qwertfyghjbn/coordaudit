# N=4 多 Agent 安全审计 Feasibility Pilot 规划

> 迁移注记（2026-09-15）：本计划的执行根目录已迁至 `/home/lqs/coordaudit`。文中对原 `datasets/` 与既有系统历史结果的描述仅作 benchmark provenance 与研究背景，不构成运行时依赖。

> **如果现在只允许做一个最小实验：先用现有 `repository_pilot_v0`，在同一个冻结配置块内跑 `S1 / P4 / B4-aware / T4` 各 1 次；模型沿用当前 DeepSeek OpenAI-compatible 接入。开跑前只补五类 P0：真正的 P/hidden-oracle 隔离、调用前全局预算许可、可关联的事件/证据日志、duplicate-work 与 coordination 指标、严格 finding 校验/确定性去重。暂不做 M4，也不新造大 benchmark。**

审计日期：2026-09-15。本文是执行规划，不是实验结果，也不修改 `datasets/` 或现有 harness。仓库递归盘点覆盖 29,463 个文件；对 36 个 case 的 `case.yaml`、`ground_truth.json`、必需文件和源码 anchor 做了结构化核验，对 CoordAudit 原型的全部 harness、grader、测试和现有 run 逐项检查，并抽查/汇总了 DeepAudit、IRIS、OpenAnt 和 Architecture Attribution 的脚本、manifest 与历史结果。大体积第三方 repo snapshot 采用全量文件/测试/anchor 校验和目标链抽查，而不是把 vendored 源码逐行当作本项目实现审阅。

## 1. Executive Summary

- **结论：GO WITH MINIMAL CHANGES。** 仓库已经有可复用的 S/P/B/T 统一 runner、OpenAI-compatible 模型入口、每 Agent 私有副本、raw shared filesystem、原子 task claim、JSONL 事件、hidden grader 和一个 5-front composite repo，基础不是从零开始。
- 最小实验应只跑 `S1 / P4 / B4-aware / T4 × 1 matched block`；机械指标通过后再补第二个 matched seed/block。M4 当前没有实现，不应为 9.17 强行加入。
- 推荐 benchmark 是 `experiments/emergent_coordination/repositories/repository_pilot_v0/`。它有 3 个 positive、2 个 near miss、5 条跨文件 HTTP 链，足以勉强验证 N=4 harness，但规模余量很小，不能支持 N=16，也不能用于架构优劣结论。
- 最大 blocker 不是 Agent loop，而是**测量可信度**：当前预算在 API 返回后才扣费，无法阻止并发超支；没有 API cost；事件没有 event/call/step lineage；分析器没有 `duplicate_work_ratio`；T 的 message read 不记录具体消息；grader 对 source 约束未实际使用。
- 当前 `P` 的私有目录隔离有单测，但 `run_shell(shell=True)` 仍运行在宿主机，只靠字符串黑名单和代理环境变量；它可以访问未列入黑名单的绝对路径，`NO_PROXY=*` 也不是断网。正式 live pilot 前必须用本机已有 `/usr/bin/bwrap` 或等价 OS sandbox 收紧。
- `B` 与 `T` 的代码边界基本清楚：B 只有 generic shared list/read/create/mkdir，不暴露 task/message/claim；T 有 typed task 和进程内原子 claim。需要继续保护该因果区别，不向 B 注入 namespace、任务模板、owner、leader 或 protocol 示例。
- 当前 4 份保存的 coordination run 只是 `mock` 的 N=1/2 空 finding 生命周期样本，不是 live pilot 证据；本次额外确认 S1/P4/B4/T4 的 mock CLI 都能启动并结束。
- 当前 `experiments/` 和 `docs/research/` 在工作树中尚未被 Git 跟踪；run manifest 只记 `HEAD=5221728...` 不能唯一冻结实际 harness/benchmark。第一条 live block 必须额外保存 dirty-worktree/tree-content digest。
- 最低实现工作量是局部加固现有 `experiments/emergent_coordination/`，不需要引入新 framework：预算许可、sandbox、事件字段、grader/dedup、analysis/block summary 五处小范围修改即可。
- Pilot 模型只用于验证 harness 与行为可观察性。当前 `.env_deepseek` 指向 `deepseek-v4-pro`，但必须先做兼容性 smoke，并在 manifest 记录 provider 返回/实际接受的精确配置；不得把本 pilot 的性能排名外推到未来 N=16 或其他模型。

## 2. Existing Assets

### 2.1 Benchmark

#### 总体清单

| 资产 | 路径 | 内容 | 可复用程度 | 关键限制 |
|---|---|---|---|---|
| Synthetic cases | `datasets/synthetic/` | 24 个 case；Python/Java × file/repo × PT/SSRF/SSTI × vulnerable/near-miss | 高，适合构造受控 composite 或 portfolio | 每个原始 case 只有 0/1 个标注 target；答案文件与源码同目录，不能直接暴露给 Agent |
| Real-world pairs | `datasets/real_world/` | 6 组 VULN/FIXED，共 12 个 repo case | 中，适合后续外部有效性和 pair 对照 | 多数 case 只有 1 个标注 target；大仓内 off-target 真问题未完整标注，不适合直接计算全仓 precision |
| 当前 composite repo | `experiments/emergent_coordination/repositories/repository_pilot_v0/` | 匿名 Flask 应用；3 positive + 2 near miss；5 条 route→service→helper 链 | **最高，直接用于本 pilot** | 仅 307 行 Python（含测试）、3 个漏洞家族、5 fronts；对 N=4 只是下限 |
| Composite hidden truth | `experiments/emergent_coordination/evaluator_private/repository_pilot_v0/` | `ground_truth.json` + `provenance.json` | 高 | 文件位置正确，但当前 shell 隔离不足，物理不可见性尚不可信 |
| Composite deterministic tests | `experiments/emergent_coordination/tests/test_repository_semantics.py` | 5 个 positive 语义断言、4 个 near-miss/guard 断言 | 高 | 测的是源 benchmark 语义；还未成为 run snapshot 上的 `verification_event` |
| Composite grader | `experiments/emergent_coordination/evaluator/score.py` | deterministic file/function/sink/category matching | 中 | `required_source_tokens_any` 未参与判定；`verified_findings` 信任 Agent 自报；无 schema 校验 |
| Portfolio-like registry | `reports/systems/openant/registries/e2_unit_partition_manifest.json`、`openant_case_matrix.json/csv` | 覆盖 synthetic/real-world 的 case 列表与历史结果 | 低到中，可借字段和分层 | 含另一个工作区的绝对路径；不是当前 harness 可执行的 portfolio manifest |
| 全局 benchmark manifest | 无 | 只有逐 case `case.yaml` 和 composite manifest | 缺失 | 36 case 没有统一版本/hash/clean-input/oracle registry |

全量核验结果：36/36 case 均有 `README.md`、`case.yaml`、`ground_truth.json`；目录 ID、YAML ID、ground-truth ID 和 label 一致；36/36 的 positive recall anchor 或 near-miss case target 均能定位源码，行号有效。一个需要后续统一的元数据差异是：synthetic repo anchor 相对 case 根（含 `src/...`），real-world anchor 相对 `input.repo_root`（不含 `repo/`）。当前 composite grader不受此差异影响。

仓库 benchmark 只覆盖 path traversal、SSRF、SSTI。36 个 `ground_truth.json` 都没有显式 CWE ID 字段；CWE 只在部分历史系统输出或 case 语义中间接出现。数据集中没有 command injection、SQL injection、auth/access control 或 unsafe deserialization case；也没有自动 seeded-variant 生成器。编号 001/002 和 VULN/FIXED 是人工/历史配对，不应称作随机 seed variants。

#### 每个 synthetic case

下表中的“确定性 oracle”均指结构化 label、source/sink/guard 和有效源码 anchor；原始 24 case 没有统一可执行 grader 或 exploit script。“hidden”均为**条件式**：答案当前与源码同目录，只有经过 clean-input copy 后才能隐藏。“可组合”表示可匿名重组到 composite，不表示把 case 目录直接拼接后即可成为有效 repo。

| 名称 | 路径 | 粒度 | 语言/框架 | 漏洞/标签 | 确定性 oracle | Runtime reproduction | Hidden GT | 可组合为 repo task | 有效 fronts |
|---|---|---|---|---|---|---|---|---|---:|
| PT-JA-FILE-001 | `datasets/synthetic/PT-JA-FILE-001/` | file | Java/Spring | PT / positive | anchor，有；可执行 grader，无 | 无 | clean-input 后 | 可，需重组 | 1 |
| PT-JA-FILE-002 | `datasets/synthetic/PT-JA-FILE-002/` | file | Java/Spring | PT / near miss | guard anchor，有 | 无 | clean-input 后 | 可，需重组 | 1 |
| PT-JA-REPO-001 | `datasets/synthetic/PT-JA-REPO-001/` | 3-layer repo | Java/Spring | PT / positive | source→sink anchor；另有 compile recipe | 无 exploit | clean-input 后 | 可 | 1 |
| PT-JA-REPO-002 | `datasets/synthetic/PT-JA-REPO-002/` | 3-layer repo | Java/Spring | PT / near miss | cross-file guard anchor | 无 | clean-input 后 | 可 | 1 |
| PT-PY-FILE-001 | `datasets/synthetic/PT-PY-FILE-001/` | file | Python/Flask | PT / positive | anchor，有 | 无 | clean-input 后 | 可，需重组 | 1 |
| PT-PY-FILE-002 | `datasets/synthetic/PT-PY-FILE-002/` | file | Python/Flask | PT / near miss | guard anchor，有 | 无 | clean-input 后 | 可，需重组 | 1 |
| PT-PY-REPO-001 | `datasets/synthetic/PT-PY-REPO-001/` | 3-layer repo | Python/Flask | PT / positive | source→sink anchor | 无 exploit | clean-input 后 | **已用于 pilot repo** | 1 |
| PT-PY-REPO-002 | `datasets/synthetic/PT-PY-REPO-002/` | 3-layer repo | Python/Flask | PT / near miss | cross-file guard anchor | 无 | clean-input 后 | **已用于 pilot repo** | 1 |
| SSRF-JA-FILE-001 | `datasets/synthetic/SSRF-JA-FILE-001/` | file | Java/Spring | SSRF / positive | anchor，有 | 无 | clean-input 后 | 可，需重组 | 1 |
| SSRF-JA-FILE-002 | `datasets/synthetic/SSRF-JA-FILE-002/` | file | Java/Spring | SSRF / near miss | guard anchor，有 | 无 | clean-input 后 | 可，需重组 | 1 |
| SSRF-JA-REPO-001 | `datasets/synthetic/SSRF-JA-REPO-001/` | 3-layer repo | Java/Spring | SSRF / positive | source→sink anchor；另有 compile recipe/stub | 无 exploit | clean-input 后 | 可 | 1 |
| SSRF-JA-REPO-002 | `datasets/synthetic/SSRF-JA-REPO-002/` | 3-layer repo | Java/Spring | SSRF / near miss | cross-file guard anchor | 无 | clean-input 后 | 可 | 1 |
| SSRF-PY-FILE-001 | `datasets/synthetic/SSRF-PY-FILE-001/` | file | Python/Flask | SSRF / positive | anchor，有 | 无 | clean-input 后 | 可，需重组 | 1 |
| SSRF-PY-FILE-002 | `datasets/synthetic/SSRF-PY-FILE-002/` | file | Python/Flask | SSRF / near miss | guard anchor，有 | 无 | clean-input 后 | 可，需重组 | 1 |
| SSRF-PY-REPO-001 | `datasets/synthetic/SSRF-PY-REPO-001/` | 3-layer repo | Python/Flask | SSRF / positive | source→sink anchor | 无 exploit | clean-input 后 | **已用于 pilot repo** | 1 |
| SSRF-PY-REPO-002 | `datasets/synthetic/SSRF-PY-REPO-002/` | 3-layer repo | Python/Flask | SSRF / near miss | cross-file guard anchor | 无 | clean-input 后 | **已用于 pilot repo** | 1 |
| SSTI-JA-FILE-001 | `datasets/synthetic/SSTI-JA-FILE-001/` | file | Java/Spring/FreeMarker | SSTI / positive | anchor，有 | 无 | clean-input 后 | 可，需重组 | 1 |
| SSTI-JA-FILE-002 | `datasets/synthetic/SSTI-JA-FILE-002/` | file | Java/Spring/FreeMarker | SSTI / near miss | source-vs-model guard anchor | 无 | clean-input 后 | 可，需重组 | 1 |
| SSTI-JA-REPO-001 | `datasets/synthetic/SSTI-JA-REPO-001/` | 3-layer repo | Java/Spring/FreeMarker | SSTI / positive | source→sink anchor | 无 exploit | clean-input 后 | 可 | 1 |
| SSTI-JA-REPO-002 | `datasets/synthetic/SSTI-JA-REPO-002/` | 3-layer repo | Java/Spring/FreeMarker | SSTI / near miss | cross-file source-vs-model anchor | 无 | clean-input 后 | 可 | 1 |
| SSTI-PY-FILE-001 | `datasets/synthetic/SSTI-PY-FILE-001/` | file | Python/Flask/Jinja2 | SSTI / positive | anchor，有 | 无 | clean-input 后 | 可，需重组 | 1 |
| SSTI-PY-FILE-002 | `datasets/synthetic/SSTI-PY-FILE-002/` | file | Python/Flask/Jinja2 | SSTI / near miss | source-vs-context guard anchor | 无 | clean-input 后 | 可，需重组 | 1 |
| SSTI-PY-REPO-001 | `datasets/synthetic/SSTI-PY-REPO-001/` | 3-layer repo | Python/Flask/Jinja2 | SSTI / positive | source→sink anchor | 无 exploit | clean-input 后 | **已用于 pilot repo** | 1 |
| SSTI-PY-REPO-002 | `datasets/synthetic/SSTI-PY-REPO-002/` | 3-layer repo | Python/Flask/Jinja2 | SSTI / near miss | cross-file source-vs-context anchor | 无 | clean-input 后 | 可作为 pilot 最小第 6 front | 1 |

#### 每个 real-world case

这些 repo 可包含很多自然探索面，但 ground truth 只标一个 CVE target。因此“有效 fronts”按**可可靠评分的 target**计为 1；未标注的真实问题不能直接当 FP，也不能虚增 benchmark 并行度。大仓更适合未来第二阶段外部有效性，不适合作为 9.17 前的第一条 N=4 matched block。

| 名称 | 路径 | 粒度 | 语言/框架 | 漏洞/标签 | 确定性 oracle | Runtime reproduction | Hidden GT | 可组合为 repo task | 有效 fronts |
|---|---|---|---|---|---|---|---|---|---:|
| PT-JA-REPO-CVE-2024-53677-VULN | `datasets/real_world/PT-JA-REPO-CVE-2024-53677-VULN/` | curated repo | Java/Struts | PT/upload / positive | anchor，confidence=medium | 无独立 PoC/test harness | clean-input 后 | portfolio 可；不宜混拼 | 1 |
| PT-JA-REPO-CVE-2024-53677-FIXED | `datasets/real_world/PT-JA-REPO-CVE-2024-53677-FIXED/` | curated repo | Java/Struts | PT/upload / near miss | migration guard，confidence=medium | 无统一可执行 oracle | clean-input 后 | portfolio 可；不宜混拼 | 1 |
| PT-PY-REPO-CVE-2024-32982-VULN | `datasets/real_world/PT-PY-REPO-CVE-2024-32982-VULN/` | full-ish repo | Python/Litestar | PT / positive | high-confidence anchor | 无随 case 封装的 exploit | clean-input 后 | portfolio 可 | 1 |
| PT-PY-REPO-CVE-2024-32982-FIXED | `datasets/real_world/PT-PY-REPO-CVE-2024-32982-FIXED/` | full-ish repo | Python/Litestar | PT / near miss | normpath/commonpath guard | 有上游 regression test `test_no_path_traversal_from_static_directory` | clean-input 后 | portfolio 可 | 1 |
| SSRF-JA-REPO-CVE-2023-3432-VULN | `datasets/real_world/SSRF-JA-REPO-CVE-2023-3432-VULN/` | curated repo | Java/PlantUML | SSRF / positive | high-confidence anchor | 无封装 PoC | clean-input 后 | portfolio 可 | 1 |
| SSRF-JA-REPO-CVE-2023-3432-FIXED | `datasets/real_world/SSRF-JA-REPO-CVE-2023-3432-FIXED/` | curated repo | Java/PlantUML | SSRF / near miss | `@` rejection guard | 无统一可执行 oracle | clean-input 后 | portfolio 可 | 1 |
| SSRF-PY-REPO-CVE-2025-2828-VULN | `datasets/real_world/SSRF-PY-REPO-CVE-2025-2828-VULN/` | large monorepo | Python/LangChain | SSRF / positive | high-confidence anchor | 无随 case 封装 PoC | clean-input 后 | portfolio 可；成本高 | 1 |
| SSRF-PY-REPO-CVE-2025-2828-FIXED | `datasets/real_world/SSRF-PY-REPO-CVE-2025-2828-FIXED/` | large monorepo | Python/LangChain | SSRF / near miss | opt-in guard | 有相关 requests-tool unit tests，非统一 CVE grader | clean-input 后 | portfolio 可；成本高 | 1 |
| SSTI-JA-REPO-CVE-2025-64087-VULN | `datasets/real_world/SSTI-JA-REPO-CVE-2025-64087-VULN/` | curated repo | Java/XDocReport/FreeMarker | SSTI / positive | high-confidence anchor | 无随 vuln case 的 test | clean-input 后 | portfolio 可 | 1 |
| SSTI-JA-REPO-CVE-2025-64087-FIXED | `datasets/real_world/SSTI-JA-REPO-CVE-2025-64087-FIXED/` | curated repo | Java/XDocReport/FreeMarker | SSTI / near miss | safer resolver guard | 有 `FreemarkerTemplateEngineSecurityTestCase` | clean-input 后 | portfolio 可 | 1 |
| SSTI-PY-REPO-CVE-2024-45053-VULN | `datasets/real_world/SSTI-PY-REPO-CVE-2024-45053-VULN/` | large repo | Python/Fides/Jinja2 | SSTI / positive | high-confidence anchor | 有一般 messaging tests，无封装 exploit | clean-input 后 | portfolio 可；成本高 | 1 |
| SSTI-PY-REPO-CVE-2024-45053-FIXED | `datasets/real_world/SSTI-PY-REPO-CVE-2024-45053-FIXED/` | large repo | Python/Fides | SSTI / near miss | removal-of-Jinja guard | 有 `test_message_template_render.py` 的 unsafe-template regression | clean-input 后 | portfolio 可；成本高 | 1 |

#### 当前 composite 的有效 work fronts

| Front | Agent-visible chain | 类型 | 可独立推进 | 确定性验证 |
|---|---|---|---|---|
| F1 | `/api/files/download` → `FileService` → `common/storage.py` | PT positive | 是 | `test_gt001_*` |
| F2 | `/api/documents/download` → `DocumentService._resolve_safe_path` → `common/io.py` | PT near miss | 是 | `test_nm001_*` |
| F3 | `/api/integrations/fetch` → `FetchService` → `common/http_client.py` | SSRF positive | 是 | `test_gt002_*` |
| F4 | `/api/webhooks/preview` → `WebhookService._is_safe_url` → `common/http_strict.py` | SSRF near miss | 是 | `test_nm002_*` |
| F5 | `/api/reports/preview` → `ReportService` → `common/templates.py` | SSTI positive | 是 | `test_gt003_*` |

**N=4 判断：**存在 5 条入口、数据流和 guard 语义不同的调查线，满足“至少 4 条可同时推进”的最低门槛；但 F1/F2 与 F3/F4 分别共享漏洞家族，代码链都很浅。因此它是 harness-feasibility benchmark，不是稳健的 coordination-performance benchmark。不要把 5 个 hidden target 等同于 5 个持续占满 Agent 的长任务。

### 2.2 Agent runtime

| 路径 | 当前用途 | 可复用 | Architecture-specific | 污染/缺口与所需修改 |
|---|---|---|---|---|
| `harness/agent_loop.py` | ReAct-like 多步 loop、tool dispatch、finding submit | 高 | 否，mode 只用于 prompt/tools | 不保存 transcript/assistant reasoning；没有 call timeout/retry；budget 在调用后 charge |
| `harness/policies/base.py` | S sequential、P/B/T thread-parallel policy | 高 | 是，薄 adapter | S/P/B/T 共用 `AgentRunner`，方向正确；M 不存在 |
| `harness/prompts.py` | 公共 audit prompt + B/T capability 增量说明 | 高 | 增量部分是 | base prompt 相同；不同 tool schema 自然增加输入 token，应记录 scaffold tokens |
| `harness/llm/client.py` | OpenAI-compatible Chat Completions gateway、mock client | 高 | 否 | temperature/max_tokens 硬编码且不入 manifest；seed 未传；无 timeout/retry/cost；env `\r` 未清理 |
| `harness/runner.py` | workspace、policy、budget、merge、grader、summary | 高 | 只通过 policy | `merge_findings()` 只是 concat，不是 dedup；没有 block runner和统一 comparison |
| `run_experiment.py` | 单 run CLI | 高 | mode 参数 | 可跑 S/P/B/T；`--model` live 时被忽略；预算只能选 default/smoke，不能冻结任意 block config |

仓库没有另一套本地可复用的 planner/worker/reviewer/verifier/specialist/router 实现。DeepAudit、IRIS、OpenAnt 的核心系统源码不在本仓库；`scripts/` 主要是外部系统的 clean-input、HTTP 调用、polling 和 artifact collection，因此不能直接当作 CoordAudit Agent runtime。

### 2.3 Tools

| 路径/工具 | 当前能力 | 可复用 | 风险/修改 |
|---|---|---|---|
| `harness/tools/specs.py` | `list_files/read_file/write_file/run_shell/submit_findings` | 高 | finding item 无字段级 JSON schema；建议所有条件统一收紧 |
| `harness/tools/sandbox.py` | private path check、scratch、shell、submission | 中 | Python file API 隔离有效；shell 不是 OS sandbox，且 `shell=True`；必须 bwrap/argv allowlist + env scrub |
| `run_shell` | 可间接执行 `rg`、Python tests、build 命令 | 中 | 搜索/测试事件难规范化；网络禁用只是环境变量，不是真正禁网 |
| Repo search/read | `list_files/read_file`，shell 内可用 `rg` | 高 | 建议新增所有条件共享的 typed `search_repo`，便于 duplicate 计量 |
| AST/static analysis | 无通用 wrapper | 缺失 | Pilot 不必新增 CodeQL/Bandit；避免引入额外 compute confounder |
| Test/build | shell 可执行；composite 有 smoke/private semantic tests | 部分 | 需要 typed event 或至少给 shell test attempt 分类 |
| Exploit reproduction | 无专用工具 | 缺失 | Pilot 用 deterministic evaluator-side regression + Agent test-attempt 事件即可 |
| Finding submission | 已有 `submit_findings` | 高 | 需 schema validation、finding ID、evidence refs、deterministic dedup |

DeepAudit 脚本（如 `scripts/run_deepaudit_repo_experiment.sh`、`run_deepaudit_boundary_agent_slots.sh`）可复用 clean ZIP、run manifest、task polling 和 metrics 命名经验，但它们调用 DeepAudit 专用 API、携带 target-vulnerability/target-files 语义，会污染不同 coordination condition，不能直接嵌入本 pilot。`scripts/run_llm_prompt_capture.py` 展示了保存 request/prompt/response/seed 的较好做法，可把这一做法移植到统一 gateway。

### 2.4 Coordination

| 机制 | 路径 | 现状 | 分类 | 可复用与缺口 |
|---|---|---|---|---|
| P isolation | `workspace.py`、`sandbox.py`、`test_harness.py` | 每 Agent target/scratch 副本；工具 schema 无 shared API | 部分已有 | Python API 层通过；shell/host/env 层未隔离 |
| Raw store | `shared_fs.py`、`BLACKBOARD_TOOLS` | list/read/create/mkdir；create-only，可 append；无 message/task/claim/owner/roster | **Raw shared store** | 可直接复用；`append` 是 generic write 行为，但必须保持不解析 task semantics |
| Typed backlog | `task_board.py`、`TEAM_TOOLS` | create/list/claim/release/complete；owner/status/dependency/result_artifacts | **Structured coordination** | claim 在当前单进程 thread runner 内原子；没有 claim-conflict event，跨进程不原子 |
| Messaging | `TaskBoard.send_message/list_messages` | T-only P2P/`*` broadcast | Structured coordination | `message_read` 只记 count，不能知道读了哪些 message；read state 不持久 |
| Artifacts | `publish_artifact/list_artifacts` | T-only publish metadata | Structured coordination | peer 没有 `read_artifact`，当前实质 write-only；建议 pilot 收窄/修正 |
| Worker ID | `paths.py:agent_id_for()` | `agent_001`…`agent_032` | Observer identity | 可复用；B 不提供 peer directory，符合要求 |
| Manager/queue/lease/CAS | 无 | M、lease、crash recovery、跨进程 CAS 均无 | 缺失 | N=4 pilot 不需要；M4 暂不加入 |

特别说明：B 的 prompt 只说 `/shared` 是其他 concurrent process 可见的持久目录，没有任务、leader、mailbox 或分工模板，符合本次 `B-aware` 定义。T 的 typed task/message/artifact 明显属于 developer-provided semantics，不能与 B 合并报告。

### 2.5 Logging

| 路径 | 已有字段/事件 | 可复用 | 当前不能回答什么 |
|---|---|---|---|
| `harness/events.py` | timestamp、run_id、agent_id、event_type、payload、token_usage、target；JSONL + thread lock | 高 | 无 event_id、step_id、call_id、parent refs、duration、status |
| `agent_loop.py` | agent start/finish、LLM usage、tool args、budget/error | 中到高 | 不保存 prompt/assistant output/raw response/tool result；无法还原 hypothesis 形成原因 |
| `shared_fs.py` | path、creator event、hash、bytes、小内容 inline、snapshot | 高 | analyzer 只算精确 path 的 cross-agent read；append lineage 不完整 |
| `task_board.py` | task create/claim/release/complete、message send/read、artifact publish | 中 | claim failure 不记专用事件；message read 无 IDs；artifact 无 read；task result语义弱 |
| `runs/*` | run_manifest、events、per-agent findings、merged findings、evaluation、summary | 高 | 现有 4 run 全是 mock；没有 live/N4 trace、metrics.json 或 block summary |
| 旧 `artifacts/` | 49 个 run manifest、35 个 metrics.json、系统专用 task events/results | 中，字段经验可复用 | 没有统一 JSONL schema；系统间 token/cost/event 口径不一致 |

当前只能重建“哪个 Agent 何时调用了哪个工具/读了哪个文件、用了多少 provider-reported tokens、是否写/读同一 shared path”。不能可靠重建“因为看见哪条 message/evidence 而形成哪个 hypothesis，后续哪个 Agent采用并验证”。缺少：稳定 event/evidence/message ID、LLM output/transcript、read receipt、finding→evidence refs、verification event 和 parent/causal links。

### 2.6 Budgeting

`harness/budget.py` 已有 global input/output cap、per-agent cap、max LLM calls、reasoning/cached token字段和 thread lock，属于可复用骨架。但 `AgentRunner` 先调用 provider，再 `charge()`：并发请求已经产生费用后才发现超限，且被拒绝的 usage 不进入正常 `llm_call` 统计。wall-clock 只在 Agent 启动前检查，不会中止运行中的 provider call。当前也没有 tool budget、美元成本或 retry/failed-call accounting。

现有 manifest 的 default 是 200k input、80k output、40 calls、600 秒；但相同 `max_steps` 会使 S1 最多只跑 8/12 次、P4 最多跑 32/48 次，S1 实际无法使用团队全局 call budget。这是必须修复的公平性问题。

### 2.7 Evaluation 与历史结果

- `evaluator/score.py` 能输出 TP/FP/FN、precision/recall/F1、duplicate findings 和 near-miss FP，且不用 LLM judge，方向正确。
- positive matcher 当前允许 `file+category` 直接命中，定义在 ground truth 的 `required_source_tokens_any` 没有使用；容易把浅层猜测算作 TP。
- `verified_findings` 只检查 Agent 提交的 `reproduction.successful=true`，即使是 FP 也会计数；它不是 verifier 结果。
- `merge_findings()` 保留所有重复项；grader只是把同一 GT 的后续命中标为 duplicate。当前 precision 也没有因这些 duplicate submission 受罚。
- `experiments/emergent_coordination/runs/` 现有 single/parallel/raw_blackboard/structured_team 四次 run 均为 2026-09-13 的 `mock` N=1/2，全部 0 findings；只能证明生命周期和 artifact layout，不能证明 security 或 coordination behavior。
- 仓库已有 DeepAudit/IRIS/OpenAnt/Architecture Attribution 的丰富历史结果与统一入口 `reports/cross_system/canonical_results.tsv`。这些结果说明 full-repo broad scan 存在 off-target 和高成本问题，但其系统、prompt、tools、预算口径不同，不能当作本 pilot baseline。

#### 文档、配置和历史证据入口

| 资产 | 路径 | 当前作用 | 对 N=4 pilot 的复用 |
|---|---|---|---|
| 项目术语/边界 | `CONTEXT.md` | 定义 Case、Target Vulnerability、Near-miss、Clean Input、CoordAudit、Raw Shared Store | 高；沿用术语和隔离边界 |
| 评测约束 | `agent_eval_learning_rules.md` | 冻结配置、盲评、成本、失败分类、finding记录 | 高；作为 protocol gate |
| 总体方法 | `llm_audit_system_learning_method.md` | 分阶段学习/诊断/benchmark方法 | 中；不把 feasibility写成正式评测 |
| CoordAudit 任务定义 | `docs/research/coord_audit_task.md` | 定义 S/P/M/B/T、fixed-global、work-front目标 | 高；本计划是其 N=4 落地 |
| 既有多 Agent 调研 | `docs/research/multi_agent_coordination_prior_art.md` | 已完成 prior-art、预算、benchmark和架构映射 | 高；无需再次大规模文献调研 |
| 独立实验线 ADR | `docs/adr/0001-architecture-attribution-as-independent-experiment-line.md` | 防止不同归因实验混写 | 中到高；CoordAudit保持独立结果线 |
| 报告规范 | `reports/README.md` | `artifacts/` 存证据、`reports/` 存人读结论 | 高；pilot稳定后建立 `reports/systems/coordaudit/` |
| Canonical 历史结果 | `reports/cross_system/canonical_results.tsv`、`overall_report.md` | 收口 OpenAnt/DeepAudit/IRIS/旧 Architecture Attribution | 只作风险背景，不能合并评分 |
| 外部系统运行脚本 | `scripts/run_deepaudit_*.sh`、`run_iris_smoke_cases.sh`、`iris_prepare_and_preflight.sh` | clean input、HTTP/task polling、manifest、metrics | 复用约定/字段，不复用 architecture-specific runtime |
| 模型配置 | `.env_deepseek` | provider/model/base URL/API key环境变量 | 接入可复用；secret不归档，CR需清理 |
| Git历史 | `main` 现有 5 个提交，HEAD `5221728` | 已提交仓库收口历史 | CoordAudit `experiments/` 当前未跟踪，单独 git commit字段不足 |

历史 evidence 目录中共找到 49 个 `run_manifest.json`、35 个 `metrics.json`，但没有统一的 `*.jsonl` event log；另有系统专用 task-event JSON。它们适合作为字段设计样本，不适合直接汇入新的多 Agent event stream。当前工作树已有其他用户修改和未跟踪资产，本任务没有改动或清理它们。

测试实况：`python3 -m unittest discover -s experiments/emergent_coordination/tests -t . -v` 的 35 项通过。根 README 中 target-visible smoke 命令若从仓库根直接执行会因 `ModuleNotFoundError: app` 失败；进入 `repositories/repository_pilot_v0/` 后执行，6 项通过。文档应修正工作目录。另有 `requests`/`urllib3` 版本 warning，不影响本次测试结果，但应进入 environment manifest。

## 3. Gap Analysis

| 能力 | 级别 | 代码事实 | Pilot 最小补齐 |
|---|---|---|---|
| S/P/B/T 同一 Agent loop | 已有 | `AgentRunner` + `CoordinationPolicy` | 保持，不重构 |
| P isolation | 部分已有 | private copy/scratch 有测试；shell 可见宿主机和继承 env | bwrap `--unshare-net`、只 bind private workspace/必要 runtime、清理 secret env；增加越界/跨 Agent/网络测试 |
| B raw store | 已有 | generic list/read/create/mkdir；无 structured API | 冻结 B-aware prompt/tool schema；禁止新增 parser、namespace、通知、CAS/lock |
| T atomic claim | 部分已有 | `threading.Lock` 对单 runner 内线程原子 | N=4 可用；补 claim-conflict 事件、task result；明确“不支持跨进程” |
| Global accounting | 部分已有 | usage 字段齐，但 post-call charge 可超支 | 调用前原子 acquire call permit；pilot 用 calls + per-call output hard proxy；所有成功/失败/retry均记账 |
| API cost | 缺失 | run history 明确不写价格 | manifest 冻结当日 input/cache/output/reasoning 单价或 provider billed cost，生成 derived cost 与 unknown 标志 |
| Event logging | 部分已有 | JSONL 有基础事件 | event/step/call/op ID、duration、outcome、content/artifact hash、prompt/tool-schema hash、transcript |
| Evidence lineage | 缺失 | finding evidence 是自由文本，T reads 不可定位 | evidence refs、message/shared origin、read receipt、finding/verifier links；允许明确 adoption，另做时序推断 |
| Duplicate-work measurement | 缺失 | 只有 duplicate findings | 规范化 file/search/hypothesis/source→sink/test fingerprints，输出总量与分项 ratio |
| Work allocation/utilization | 部分已有 | start/finish 和 per-agent budget存在 | per-agent active duration、module/hypothesis fronts、idle、usage Gini、peak concurrency |
| B behavior metrics | 部分已有 | shared read/write + cross-agent exact-path read | first RAW latency、多读 key、lexical task/owner/mailbox/verify indicators；只报告行为证据 |
| T metrics | 部分已有 | create/claim/release/complete 有事件 | claim conflicts、abandoned、duplicate task、load balance、result adoption |
| Deterministic merge/dedup | 缺失 | 当前仅 concat | 固定 fingerprint、保留 provenance、所有条件同一算法 |
| Finding schema enforcement | 部分已有 | prompt 示例 + 宽松 tool schema | JSON Schema 校验，缺字段作为 invalid submission，不由 LLM aggregator修复 |
| Deterministic verification | 部分已有 | private semantic tests存在 | 在 run snapshot 上执行、生成 verification events；不得信任自报 successful |
| Model reproducibility manifest | 部分已有 | model/seed/start/git commit | provider、base URL host、request params、seed support、reasoning config、prompt/tool schema/version/hash、dependency versions |
| Retry/provider timeout | 缺失 | client无 timeout/retry | 统一很小的固定策略；失败调用计预算和事件 |
| M4 | 缺失 | 只有 future-policy 注释 | 本 pilot 不实现 |

### 关键 confounders

- `system_prompt()` 和 `user_prompt()` 具有 mode-specific 增量文字，T/B 又有更长 tool schema。这是 treatment 的必要组成，但它会增加输入 token；必须把实际输入 tokens 和 mandatory scaffold bytes/tokens 单列。
- T 当前同时提供 task、message、broadcast 和不可读 artifact，而建议的核心 treatment 是 typed claim。若保留全部接口，`T-P` 估计的是整套 structured team capability，不是 atomic claim 单一效应。Pilot 可以接受，但必须如此命名；最小化方案见第 8 节。
- B 的 `append=true` 比纯 overwrite store 更利于共享日志且减少 lost update。它仍是 generic storage，但属于 substrate 设计选择，必须冻结并在 manifest 明示。
- S 与 N=4 若共用相同 per-agent `max_steps`，并不拥有相同 team opportunity；必须让 S 的 step ceiling 等于 team 总 call permits。
- 当前 seed 只写 manifest，不传 provider；不能把不同 seed 标签解释为模型随机种子。
- `run_shell` 允许 Agent 修改 target copy，和 `write_file()` 的“target read-only”承诺冲突；还可经宿主路径制造跨条件/跨 Agent共享。
- `score.py` 的宽匹配、Agent 自报 verification 和未去重 merge 会改变 architecture outcome，必须在第一条 live block 前冻结修正。

## 4. Recommended N=4 Architecture

不新建 framework，沿用当前文件边界，只把缺失的公共层补齐：

```text
BlockRunner（新增很薄的一层，只冻结并启动 matched runs）
└── AgentLoop（现有 AgentRunner）
    ├── core audit prompt（现有 COMMON_INSTRUCTIONS + 严格 finding schema）
    ├── common tools（list/read/search/test/scratch/submit）
    ├── model gateway（现有 OpenAICompatibleClient，加 timeout/usage/config）
    ├── global budget arbiter（现有 BudgetTracker，加 pre-call permit）
    ├── event/evidence recorder（现有 EventLog，加 IDs/links/duration）
    └── coordination adapter（现有 CoordinationPolicy）
        ├── none_single          → S1
        ├── independent_parallel → P4
        ├── raw_store            → B4-aware
        ├── structured_backlog   → T4
        └── manager_worker       → M4，暂不实现

Run-final common pipeline
├── schema validation
├── deterministic merge/dedup
├── hidden deterministic verification/scoring
├── trace/duplicate/allocation analysis
└── matched-block comparison
```

核心隔离合同：

| 层 | S1 | P4 | B4 | T4 |
|---|---|---|---|---|
| Model/core audit prompt | 相同 | 相同 | 相同 | 相同 |
| Target/private scratch | 1 份 | 4 份完全隔离 | 4 份完全隔离 | 4 份完全隔离 |
| Common audit tools | 相同 | 相同 | 相同 | 相同 |
| Runtime communication | 无 | 无 | generic store only | typed backlog + 可选 P2P message |
| Peer roster | 无 | 无 | 无 | 由稳定 pseudonym 支持定向 message；不设 leader |
| Final intake/grader/dedup | 相同 | 相同 | 相同 | 相同 |
| Team budget | 同一全局上限 | 同一全局上限 | 同一全局上限 | 同一全局上限 |

T4 建议保留 `create_task/list_tasks/claim_task/release_task/complete_task` 与现有 `send_message/list_messages`，但把 `complete_task` 扩为可携带小型 `result`/evidence refs。当前 `publish_artifact/list_artifacts` 因没有 peer read 能力而语义残缺；第一版要么补 `read_artifact` 并计 lineage，要么更简单地从 pilot tool surface 移除。不要把这些接口复制给 B。

M4 暂缓。仓库没有 manager role、分派权限、worker→manager result channel 或 manager bottleneck metrics；此时新增 M 会同时改变 prompt、权限、消息拓扑和 aggregation，超出最小 feasibility block。

## 5. Benchmark Selection

### 选择

使用当前 `repository_pilot_v0`，不先切换到 real-world 大仓，也不把 36 个 case 当成一个目录直接交给 Agent。

理由：

- 已经是匿名、agent-visible 的正常 Flask repo，private provenance 明确来自 5 个既有 synthetic repo case。
- 具有 5 条独立 HTTP entry point、3 个漏洞家族、3 positive、2 near miss，所有链均跨 route/service/helper 文件。
- private deterministic semantics tests 已通过，能够区分 vulnerable chain 与 guard-protected near miss。
- 体积小，适合低成本观察 P 重复导航、B shared-store 使用和 T task claim，不会被依赖安装/构建噪声主导。
- 已有 manifest、clean workspace、leak tests、grader、mock runner和 run layout，新增成本最低。

### Ground truth 与 verification

- Hidden findings：`GT-001` PT、`GT-002` SSRF、`GT-003` SSTI。
- Near misses：`NM-001` protected file read、`NM-002` protected outbound request。
- Deterministic source：`evaluator_private/repository_pilot_v0/ground_truth.json`。
- Deterministic behavior tests：`tests/test_repository_semantics.py`，应改为针对每个 run 的 frozen target snapshot 执行并输出 oracle IDs，而不是只在开发树上运行。
- Agent-visible `tests/test_app_smoke.py` 只测基本路由/缺参，不泄露漏洞答案。

### 是否需要最小改造

第一条 feasibility block **不改 benchmark 内容**，先用行为 trace 测量 task starvation。预注册 starvation 判据：在前 50% 全局 call budget 内，可识别的 unique semantic fronts 少于 4，或至少 2 个 Agent 超过一半活动都落在已被其他 Agent覆盖的同一 front，则标记 benchmark undersized，pilot 仍可用于 harness 结果，但不可解释 T/B 效果。

如果发生 starvation，最小改造不是新造大仓，而是把已存在的 `SSTI-PY-REPO-002` 匿名接入同一 Flask app，形成第 6 条 SSTI near-miss 链，并给 private oracle 增加对应 guard test。这样得到 3 positive + 3 near miss、6 fronts，仍只复用现有资产。改造后必须提升 repository version，不能与 v0 run 混合比较。

Real-world repo 暂不进入最小 block：每个只有一个标注 target，大仓中的 off-target finding 又未完整标注，会破坏 precision/duplicate-work 解释。它们应在 harness 可行后作为第二 benchmark line，而不是 9.17 前的阻塞项。

## 6. Experimental Matrix

| Condition | N | Coordination | Budget | Main purpose | Pilot 状态 |
|---|---:|---|---|---|---|
| S | 1 | none | same global | single baseline | 必跑 |
| P | 4 | none during run | same global | sampling | 必跑 |
| B | 4 | raw store | same global | emergent shared-state behavior | 必跑，B-aware |
| T | 4 | typed claim | same global | structured coordination | 必跑 |
| M | 4 | manager-worker | same global | optional centralized baseline | **不进入最小 block** |

### 最省成本且有信息价值的规模

阶段 A：1 repo × S1/P4/B4/T4 × 1 matched block（建议 block seed/replicate `17`）。它只回答机械可行性和可观察性。

阶段 B：仅当阶段 A 同时满足无 capability leak、四条件都正常结束、预算/事件完整、至少 4 fronts 被触达、B 有真实 store operation、T 有真实 claim 后，再用第二个 block（建议 `29`）重复。若 provider 不支持 seed，字段改记 `replicate_id`，不得声称 deterministic seed。

M4 只有在 S/P/B/T 的 block 已经产生完整 trace，且 manager adapter 可在不引入专属审计知识/工具的前提下加入时才做；不作为 9.17 成功条件。

### Pilot global budget

当前 provider usage 不能支撑严格的 pre-known input-token hard cap，因此 pilot 主预算明确使用允许的 proxy：

```text
max_total_model_calls_per_condition = 32
max_output_tokens_per_call = 1024
S1 max_steps = 32
P4/B4/T4 max_steps_per_agent = 8
max_common_tool_calls_per_condition = 160
per_shell_call_timeout_seconds = 30
wall_clock_safety_ceiling_seconds = 600
```

所有 call permit 必须在请求前原子获取；provider 请求失败和 retry 也消耗 call permit。S1 因此能使用完整 32-call team budget，P/B/T 最多 4×8。`global_input_token_cap` 可保留为“完成一次 call 后、发下一次前”的软停机线，但不得称作严格 hard cap。实际 input/output/cached/reasoning tokens 全量记录；reasoning 未返回时写 `null`，不能写 0。

如果实现了可靠 tokenizer 估计，可在调用前 reserve `estimated_input + max_output`，完成后按 actual refund；这不是第一条 pilot 的必要条件。不要为 pilot 实现复杂 scheduler。

同一 block 冻结：provider、exact model string、temperature=0、max output、reasoning setting、tool schema、common prompt、condition delta prompt、timeout/retry、价格快照和依赖环境。当前 `deepseek-v4-pro` 只作为现有接入候选；先做 1 次不计入 block 的 live compatibility smoke。历史 manifest 已出现模型/provider 值尾随 `\r`，gateway 必须 trim 后同时记录 raw/resolved 值。

## 7. Metrics

### 7.1 Security outcome

```text
unique_true_findings
false_positives
false_negatives
precision / recall / F1
near_miss_false_positives
deterministically_verified_findings
invalid_finding_submissions
duplicate_findings_before_dedup
```

TP 必须匹配 category + source/dataflow + sink/guard anchor，而不只是 filename/category。`deterministically_verified_findings` 只来自 evaluator-side oracle，不接受 Agent 自报。另保留每个 Agent 原始 findings 和 dedup provenance。

### 7.2 Resource use

```text
input_tokens / cached_input_tokens / output_tokens / reasoning_tokens_or_null
total_tokens（同时给 raw 与 billed口径）
API cost 与 price snapshot
model calls（成功/失败/retry）
tool calls，按 list/read/search/shell/test/coordination 分类
read bytes / shared bytes / message bytes
wall clock / summed agent active seconds / peak concurrency
termination reason
```

对每个 Agent 和整个 team 同时报告；T/B 的 coordination payload bytes 与进入 LLM context 后产生的 input tokens分开。

### 7.3 Duplicate work

建立四类 normalized fingerprint：

- file：规范化 repo-relative path；若支持 range/function，再加 symbol/range。
- search：小写、空白归一的 pattern + scope；对 `rg/grep` shell 命令做解析，优先使用统一 `search_repo` tool。
- hypothesis：category + source file/function + sink file/function；由 finding/assistant transcript 提取，低置信提取单列。
- reproduction：normalized test/exploit command + target chain/oracle ID。

对每个 fingerprint `f` 计算接触它的 distinct Agent 数 `a_f`：

```text
duplicate_units = Σ_f max(0, a_f - 1)
total_cross_agent_units = Σ_f a_f
duplicate_work_ratio = duplicate_units / total_cross_agent_units
```

分别输出 `file_duplicate_ratio`、`search_duplicate_ratio`、`hypothesis_duplicate_ratio`、`reproduction_duplicate_ratio` 和合并值。shared/message/task 工具本身不计审计重复劳动；同 Agent 重读另报 `within_agent_repeat_ratio`。Pilot 主比较为 P4 vs B4 vs T4，S1 只作参考。

### 7.4 Allocation

按 Agent 输出：实际触达 module/files、hypothesis/front、首次/最后活动时间、active duration、model/tool/token usage。Team 输出：unique fronts、front×Agent matrix、idle fraction、usage Gini、front coverage over time、specialization entropy。specialization 以实际行为聚类/集中度描述，不依据 Agent 自称角色。

Task-starvation 主要看：前 25/50/75% budget 时的 active unique fronts、每个 Agent 的新增 evidence 率、重复率与 idle。不要用“4 个 Agent 都发了请求”替代有效并行度。

### 7.5 Knowledge propagation

最小可重建链：

```text
origin event/artifact/message/shared-write
→ consumer read receipt
→ consumer 后续 tool/hypothesis/finding event
→ verifier event
```

输出 cross-agent evidence exposures、adoptions、adoption latency、adopted findings、adopted false/unsupported claims、correction events。Pilot 的 adoption 采用两层口径：Agent 显式 `evidence_refs/informed_by` 为强证据；读取后时序/内容相似为推断证据，必须分开报告。

### 7.6 B-specific behavior

```text
first_cross_agent_read_after_write_seconds
shared_keys_created / shared_reads / shared_bytes
keys_read_by_2plus_agents
creator→reader edges
task-like / owner-like / claim-like / verify-like / mailbox-like lexical observations
agent-specific namespaces observed
shared finding/evidence artifacts observed
```

分类器只在 key/path/content 中查找预注册 pattern，并保留原始证据引用。结果措辞使用“观察到 task-like artifact”，不能自动写“emergent protocol formed”。B 未使用 store 也是有效 intention-to-treat 结果。

### 7.7 T-specific behavior

```text
tasks_created / claimed / completed / released / abandoned
claim_conflicts
duplicate_task_creation（description semantic fingerprint）
time_to_first_claim / queue wait / task duration
task result read/adoption
tasks_per_agent / completion per agent / load-balance Gini
message send/read/adoption（若启用）
```

核心检验是 T4 的 audit-work duplicate ratio 是否低于 P4/B4，同时没有因 task overhead 显著降低 unique fronts 或 verified findings。单 seed 只做描述，不做优劣结论。

### 7.8 Optional M-specific behavior

若后续加入 M4，记录 manager token share、worker idle/queue time、assignment→start latency、reassignment、manager fan-in、worker result丢失/压缩和 critical path。Manager 是 N=4 的一个 slot并计全局预算。

## 8. Required Code Changes

### P0 — pilot 必须

| 文件 | 需要修改什么 | 为什么 | 预计风险 |
|---|---|---|---|
| `harness/budget.py`、`agent_loop.py` | 增加调用前原子 call permit；失败/retry记账；S1 与 team 使用不同 max_steps但相同总 permits | 防并发超支并让 S1 真正拥有 team budget | 中：permit 释放/终止处理错误会死锁或漏账 |
| `harness/llm/client.py`、`run_experiment.py`、manifest | CLI/manifest 冻结 provider、resolved model、temperature、max tokens、seed support、reasoning config、timeout/retry；trim CR；记录 usage/raw response metadata与价格快照 | 当前 seed无效、参数不入 manifest、历史模型值带 `\r`、无 cost | 中：不同 OpenAI-compatible provider字段差异 |
| `harness/tools/sandbox.py`、`workspace.py` | 使用现有 `bwrap` 只暴露 Agent private root和必要只读 runtime，`--unshare-net`，清理 API key/host env；shell target只读；各 condition按 policy决定是否有 shared mount/API | P/hidden GT/无网络目前只在字符串层承诺 | 高：Python解释器/动态库 bind 不完整会影响 tests；必须用 isolation tests锁定 |
| `harness/events.py`、`agent_loop.py`、`sandbox.py` | 添加 monotonic sequence、event_id、step_id、call_id/op_id、parent refs、start/end/duration/outcome；保存每 Agent transcript或等价 request/response artifact（敏感字段脱敏）；合并 dispatcher 与 sandbox 对同一操作重复写入的 `tool_call`，或用同一 `op_id` 明确关联并在统计时只计一次 | 无法重建 hypothesis/evidence lineage 和 active time；当前部分工具调用会被双记，`tool_calls` 不能直接用于条件比较 | 中：日志量、并发顺序、去重口径与敏感信息处理 |
| `shared_fs.py`、`task_board.py` | B write版本/append origin；T message read记录 message IDs，claim失败发 `task_claim_conflict`；task complete携带 result/evidence refs；修复或移除不可读 artifact API | B/T adoption与T指标当前不可重建 | 中：不能把 T semantics 泄给 B |
| `harness/tools/specs.py`、`prompts.py` | 所有条件统一收紧 finding JSON schema，增加 finding_id、evidence refs、reproduction artifact；可增加共同 `search_repo` tool | 防无结构输出并支持 duplicate/lineage | 中：schema过严可能增加 invalid submissions，必须先 mock/live smoke |
| `harness/runner.py`、`evaluator/score.py` | deterministic finding fingerprint、merge/dedup并保留 submitted_by；positive matcher实际检查 source/sink；verification不信任自报 | 当前 outcome 可被浅 filename猜测和自报 verification污染 | 高：grader变化会改变分数；需冻结版本并补 regression tests |
| `tests/test_repository_semantics.py` 或 evaluator-private runner | 对 run snapshot 运行 private oracle，输出 oracle ID、命令、exit code、时间、finding link；Agent不可见 test名称/内容 | 产生真正 deterministic verification event | 中：import path/cache必须指向本 run，不得误测开发树 |
| `analysis/analyze_run.py` | 实现第 7 节 duplicate、allocation、B、T、lineage和cost指标，写 `metrics.json` | 当前只有 token/基础 event count | 中：hypothesis semantic fingerprint只能作为近似，需保留分项 |
| 新增薄 `run_block.py` 或等价 | 从一个 frozen block config 启动 S/P/B/T，固定 config hash、运行顺序、共同预算并生成 block manifest | 手工四条命令易漂移，无法证明 matched block | 低到中：不要把它发展成新 orchestration framework |
| Tests | 增加 N=4 budget race、shell escape/network/env、B/T tool leak、claim conflict、message receipt、dedup、source-aware grader、snapshot oracle、block-config equality 测试 | 现有 35 测试未覆盖上述关键失效 | 低 |

### P1 — 强烈建议

| 文件 | 需要修改什么 | 为什么 | 预计风险 |
|---|---|---|---|
| `analysis/compare_runs.py`（新增） | 汇总一个 block 为 CSV/Markdown，检查 config hash一致，输出 P/B/T duplicate和trace | 降低手工比较错误 | 低 |
| `repositories/repository_pilot_v0/requirements.txt`、environment manifest | 冻结/记录实际 Python、OpenAI SDK、Flask/Jinja/requests版本 | 当前 requirements 用范围，已出现 requests dependency warning | 低 |
| `README.md` | 修正 target smoke 的 cwd 和 analyze_run 的实际 run path | 当前根目录命令可复现失败 | 低 |
| Composite v1（仅 starvation 后） | 匿名接入现有 `SSTI-PY-REPO-002` 作为第 6 near miss，更新 private provenance/oracle/version | 增加 N=4 余量并平衡 positive/near miss | 中：benchmark version变化，不得与v0混跑 |
| Prompt/tool scaffold accounting | 保存 common与condition增量 prompt/tool-schema bytes/token估计 | 解释 T/B 固定开销 | 低 |
| 第二 matched block | seed/replicate 29，反转/随机化 condition运行顺序 | 排查单次provider抖动 | 低；增加 API 成本 |

### P2 — 正式 N=16 再做

| 文件/组件 | 需要修改什么 | 为什么 | 预计风险 |
|---|---|---|---|
| `manager_worker` policy | 1 manager+3/15 worker、严格 star权限、manager metrics | M baseline | 高：同时引入多项 treatment |
| SQLite/event backend | 跨进程 atomic task、lease、recovery、durable queue | N=16/多进程稳定性 | 中到高；N=4 thread pilot不需要 |
| repository-v1 / portfolio-v1 | 12–20 N16 work fronts、4–6 CWE、shared semantics、更多可执行 oracle | 当前 v0 对 N=16 明显 task-starved | 高：标注与有效性工作大 |
| Tool compute arbiter | build/static/test CPU秒和分类额度 | 正式 fixed-global 需要控制替代性compute | 中 |
| Semantic lineage/dedup model | 人工校准或冻结 embedding/规则 | 提高 hypothesis/adoption识别 | 中；不得引入未计费 judge confounder |
| 多 provider/model block | 正式模型复现与模型×架构交互 | 避免廉价 pilot外推 | 高成本，不属于 feasibility |

## 9. Exact Run Procedure

以下流程先完成 P0，再执行 live block。命令只使用仓库当前真实存在的 CLI；需要新 `run_block.py` 的自动化属于第 8 节待实现项，不在这里伪造命令。

### 9.1 Environment setup 与静态检查

从仓库根目录运行：

```bash
git status --short
python3 -m unittest discover -s experiments/emergent_coordination/tests -t . -v
```

目标 smoke 必须切到目标目录，当前从仓库根直接用 README 命令会导入失败：

```bash
cd experiments/emergent_coordination/repositories/repository_pilot_v0
python3 -m unittest discover -s tests -v
```

回到仓库根，再跑 private semantics regression：

```bash
cd /home/lqs/coordaudit
python3 -m unittest experiments.emergent_coordination.tests.test_repository_semantics -v
```

运行 case 完整性检查：

```bash
find datasets -name case.yaml | wc -l
find datasets -name ground_truth.json | wc -l
find datasets -mindepth 3 -maxdepth 3 -name README.md | wc -l
```

预期均为 36。P0 后再跑新增 isolation/budget/grader tests；任一失败则不发 live block。

### 9.2 Benchmark freeze

记录并写入 block manifest：

- `repository_pilot_v0` manifest hash；
- agent-visible target tree hash；
- private ground-truth/provenance hash；
- private oracle test hash；
- git commit + dirty-worktree digest；
- common prompt hash、每个 condition delta hash、各 tool schema hash；
- environment/package versions。

不得把 `evaluator_private/`、原始 `datasets/*/case.yaml`、ground truth 或答案 README 放进 Agent bind mount。每个 run 使用新目录，不能复用 scratch/shared/task state。

### 9.3 Model compatibility smoke

只读取当前环境配置，不把 key 写入 manifest/log：

```bash
source .env_deepseek
python3 experiments/emergent_coordination/run_experiment.py \
  --mode single --agents 1 --live --smoke-budget --max-steps 4
```

该命令当前真实存在，但只有在 P0 的 CR trim、timeout、sandbox、request logging 完成后才建议执行。Smoke 不计入 matched block。检查 resolved model string、tool calling、usage字段、reasoning token可用性、finish reason和 cost计算；失败则停止，不切换某一个 condition 的模型。

### 9.4 Freeze run config

在 manifest 中固定第 6 节参数。由于当前 CLI 的 budget 来自 `manifests/repository_pilot_v0.json`，P0 后应让四条命令读取同一 block config/hash；在这之前不要手工临时改四次预算。运行顺序由 block seed预先随机化并记录，不能看结果后调整。

### 9.5 Execute one matched block

下面是现有 CLI 能表达的真实调用形态。`<BLOCK_RUNS_DIR>` 必须替换为同一新 block 目录；S 用 32 steps，N=4 条件每 Agent 8 steps，使总 model-call opportunity 都是 32：

```bash
python3 experiments/emergent_coordination/run_experiment.py \
  --mode single --agents 1 --live --seed 17 --max-steps 32 \
  --runs-dir <BLOCK_RUNS_DIR>

python3 experiments/emergent_coordination/run_experiment.py \
  --mode parallel --agents 4 --live --seed 17 --max-steps 8 \
  --runs-dir <BLOCK_RUNS_DIR>

python3 experiments/emergent_coordination/run_experiment.py \
  --mode raw_blackboard --agents 4 --live --seed 17 --max-steps 8 \
  --runs-dir <BLOCK_RUNS_DIR>

python3 experiments/emergent_coordination/run_experiment.py \
  --mode structured_team --agents 4 --live --seed 17 --max-steps 8 \
  --runs-dir <BLOCK_RUNS_DIR>
```

注意：当前未修改代码只提供 40-call default，而非本文 32-call proxy；所以上述 live block **必须在 P0 budget/config 改造和 config equality test通过后运行**。不要把现在的命令列表误读为“当前代码已满足公平预算”。

### 9.6 Per-run evaluation

Runner 当前会自动产生 `merged_findings.json`、`evaluation.json`、`summary.json`。对每个真实 run 路径执行现有 analyzer：

```bash
python3 -m experiments.emergent_coordination.analysis.analyze_run \
  experiments/emergent_coordination/runs/<run_id> \
  --output experiments/emergent_coordination/runs/<run_id>/metrics.json
```

若使用 `<BLOCK_RUNS_DIR>`，把上面路径替换为真实 run dir。P0 后 analyzer 必须先校验事件完整性、预算 reconciliation、oracle结果和 schema invalid count；不完整 run 标为 invalid/partial，不静默纳入对比。

### 9.7 Matched comparison

对四个 run 验证：repository/prompt/common tool/model/request params/budget/grader hashes 一致；仅 mode、N、condition delta/tool capability按预注册变化。然后生成 security/resource/duplicate/allocation/B/T 指标、至少一条完整 lineage trace 和异常清单。

如果第一 block 的机械 gate 通过，再以 seed/replicate 29 重跑；若 seed unsupported，明确写 `replicate_id=29, provider_seed=null`。第二 block 不得因第一 block 表现改变预算或 prompt。

## 10. Expected Pilot Outputs

沿用现有 `experiments/emergent_coordination/runs/` 约定；原始证据仍在 run 目录，人读报告后续可放 `reports/systems/coordaudit/`。建议产物：

```text
experiments/emergent_coordination/runs/<block_id>/
  block_manifest.json
  pilot_summary.csv
  pilot_report.md
  traces/
    selected_complete_trace.json
    selected_complete_trace.md
  <run_id>/
    run_manifest.json
    logs/events.jsonl
    logs/transcript/<agent_id>.jsonl
    artifacts/<agent_id>_findings.json
    artifacts/shared_snapshots/           # B only
    runtime/coordination/                 # T only; final snapshot archived
    merged_findings.json                  # raw deterministic union + provenance
    deduplicated_findings.json
    verification.json
    evaluation.json
    metrics.json
    summary.json
```

`run_manifest.json` 至少保存：provider、exact resolved model、run date、API request params、temperature、max output、seed requested/accepted、reasoning config、tool schema与hash、system/common/delta prompt version/hash、repo/oracle hash、budget/cost价格、environment、git/dirty digest。

`events.jsonl` 至少可关联：Agent LLM/tool/store/task/message/finding/verifier事件；`metrics.json` 给机器读；`pilot_summary.csv` 每 run一行并保留分项指标；`pilot_report.md` 只给 feasibility 结论，不写架构排名。

一条“完整 multi-agent trace”的完成条件：能从 A 的 evidence/shared/task/message origin，经过 B 的 read/adoption和后续调查，连到最终 finding及 deterministic verifier；若没有跨 Agent adoption，也应输出一条“write/read但未形成后续采用”的完整 negative trace。

## 11. Risks / Threats to Validity

- **Model drift / provider non-versioning：**`deepseek-v4-pro` 可能是可变 alias，provider也可能不返回版本。保存精确字符串、日期、响应 metadata/system fingerprint（若有）和请求参数；同 block尽量连续运行，但不能声称后续可完全复现。
- **Seed 不真实：**当前 seed只进 manifest，不进 API。provider不支持时使用 replicate_id，单次差异视为采样噪声。
- **Benchmark task starvation：**5 条浅链只勉强支持 N=4；高 duplicate/idle 可能来自 repo 太小。用 front-over-time 判据，失败时只得出 benchmark undersized，不得让 Agent人为重复采样伪造并行度。
- **Architecture leakage：**T/B 增量 prompt和tool schema是 treatment，但 common audit方法、repo权限、finding schema必须相同。保存 schema/prompt diff，自动拒绝意外额外工具。
- **Token budget unfairness：**S 若只有 8 steps就无法用 team budget；并发 post-call charge会超支。用 pre-call permit + S32/team 4×8，并报告实际 raw usage与stranded quota。
- **Tool compute substitution：**只控 LLM calls时，某 condition可能用更多 shell/tests弥补。Pilot至少统一工具、记录分类 tool calls/CPU时间并设宽松共同上限；正式实验再精细控制。
- **Shared filesystem contamination：**当前 shell可接触宿主机、target可被 shell修改，B之外也可能形成隐式共享。bwrap bind policy、run唯一目录、只读 target、scrub env和越界测试是 live gate。
- **Hidden oracle leakage：**`evaluator_private` 路径过滤不是安全边界。只有 OS mount namespace中根本不可见才算隔离；日志/异常也不能回显 host path或ground-truth名。
- **B 被意外结构化：**不得预建 `/shared/tasks`、namespace、agent目录、README、owner字段、通知、CAS/lock或解析 task-like文件。Analyzer只能事后读，不可在运行中改变 store语义。
- **B substrate choice：**create-only + append降低 overwrite冲突，可能比普通 KV更利于协议。将它视为冻结的 B-aware v0 substrate，不能泛化到所有 raw store。
- **T treatment bundling：**task claim + messages + artifacts 同时启用时，无法把收益单独归因给 claim。Pilot主张只到“structured coordination bundle可运行”；正式研究再做 claim/message ablation。
- **Atomicity范围：**当前 `threading.Lock` 只对一个 Python进程有效。N=4 thread runner可接受；跨进程/N=16不能宣称原子，需 SQLite事务/文件锁服务。
- **Deterministic grader limitations：**规则 grader可能接受措辞投机或漏掉同义描述。收紧 source/sink并保留 per-finding explanation；pilot 可做盲人工抽查，但不引入 condition-specific LLM judge。
- **Verification validity：**benchmark oracle通过证明 snapshot语义，不自动证明 Agent真的独立复现。分别报告 `oracle_verified`、`agent_attempted`、`agent_reproduced`，不能合并。
- **Near-miss policy validity：**网络/DNS等现实残余风险不在 synthetic模型内。评分遵循冻结 benchmark语义，报告不应外推为生产安全证明。
- **Off-target findings：**composite ground truth不是所有可能问题的完备证明。unmatched finding先标 `unmatched/review`；不要未经人工核验一律当现实 FP。正式 precision需更完整标注。
- **Dependency/environment drift：**当前 target requirements未完全 pin，测试还出现 requests dependency warning。保存环境版本，避免不同 condition临时安装不同依赖/cache。
- **Single-seed pilot：**1–2 block只验证 harness、task supply与trace，不支持统计显著性或架构排名；廉价模型结果不得与未来不同模型的 N=16直接比较。
- **历史结果不可合并：**DeepAudit/IRIS/OpenAnt 使用不同 prompt、tools、模型行为与预算，其 canonical结果只能帮助识别风险，不能加入本 pilot分数表。
- **代码版本不可复现：**当前 `experiments/` 尚未被 Git 跟踪，manifest 中仅记录 `git_commit` 会把不同 harness/benchmark 状态错误地标成同一版本；正式开跑前应提交冻结版本，或至少保存 dirty 状态、相关文件哈希和完整配置快照。

## 12. Go / No-Go Recommendation

**GO WITH MINIMAL CHANGES**

9.17 前最值得完成的最小实验是：

```text
repository_pilot_v0
× S1 / P4 / B4-aware / T4
× 1 matched block
× 当前可用的同一 DeepSeek-compatible exact model/config
× 32 team call permits + 1024 max output/call
```

Live gate 只要求 P0 中最影响因果可信度的五组能力完成并通过测试：

1. bwrap private/hidden-oracle/network/env isolation；
2. pre-call global call permit与 S/team公平 step ceiling；
3. event/message/shared/task/finding/verifier可关联日志；
4. deterministic schema validation、source-aware scoring和真实 dedup；
5. duplicate/allocation/B/T/cost metrics及 block config equality检查。

如果这些 gate 没完成，允许跑 mock/compatibility smoke，但结论应是“harness仍未具备可解释 live pilot条件”，而不是用不可信数据补齐矩阵。M4、第二 repo、N=16、lease/crash recovery和复杂 budget scheduler都不应挤占这次最小实验。

本 pilot 的成功结论应限定为：S/P/B/T 能否在一个 harness 下隔离运行、统一记账；v0 是否至少提供 4 个实际活跃 front；P/B/T 的重复工作能否量化；B 是否真的发生 store行为；T 的原子 claim是否真的被使用；以及能否导出至少一条完整或明确的 negative cross-agent trace。它不回答 B/T/M 谁更强。
