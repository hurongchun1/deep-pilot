# Task 6：长期记忆实验

参考 [AgentSeek content-builder 模板](https://github.com/agentseek-ai/agentseek-templates/tree/main/templates/deepagents/content-builder) 的 Deep Agents 装配方式，为[《Deep Agents 实战》第 8 章](https://datawhalechina.github.io/deepagents-in-action/chapters/ch08-long-term-memory/)建立独立实验目录。每个实验都直接调用 `create_deep_agent(...)`，完整展示该实验的 Backend、Store、Checkpointer 和 `memory=` 配置。本阶段只实现记忆实验，不包含模板的内容创作、前端、搜索或图像功能。

模板参考提交：`agentseek-ai/agentseek-templates@7149bf2da837533cec9c738de64a09f90984f76a`。本目录锁定 `deepagents==0.7.10`，与第 8 章示例版本一致，不依赖 `task5` 的环境。

## 真实模型 + LangSmith（主实验）

在 `task6` 目录运行。先把 `.env.example` 复制成 `.env`，填入模型连接信息；也可以直接设置同名环境变量。`LANGSMITH_API_KEY` 必填，`LANGSMITH_PROJECT` 可选。已有的 `.env` 不要覆盖。

```powershell
Copy-Item .env.example .env  # 仅当 .env 不存在时执行，然后填写密钥
uv run --frozen python experiments/live_memory.py
```

此脚本通过模板相同的 `AGENTSEEK_MODEL`、`OPENAI_API_KEY`、`OPENAI_API_BASE` 约定连接真实模型，当前支持 OpenAI 及兼容接口。模型自行决定工具调用；脚本打印真实的 `read_file`、`edit_file`、`write_file` 和工具结果。它验证：

1. 用户 Alice 的偏好确实写入 Store，全新线程的模型请求重新加载更新内容。
2. 用户 Bob 的模型请求只包含 Bob 的 namespace，不包含 Alice 的偏好。
3. Alice 更新语言偏好时保留格式偏好。
4. `/workspace/draft.txt` 只在原线程可恢复，新线程读取失败。
5. `edit_file` 找不到旧内容时返回错误，Store 保持原样，模型报告写入失败。

运行时强制开启 LangSmith tracing，要求密钥可用；结束时刷新上传并打印 run 链接。使用新的 `InMemoryStore` 和 `InMemorySaver`，不修改 `task5` 的文件。每次运行会调用真实模型，产生模型及追踪服务请求。

## 离线对照实验

四组离线脚本保留作确定性对照，不需要 API 密钥，也不会上传 LangSmith trace。预设模型只固定工具调用，文件工具、Checkpointer、Store、路由和记忆加载都真实运行。

```powershell
uv run --frozen python experiments/01_thread_vs_store.py
uv run --frozen python experiments/02_cross_thread_write.py
uv run --frozen python experiments/03_user_isolation.py
uv run --frozen python experiments/04_update_and_failure.py
```

| 脚本 | 验证内容 | 关键证据 |
| --- | --- | --- |
| `01_thread_vs_store.py` | State 文件按线程隔离，Store 记忆跨线程 | `read_file` 工具结果、新线程模型请求 |
| `02_cross_thread_write.py` | `edit_file` 经路由写入 Store，新线程重新加载 | Store 实际内容、新线程模型请求不含旧偏好 |
| `03_user_isolation.py` | 同一 Store 下按 `user_id` 隔离 | A、B 模型请求互不含对方标记 |
| `04_update_and_failure.py` | 局部更新保留其他条目，失败编辑不改 Store | 工具状态、更新前后 Store 内容 |

## 实验边界

- `InMemoryStore` 和 `InMemorySaver` 只在当前进程内有效；本组验证跨线程，不验证重启后的持久化。
- live 脚本检查本次模型的实际工具行为；模型服务或提示词变化可能使调用路径不同，断言失败时应查看打印的工具轨迹与 LangSmith run。
- `memory=["/memories/preferences.md"]` 加载已有文件。每组实验用 `seed()` 预置 Store，且只在新 Store 上执行，避免覆盖已有偏好。
- `CompositeBackend` 挂载 `/memories/` 后，Agent 可见路径是 `/memories/preferences.md`，底层 Store key 是 `/preferences.md`。
