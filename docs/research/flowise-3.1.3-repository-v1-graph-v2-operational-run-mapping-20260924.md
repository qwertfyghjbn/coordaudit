# Flowise 3.1.3 repository-v1 graph-v2：可实现性与历史运行映射

日期：2026-09-24。结构图绑定 `graph-v2`，其 manifest SHA-256 为
`d7013f79ffd21a7d7eb4a989ed44d16f46fd3d342ae167ca86a085311f69c041`。
本记录只读使用已冻结的 16 节点、240 条有向边和
`t4-post-sync-window-v2-192p` 的三个 matched seed；不修改 graph、runtime
contract 或历史 run。

## 执行顺序与证据边界

离线脚本
[`scripts/analyze_hidden_graph_operational.py`](../../scripts/analyze_hidden_graph_operational.py)
按以下顺序运行：

1. 对 12 条 structural actionable 边（10 条 `actionable cross-check`、2 条
   `strong dependency`）分别核对 S1/P4/B4/T4/M4 的工具、通道、可见性、permit、
   生命周期和最小信息传递条件。
2. 对三个 T4 run，在每个 `result_sync_triggered` 之前截取 ACTIVE 证据，映射
   completed task、finding evidence 和 node/edge coverage；没有冻结节点范围内
   证据的任务或 finding 标为 `out_of_graph`，不改写为 `none`。
3. 对每个 ACTIVE/RESULT_SYNC 前的 evidence ref，逐项回连
   `logs/events.jsonl` 的 `file_read` 事件和对应 model-visible
   `logs/transcripts/agent_*.jsonl` 的 `tool_result`；同时核对 task completion
   是否在同步前出现在 transcript 中。
4. 前三阶段写盘并通过完整性检查后，才读取 POST_SYNC 事件和人工语义复核，记录
   delivery、discovery、action、evidence consumption、judgment/disposition 和
   strict foreign evidence-ref adoption；再将 result-sync request、verification
   read、tool result 与 follow-up request 逐项回连到 transcript。

全部离线产物位于私有目录
[`graph-v2/operational`](../../artifacts/hidden_opportunity_graph/flowise_3_1_3_repository_v1/graph-v2/operational)：

- `operational_realizability.jsonl`：60 条（12 边 × 5 condition）合同记录；
- `run_task_mapping_pre_sync.jsonl`、`run_finding_mapping_pre_sync.jsonl`：ACTIVE/
  RESULT_SYNC 前的 task/finding 映射；
- `run_coverage_pre_sync.jsonl`、`run_mapping_summary.json`：节点与跨 agent 有向边覆盖；
- `run_handoffs.jsonl`、`run_handoff_summary.json`：三个 run 的交接点、剩余 permit 和
  POST_SYNC reservation；
- `pre_sync_transcript_provenance.jsonl`：23 个 pre-sync task/finding 行逐项绑定到
  model-visible tool-result transcript，并记录缺失引用；
- `post_sync_review.jsonl`、`post_sync_summary.json`：解盲后的逐 agent 语义复核；
- `post_sync_transcript_provenance.jsonl`：12 个 agent 行的同步交付、verification
  read→tool-result→follow-up transcript 链；
- `analysis_index.json`：阶段顺序、图摘要和规则；
- `verify` 命令用于重新核验上述文件与冻结 graph 的绑定。

## 合同层可实现性

| Condition | 12 条跨 agent actionable 边的合同判定 | 依据 |
| --- | --- | --- |
| S1 | 12/12 `no` | 单 agent；只另计 within-agent reuse |
| P4 | 12/12 `no` | 独立私有 target，无通信或共享目录 |
| B4 | 12/12 `yes` | generic `/shared` 可写入、列出、读取；没有 task/message 语义 |
| T4 | 12/12 `yes` | typed task result/evidence refs，在 RESULT_SYNC 后可见 |
| M4 | 12/12 `yes` | 可经 manager 报告和再分派中转；worker 间没有直连 |

`yes` 只表示合同提供了传递最小信息和执行 bounded check 的路径，不表示模型实际选择
了该路径。预算耗尽和窗口关闭单独记录，不能改变 graph 的结构类别。

## 历史 T4 映射（RESULT_SYNC 前）

三个 run 的 task 总数为 12，其中 4 个 task 的证据可靠落入冻结节点范围：

| Run | 映射 task → node | `out_of_graph` task | 可见节点 | 跨 agent actionable coverage |
| --- | --- | ---: | --- | ---: |
| seed 01 | agent_001 task → F001、F004 | 3 | F001、F004 | 0 条 |
| seed 02 | agent_002 task → F011、F012 | 3 | F011、F012 | 0 条 |
| seed 03 | agent_002 task → F011、F012；agent_004 task → F002 | 2 | F002、F011、F012 | 0 条 |

共有 11 个实际 finding 文件（seed 01 为 3 个、seed 02/03 各 4 个）；其中 3 个有
冻结节点范围内的 ACTIVE 证据。seed 02 agent_002 和 seed 03 agent_002 的最终 finding
含 POST_SYNC 新增 evidence ref；映射表只保留触发同步前的 refs，并将新增 refs 列为
`post_sync_evidence_refs_excluded`。

因此，三个 seed 没有形成一条由不同 agent 实际调查、且两端都在冻结 graph 中的
actionable edge instance。这个结果表示历史样本的 graph coverage 不足；它不能说明
12 条结构边为 `none`，也不能把未映射 task 当作 missed opportunity。

## POST_SYNC 解盲结果

| 阶段 | 数量 |
| --- | ---: |
| delivery（provider admission + instruction model-visible） | 12/12 |
| direct relation | 3/12 |
| actionable lead | 2/12 |
| verification action | 2/2 leads |
| evidence model-visible / consumed | 2/2 |
| judgment/disposition changed | 2/2 |
| strict foreign evidence-ref adoption | 0/12（0/2 post-evidence judgments） |

两条 judgment 变化分别是：seed 02 agent_002 在读取 feedback controller 后确认核心
IDOR 并形成 finding（附带 ID 枚举措辞过强）；seed 03 agent_002 在读取
`get-upload-file` controller 后下调公开 traversal 可达性，保留条件性的 guard gap。
这些是 claim-level disposition，不等同于最终 finding 写入 foreign task 的 evidence ref。

三条 direct relation 的 foreign artifact 没有形成可靠的冻结 graph edge 映射，均在
`post_sync_review.jsonl` 中保留为 `selected_artifact_graph_status=out_of_graph`，不计入
结构 coverage。

## 复核命令

```bash
python3 -m scripts.analyze_hidden_graph_operational run
python3 -m scripts.analyze_hidden_graph_operational verify
python3 -m scripts.hidden_opportunity_graph validate --graph-version graph-v2
git diff --check
```

本次 transcript 级核验已通过：`verify` 返回 `status=verified`，确认 23/23
pre-sync 行的 evidence chain、12/12 POST_SYNC delivery transcript chain，以及
2/2 evidence-consumption chain 均完整；图摘要仍为 16 节点、240 条有向边，未修改。

本记录的结论范围仅限这三个已冻结 T4 v2 seed；若需要估计 graph 的跨 agent coverage，
应在 graph 冻结后另行授权新的运行或补充有明确节点范围的历史样本。
