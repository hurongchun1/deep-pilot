# Task 7：第 9 章 Human-in-the-Loop 实验

依据[《Deep Agents 实战》第 9 章](https://datawhalechina.github.io/deepagents-in-action/chapters/ch09-human-in-the-loop/)编写。所有 Agent 都在各自的实验文件中直接调用 `create_deep_agent(...)`；代码用中文注释说明暂停点、Checkpoint、人工决策、恢复和实际副作用。模型使用真实 API，运行链路上传 LangSmith。

## 准备环境

在 `task7` 目录运行。项目有独立的 `pyproject.toml` 与 `uv.lock`，不修改 `task6` 的依赖。

```powershell
# 仅在 task7/.env 不存在时复制，再填写模型和 LangSmith 密钥。
Copy-Item .env.example .env

uv run --frozen python experiments/live_hitl.py
uv run --frozen python experiments/live_boundaries.py
```

沿用 AgentSeek content-builder 模板的 `AGENTSEEK_MODEL`、`OPENAI_API_KEY`、`OPENAI_API_BASE` 约定；当前脚本支持 OpenAI 及兼容接口。`LANGSMITH_API_KEY` 必填，`LANGSMITH_PROJECT` 可选。每次运行都会调用真实模型并上传 trace。实验中的“通知”只写进当前进程列表，文件写入只发生在临时目录；没有真实邮件或外部业务接口。

## 实验一：四种人工决策

[live_hitl.py](experiments/live_hitl.py) 让真实模型提出工具调用，然后由脚本代表实验中的人工审查者提交决定：

| 决策 | 审批前 | 恢复后检查 |
| --- | --- | --- |
| `approve` | 执行日志为空 | 原始参数执行一次 |
| `reject` | 执行日志为空 | 不执行，拒绝原因以 ToolMessage 返回 |
| `edit` | 执行日志为空 | 使用人工改过的 `channel` 执行一次 |
| `respond` | `ask_user` 没有运行 | 人的回答成为成功工具结果，`ask_user` 函数仍不运行 |

每组都用新的 `thread_id`，检查 `result.interrupts`、`graph.get_state(config).next` 和 `snapshot.interrupts`；恢复时使用相同的 config 与 `Command(resume={"decisions": [...]})`。`read_policy` 配置为 `False`，展示不需审批的只读工具。代码使用 `version="v2"`，因此通过 `.interrupts`、`.value` 读取结果。

## 实验二：审批边界

[live_boundaries.py](experiments/live_boundaries.py) 覆盖两种入口：

1. `interrupt_on` 中的 `when`：`/workspace/` 参数自动放行，`/protected/` 参数暂停。拒绝后执行日志不新增记录。
2. `FilesystemPermission(mode="interrupt")`：内置 `write_file` 写入 `/protected/**` 前暂停。批准前临时目录中没有目标文件，批准后才生成。

## 读代码时重点看什么

- `interrupt_on` 指定**哪些工具调用要审查**；`allowed_decisions` 决定人工可选动作。
- Checkpointer 保存暂停时的线程状态，恢复时 `thread_id` 必须一致。
- `action_requests` 是审批界面应展示的实际工具名与参数；`edit` 的 `edited_action` 使用 `name` 与 `args`。
- 最终自然语言可能误述中断过程。本次真实运行里，模型在 `approve` 后声称“调用没有被拦截”，但 `paused.interrupts`、Checkpoint 和执行日志明确显示它先暂停再获批。判断是否执行应看工具结果与实际记录。
- `InMemorySaver` 只在当前进程有效。跨进程或长时间审批应换持久化 Checkpointer。本阶段未覆盖子 Agent 审批、批量并行工具调用及自定义 Middleware 的底层 `interrupt()`；这些属于后续扩展。
