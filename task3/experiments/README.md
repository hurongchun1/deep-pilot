# 第 4 章：任务规划实验

课程网页中的“代码实战”是单文件示例。本目录统一放第 4 章的独立实验脚本；运行它们不需要启动后端服务。

## B1：离线验证任务清单的全量替换

`ch04_todo_replace.py` 用预设模型消息调用真实的 `write_todos`，不需要 API Key。两次调用分别提交完整清单；第二次故意删去旧任务并加入新任务，观察 `todos` 被替换，同时检查两条工具响应仍保存在消息历史中。

在 `task3` 目录下运行：

```powershell
uv run --frozen python experiments/ch04_todo_replace.py
```

可以修改脚本中的 `second` 清单，重新运行，观察最终状态如何变化。

## 真实模型观察规划过程

`ch04_planning.py` 按课程示例创建 Agent，并打印工具调用、`todos` 状态变化和最终回答。脚本固定读取 `task3/.env`：优先使用 `BUB_API_KEY`、`BUB_MODEL`、`BUB_API_BASE`，也兼容模板中的 `OPENAI_API_KEY`、`AGENTSEEK_MODEL`、`OPENAI_API_BASE`；两种方式都需要 `TAVILY_API_KEY`。`BUB_MODEL=openai:deepseek-flash` 这样的配置可直接使用，脚本会把 `openai:` 适配器前缀去掉再传给 `ChatOpenAI`。首次运行前：

```powershell
Copy-Item .env.example .env  # 仅在 .env 尚不存在时执行
# 在 .env 中填写模型密钥和 TAVILY_API_KEY；按所选配置填写模型名和服务地址
uvx agentseek task sync
uv run --frozen python experiments/ch04_planning.py
```

脚本会调用真实模型和 Tavily。先看 `工具调用：write_todos` 是否出现，再看任务是否从 `pending` / `in_progress` 变为 `completed`，最后核对报告中的来源。模型决定实际调用顺序，因此这些变化不能只凭提示词保证。

后端图在 `src/research_deepagent/agent.py` 的 `build_graph()` 中接入同一个 `TodoListMiddleware`；它还加入了子 Agent 和更多工具。无需 API Key 的机制验证可运行 `uvx agentseek task course-check`。
