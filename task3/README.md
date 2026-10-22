# Task 3：任务规划与中间件

本目录是《Deep Agents 实战》第 4 章的后端学习项目。Agent 源码在 `src/research_deepagent/`，可独立运行的实验统一放在 `experiments/`。没有前端依赖。

## 目录

```text
task3/
├── .agentseek/lifecycle.toml       # 后端服务和检查命令
├── src/research_deepagent/         # Agent、提示词、搜索工具
├── experiments/                    # 第 4 章离线与真实模型实验
├── tests/                          # 模板自带的后端测试
├── .env.example                    # 模型与 Tavily 配置示例
├── langgraph.json                  # 后端图入口
├── pyproject.toml
└── uv.lock
```

## 先做离线实验

在 `task3` 目录执行；不需要 API Key，也不需要启动服务：

```powershell
uv run --frozen python experiments/ch04_todo_replace.py
```

它展示 `write_todos` 如何替换整份 `todos` 清单。实验说明见 [experiments/README.md](experiments/README.md)。

## 运行真实模型实验

首次运行时，从 `.env.example` 复制出 `.env`，填写 `OPENAI_API_KEY` 和 `TAVILY_API_KEY`。模板默认用 SiliconFlow 的 OpenAI 兼容接口；切换服务时，连同 `AGENTSEEK_MODEL`、`OPENAI_API_BASE` 一起调整。不要覆盖已经填过的 `.env`。

```powershell
uvx agentseek task sync
uv run --frozen python experiments/ch04_planning.py
```

脚本打印工具调用、任务状态变化和最终回答。核对 `write_todos` 的调用记录、`todos` 状态以及报告内容是否一致。

## 后端服务（可选）

后端图由 `src/research_deepagent/agent.py:build_graph` 创建，并显式启用 `TodoListMiddleware`。需要通过 API 调用 Agent 时，填写 `.env` 后执行：

```powershell
uvx agentseek info
uvx agentseek doctor
uvx agentseek dev
```

服务地址为 `http://127.0.0.1:2024`。无需真实模型密钥的后端机制测试可运行 `uvx agentseek task course-check`。版本锁定及规划实验注意事项见 [COURSE.md](COURSE.md)。
