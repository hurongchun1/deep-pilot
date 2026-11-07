# 03｜Backend 与文件存储：先问文件给谁用

## 核心认识

Deep Agents 的文件路径是 Agent 看到的虚拟路径。Backend 决定这些读写落到哪里。**跨一次调用、跨同一 thread、跨不同 thread、跨进程重启**是四个不同的要求；“已持久化”必须说清是哪一层。

| 选择 | 本项目中的存储位置 | 典型范围 | 关键条件 |
| --- | --- | --- | --- |
| `StateBackend` | LangGraph state 的 `files` | 当前执行或 thread | 跨调用恢复需 Checkpointer 和相同 `thread_id` |
| `FilesystemBackend` | 项目磁盘目录 | 使用同一目录的会话 | 文件本身可跨进程，仍须考虑权限和并发 |
| `StoreBackend` | LangGraph Store 的 namespace + key | 可跨 thread 共享 | 重启后保留取决于 Store 实现 |
| `CompositeBackend` | 按路径前缀路由到以上 Backend | 路由决定 | 需核对前缀剥离与实际 key |

`InMemorySaver` 和 `InMemoryStore` 都只在对应进程内有效。`StoreBackend` 能跨 thread 访问同一数据组，不等于跨进程持久化。`namespace` 是逻辑分组，不是身份验证或授权；多用户场景必须由应用传入可信身份并限制访问。

## 选择方法

- 临时草稿、当前任务中间结果：通常先考虑 State。
- 本地项目文件、可在编辑器检查的产物：Filesystem。
- 不同会话都要用的偏好或共享资料：Store，或明确管理的持久文件；同时设计身份隔离。
- 同一 Agent 需要混用临时文件和长期记忆：Composite 路由不同路径。

Task 8 使用 `FilesystemBackend(root_dir=..., virtual_mode=True)`，让 Agent 通过 `/skills/`、`/memory/` 等路径访问项目文件。它的计划由自定义 `save_plan` 写入 `artifacts/`；配置 Backend 本身并不会生成计划。Task 2 的 `StateBackend` 实验里，文件在 state 中，并不存在同名 Windows 文件。

## 文件工具与上下文

文件在 Backend 中，不等于全文已经进入模型上下文；需要工具读出，或由专门的记忆加载机制注入。大工具结果卸载会把完整结果放到文件，模型先看到路径和预览，再按需读取；这与对话历史摘要是两套机制。

本项目的 `LocalShellBackend` 提供执行命令的能力，但 `virtual_mode=True` 的文件路径约束**不是 Shell 沙箱**。如果要执行不可信命令，需要另外设计隔离。

## 自测问题

一个用户在新会话中找不到上次的草稿：先检查 Backend、`thread_id`、Checkpointer、Store 实现和 namespace 中的哪几项？为什么只看到 `/notes/plan.md` 不能断定磁盘上有该文件？

**项目证据**：`task2/experiments/README.md`；`task5/notes/ch07-backends-namespace-note.md`；`task8/CHECKIN.md`。**文档**：[Deep Agents Backends](https://docs.langchain.com/oss/python/deepagents/backends)。
