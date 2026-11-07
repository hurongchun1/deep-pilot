# 06｜Memory：决定记什么、给谁用、何时更新

## 短期与长期

短期状态通常服务于同一个 thread：消息、工具结果、当前任务进度。配合 Checkpointer 与相同 `thread_id`，可以在多次调用间恢复。长期记忆面向跨 thread 复用，例如明确的用户偏好、稳定项目背景、经核实的研究结论。能否跨程序重启，取决于实际 Checkpointer、Store 或文件存储实现。

| 设计问题 | 需要明确的答案 |
| --- | --- |
| 记什么 | 稳定偏好、项目事实，还是当前任务输入？ |
| 给谁用 | 单用户、某 Agent、团队或组织？ |
| 什么时候写 | 用户明确要求、人工审核后，还是有其他可信触发？ |
| 什么时候读 | 启动加载，还是任务相关时按需检索？ |
| 什么时候改或删 | 新信息冲突、过期、用户要求修改时如何处理？ |

`namespace` 可把 Store 数据按用户或组织分组，但它本身不认证身份。应用必须从可信上下文构造 namespace，避免不同用户记忆串用。把一次任务的期限、某个案例的假设直接写成长期偏好，会污染未来任务。

## Task 8 的做法

`MemoryMiddleware` 加载 `/AGENTS.md` 和 `/memory/preferences.md`。只有用户明确要求“记住”语言、语气或格式时，才调用 `save_preference`。普通目标和截止时间只用于本次计划。实际写入后，应该读回文件，并在新 thread 验证偏好确实被加载。

`memory=` 或 `MemoryMiddleware` 指定读取位置，不保证文件自动创建，也不保证模型一定正确更新。读写策略、权限和内容校验仍由应用设计。写入整份文件与局部编辑的语义也要确认，避免覆盖已有记忆。

## 常见误区

- “长期”不等于永不删除；过期和错误信息应有修订机制。
- “新 thread 读到了”不等于进程重启后仍保留。
- “同 namespace”不等于授权通过或内容已经写入。
- “模型记住了”应具体化为可查看的文件、Store 记录和新的调用证据。

## 自测问题

用户说“这次计划用中文，两周完成”，哪些内容进入本次任务，哪些可以成为长期偏好？如果另一个用户读到了此偏好，应检查哪一层？

**项目证据**：`task6/ch08-long-term-memory-summary.md`；`task5/notes/ch07-backends-namespace-note.md`；`task8/CHECKIN.md`；`task8/memory/preferences.md`。**课程**：[第 8 章长期记忆](https://datawhalechina.github.io/deepagents-in-action/chapters/ch08-long-term-memory/)。
