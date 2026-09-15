# CoordAudit v0 冻结补遗：S1 smoke 与合同 hash

本补遗补全 [`v0-freeze.md`](v0-freeze.md) 中有意省略的非敏感 S1 smoke 摘要与 per-condition hash。它不修改 `coord-audit-v0` tag，也不替代原始 run artifact。

## S1 live smoke 的完整公开摘要

| 字段 | 值 |
| --- | --- |
| Run ID | `single_n1_20260915T080646.642486+0000_ce952b81` |
| Runtime commit | `d7e0b25` |
| Seed | `0` |
| 开始 / 结束 | 2026-09-15T08:06:46.679114Z / 2026-09-15T08:06:52.647062Z |
| Mode / Agent count | `single` / 1 |
| 模型 profile | `deepseek-flash`、non-thinking、temperature 0、1024 output ceiling |
| OS sandbox | required，live bwrap self-check 通过 |
| Smoke hard budget | 4 permits、60 秒 wall clock、最多 4 steps、最多 1 次 harness retry |
| Permit 结果 | 4 acquired、4 succeeded、0 failed、0 retry、0 timeout、0 provider error |
| 运行有效性 | `run_validity=valid`；`reconciliation=valid` |
| 活动时间 | 5.926993 秒（agent 生命周期包络，非 CPU 时间） |

### 资源与事件

| 指标 | 值 |
| --- | ---: |
| Provider-reported input tokens | 8,662 |
| 其中 cached-input tokens | 5,248 |
| Provider-reported output tokens | 540 |
| Input + output | 9,202 |
| Events / transcripts / artifacts | 50 / 23 / 16 |
| `file_read` / `tool_call` | 13 / 17 |
| `llm_call_attempted` / `llm_call` | 4 / 4 |

run manifest 中的 4,000 input 与 2,000 output 是历史 smoke budget 字段；live provider usage 只会在响应后得到，因此当前 ADR 0002 runtime 的唯一严格 admission budget 是 4 个 hard permits。`token_stop_threshold` 为 `null`，上述实测 token 不构成 token-cap violation。

### 公开评估

| 项目 | 值 |
| --- | --- |
| 提交 / invalid submissions | 0 / 0 |
| TP / FN / positive recall | 0 / 3 / 0.0 |
| known-near-miss FP / unmatched review / duplicates | 0 / 0 / 0 |
| closed-world lower / labeled-only upper precision | 0.0 / 0.0 |
| evaluator-verified findings / semantic judge | 0 / false |
| Agent stop reason | `model_format_failure` |

这些分数只描述未提交 finding 的 S1 smoke；它们不支持安全能力、模型质量或 coordination effect 结论。

## N=4 prompt 与 tool-schema hash

所有 hash 为 SHA-256，来源是冻结 artifact `n4-pilot-v0-freeze-20260915/block_manifest.json`；common prompt hash 为 `d2581ec0545fec8d655d25331232e989694f271721d43b1da1b410e8f05e2407`。

| Condition | System prompt | User prompt | Tool schema |
| --- | --- | --- | --- |
| S1 | `822495e4095e175322c769809584f1196784d7e2965ccf54008c83f042ca4ff4` | `02bbdaabb92f41a3960f385674ab7d574ba2cdd1cf5cc1075152d34d4ed420b4` | `6496b55792eb5a3b8cc93caa129eb3a6fe2483433cff33ead7924c408de985b8` |
| P4 | `822495e4095e175322c769809584f1196784d7e2965ccf54008c83f042ca4ff4` | `23f29eedbe1583ffecf9983a035c868567fe80759ffcbe89b9882c95881d0951` | `6496b55792eb5a3b8cc93caa129eb3a6fe2483433cff33ead7924c408de985b8` |
| B4 | `430eefa20b55f96fd5a47915e8faac5c1161d65bfd63b2d69a71f0e1b7bdbeb7` | `689dce613a7c8e3ca6362c221512fdf96c625c85e9a2e8b053f8cb326f95948e` | `4bc537e0a4fde78223aee790072122cd023779ecd3c1d279c63e61a0b5db9280` |
| T4 | `5732911399ce15c3fcbd404ba0dfb7febc6ecfda7d57a40953496738d72ae104` | `b34a0f567beb080adccdfc0d458518601c73923624a9bb60fdf1a40e14eeb415` | `c71813457f22e2318bbe4cdd1e4f3741579adef247f6ba8a9f0445ba3b3bee11` |

## 明确保留在运行产物、而不复制到版本化文档的内容

- `events.jsonl`、model-visible transcript 与 tool/artifact 正文；
- 每次 provider request/response ID、模型正文与工具参数；
- evaluator-private verification、ground-truth assignment 与 duplicate provenance。

它们仍保留于 `experiments/emergent_coordination/runs/` 的对应 run directory，默认不提交；该边界防止凭证、宿主路径、hidden evaluator 或不必要的模型内容进入正式发布物。
