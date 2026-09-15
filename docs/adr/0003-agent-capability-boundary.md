# 0003. Agent 外部能力只经受控工具 API 暴露

## 状态

Accepted

## 决策

模型输出能够触发的所有文件系统、网络、进程与代码执行能力必须通过注册且按 coordination condition 授权的 tool dispatcher。Trusted controller 保留 provider 网络、快照、日志和 hidden evaluator 权限，但这些权限不能由 Agent 参数调用或通过工具结果泄露。`run_shell` 每次在 fail-closed bubblewrap namespace 中执行；本 pilot 不把整个 controller 放入无网络 namespace，也不引入 provider broker。

## 理由

只依赖 prompt 自律、路径字符串黑名单或代理变量不能形成安全边界；把整个 controller 沙箱化又需要新增网络 broker 和 IPC，扩大 P0。受控 tool API 加 shell subprocess namespace 能覆盖 Agent 可触发的外部作用，同时保持 provider 与 evaluator 位于可信控制面。

## 后果

- `target` 只读，Agent 只可写各自 `scratch`；B/T 状态只能经对应受记录 API 访问，不能直接挂入 shell。
- Shell 使用独立 mount/network/PID/IPC/UTS namespace、环境 allowlist 和最小只读运行时挂载；live 中 sandbox 不可用或自检失败时禁止降级运行。
- 新增任何可触发 I/O、网络或执行的工具，必须进入 condition tool-surface hash、隔离测试、事件日志和 matched-block equality 检查。

## 实现对齐（2026-09-15）

`run_shell` 使用 `bwrap` 的独立 network/PID/IPC/UTS namespace、清空后的环境 allowlist、只读 `/usr`、`/lib`、`/lib64`、私有 `/proc`/`/dev`/`/tmp`，并仅绑定 `/work/target`（只读）和当前 Agent 的 `/work/scratch`（可写）。shell 不挂载其他 Agent、run state、B shared state、T task state 或 `evaluator_private`，且不会退回宿主 shell。live run 在开始及每个 Agent sandbox 初始化时做同一 self-check，失败即拒绝执行；provider 网络和 hidden evaluator 继续留在 trusted control plane。
