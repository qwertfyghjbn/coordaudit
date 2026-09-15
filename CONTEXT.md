# CoordAudit

CoordAudit 研究在审计目标、模型、工具权限、输入可见性与团队预算保持可比时，runtime coordination adapter 如何影响多 Agent 漏洞审计行为与结果。

## Language

**Coordination condition（协调条件）**:
一次运行中 Agent 可用的协调能力边界；当前条件为 S、P、B、T。条件包含必要的 prompt 增量与工具 schema，但不包含模型、审计目标或团队预算差异。
_Avoid_: 架构（未说明是 runtime coordination 时）、模式

**Matched block（匹配实验块）**:
针对同一 Agent-visible target 与冻结配置执行的一组 S、P、B、T 运行；除协调条件及其必要能力外，其他因果相关配置相同。
_Avoid_: 一批运行、同轮实验

**Hard team call budget（团队硬调用预算）**:
一个 condition 内所有 Agent 共同竞争的 model-call permit 总数；它不随 Agent 数量相乘，也不预先均分给各 Agent。每 Agent 获得的实际 permits 是资源分配结果。
_Avoid_: `N × per-agent` 预算、每 Agent 均分预算、总 token 硬预算

**Attempted model call（已尝试模型调用）**:
已经实际发给 provider 的请求，无论最终成功、超时或返回 provider error。每次 attempted model call 消耗一个 team call permit；retry 是新的 attempted model call。
_Avoid_: 仅成功调用、免费重试

**Per-call output ceiling（单次输出上限）**:
每个 model call 可生成的最大 output tokens；它不限制 input tokens，也不等同于团队硬调用预算。
_Avoid_: team token budget、总输出量

**Token stop threshold（Token 停机软阈值）**:
根据 provider 已报告 usage 决定是否停止后续调用的安全阈值。它允许最多一次已在途调用造成的越界，不是精确 admission-controlled 的硬预算。
_Avoid_: hard token cap、精确 token 预算

**Actual token usage（实际 Token 用量）**:
provider 对 input、cached input、output 与 reasoning tokens 的实际报告；它是 condition 的资源结果，不触发事后额度补偿。
_Avoid_: 预算许可、估算 token

**Agent-visible target（Agent 可见目标）**:
审计 Agent 被允许读取和操作的匿名仓库快照；不包含 hidden evaluator、ground truth、source case 标签或 provenance。
_Avoid_: 完整 benchmark、源 case

**Agent capability boundary（Agent 能力边界）**:
模型输出能够触发的全部外部作用范围。任何文件系统访问、网络访问、进程创建或代码执行都必须经注册且按 condition 授权的 controlled tool API；未注册能力视为隔离失败。
_Avoid_: 只约束 shell、prompt 中要求自律

**Trusted control plane（可信控制面）**:
准备快照、调用模型 provider、仲裁预算、记录事件和运行 hidden evaluator 的 harness 部分。它不接受 Agent 任意代码，且不能把自身可见的私有数据或网络能力转化为 Agent capability。
_Avoid_: Agent runtime、共享工具

**Model-visible transcript（模型可见转录）**:
按真实顺序记录模型实际接收的消息、工具 schema/调用/结果，以及模型返回内容的脱敏运行证据。它只包含进入模型上下文的内容，不以宿主原始输出或隐藏推理替代。
_Avoid_: 仅事件摘要、完整宿主日志、hidden chain of thought

**Lineage（证据链）**:
由稳定 ID 与父引用连接 call、tool、store/task、evidence、finding 和 verification 的可重放关系。时间相邻或内容相似只能形成推断关系，不能替代显式 lineage。
_Avoid_: 只有 timestamp 的日志、后验 interaction graph

**Hidden evaluator（隐藏评估器）**:
运行结束后在 Agent 可见边界之外执行的确定性验证与评分资产集合。
_Avoid_: Agent 测试、公开 oracle

**Valid finding（有效 Finding）**:
通过冻结 schema、具有可解析的漏洞类别与 typed locations，并引用 Agent 实际接触过的证据事件的提交。格式有效不表示它已命中 ground truth 或已被 evaluator 验证。
_Avoid_: 已验证漏洞、任意模型输出

**Known near-miss false positive（已知近似误报）**:
将冻结 ground truth 明确标为安全近似路径的行为报告为可利用漏洞；这是可确定计数的 false positive。
_Avoid_: 所有 unmatched finding、一般误报

**Unmatched review（未匹配待复核）**:
Schema 合法但未命中已知 positive 或 near miss 的 finding。由于 composite ground truth 不完备，它既不自动算现实漏洞，也不自动算现实 false positive。
_Avoid_: false positive、true positive

**Precision bounds（精确率边界）**:
分别在 closed-world 与 labeled-only 假设下计算的精确率区间，用来显式表达 unmatched review 的不确定性。
_Avoid_: 无假设的单一 precision、正式全仓 precision

**Evaluator verification（评估器验证）**:
Hidden evaluator 对冻结 run snapshot、ground-truth anchors 与 finding evidence 的确定性检查。它与 Agent 自报的 reproduction attempt 或 success 分开记录。
_Avoid_: Agent 自报 verified、仅通过 benchmark smoke test

**Work front（工作前线）**:
可由一个 Agent 独立取得实质性审计进展、并能产生可评分证据的调查线。文件数、路由数和 Agent 自称的任务不自动构成 work front。
_Avoid_: 文件、endpoint、task

**Harness hardening（harness 加固）**:
使 matched block 具备因果可比性、隔离性、预算完整性和可重建证据链所需的改造；不包括扩大 benchmark 或新增 coordination condition。
_Avoid_: benchmark 扩充、一般性重构

**Live gate（真实运行门槛）**:
允许生成可解释 live matched block 之前必须满足的验证条件。只通过 mock smoke 不等于通过 live gate。
_Avoid_: smoke test、运行成功

**Infrastructure-invalid run（基础设施无效运行）**:
因 provider 基础设施故障达到预注册阈值，或因 harness、runtime、预算、日志、隔离错误而失去可解释性的运行。它保留为运行证据，但不进入 coordination 效果比较。
_Avoid_: 模型失败、低分运行、可重试样本

**Infrastructure-invalid block（基础设施无效实验块）**:
包含至少一个 infrastructure-invalid run 的 matched block。该 block 立即停止并整体重跑，不能只补跑其中一个 condition。
_Avoid_: 失败 condition、部分 matched block

## Example dialogue

> 开发者：T4 比 P4 多用了 task claim，是否还能放在同一个 matched block？
>
> 领域专家：可以，task claim 是 coordination condition 的必要差异；但两者必须共享同一 Agent-visible target、模型配置和 hard team call budget。先通过 live gate，再比较 work front 覆盖、重复劳动和结果。
