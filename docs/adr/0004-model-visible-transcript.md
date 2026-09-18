# 0004. 事件索引与模型可见转录分离保存

## 状态

Accepted

## 决策

每个 live run 保存经过确定性脱敏的完整 model-visible transcript；`events.jsonl` 只保存稳定ID、顺序、父引用、时间、outcome、budget progress、内容hash与artifact引用。大内容按Agent写入append-only transcript/artifact，内容必须与模型实际看到的截断结果一致。事件、转录和budget ledger在run结束时reconcile，缺失引用或hash不一致使run infrastructure-invalid。

## 理由

只有hash无法判断证据exposure、adoption或错误传播；把全部正文塞进event stream又难以校验、脱敏和分析。分离保存既能重放模型上下文，也能让结构化事件保持稳定。

## 后果

- 落盘前移除API凭证、授权头、敏感provider参数和宿主绝对路径；出现hidden evaluator/private内容立即使run invalid。
- Provider reasoning content只有在后续请求必须回传时才正文保存在受限artifact中，否则仅记录存在性、token数、hash与长度；它不进入评分或coordination分析。
- 默认`runs/`不提交；正式versioned artifact只发布脱敏派生指标和选定trace。

## 实现对齐（2026-09-15）

`EventLog` 写入顺序化 `events.jsonl`，将命令、参数、模型/工具正文和错误正文移到 append-only `logs/artifacts/*.jsonl`；`TranscriptLog` 按 Agent 写入实际 request messages、tool schema、response 与截断后的 tool result。三者在落盘前使用同一确定性脱敏器，检测到 hidden evaluator/private 标记会把 run 标记为 `infrastructure_invalid`。`reconcile_run()` 校验事件和转录序号、父引用、artifact/transcript hash 与每一 permit 对应的 call/request/response 记录。这里的“可重放”是指可由保存的模型可见输入重建上下文与审计 lineage，并不承诺重新调用 provider 会得到相同响应。

每个成功 provider response 的 `model_metadata` 还保留原始 `choices[0].finish_reason`（provider 未提供时为 `null`）；该字段同时进入 model-visible transcript 与对应的 `llm_call` event，用于区分正常停止、tool call 和 output-length 截断，不改变调用预算或 Agent 可见 prompt。

宿主绝对路径脱敏不得破坏 JSON 编码字符串的转义边界；对工具结果等嵌套 JSON 文本替换路径后，持久化的文本仍必须可解析。
