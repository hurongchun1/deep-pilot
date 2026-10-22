# Task 4：DeepAgents Content Builder（仅后端）

本目录由 [AgentSeek content-builder 模板](https://github.com/agentseek-ai/agentseek-templates/tree/main/templates/deepagents/content-builder) 生成，源提交为 `7149bf2da837533cec9c738de64a09f90984f76a`。项目名和 Python 包名改为 `task4`，并移除了前端及其生命周期配置。原模板说明保留在 [TEMPLATE_README.md](TEMPLATE_README.md)；课程实验见 [COURSE.md](COURSE.md)，其中的前端步骤不适用于本目录。

本项目独立于仓库根目录的 `venv`，使用 Python 3.12、`uv.lock` 和锁定的 `deepagents==0.7.8`。

子 Agent 工具集继承实验脚本放在 [experiment/verify_subagent_tools.py](experiment/verify_subagent_tools.py)，无需模型密钥。

## 安装

在 PowerShell 中运行：

```powershell
cd D:\pythonProject\gitProject\deep-pilot\task4
uv sync --python 3.12 --frozen
Copy-Item .\.env.example .\.env
notepad .\.env
```

默认模型使用 SiliconFlow 提供的 `deepseek-ai/DeepSeek-V3.2`。在 `.env` 中填入 SiliconFlow 的 `OPENAI_API_KEY`。保持默认的 `OPENAI_API_BASE=https://api.siliconflow.cn/v1`。纯文本模式不需要 Tavily 或图像服务密钥。不要将 `.env` 提交到 Git。

## 运行后端

```powershell
uv run --frozen agentseek-api dev --port 2024
```

API 文档：<http://127.0.0.1:2024/docs>；健康检查：<http://127.0.0.1:2024/health>。按 `Ctrl+C` 停止服务。

现在的 `.agentseek/lifecycle.toml` 也只声明后端，所以配置好 `.env` 后可以使用 `uvx agentseek==0.1.2 doctor` 和 `uvx agentseek==0.1.2 dev`。

## 无模型密钥的检查

```powershell
uv run --frozen pytest tests -q
```

测试采用脚本化模型；真正的内容生成仍需在 `.env` 配置可用的模型密钥。生成内容会写入 `blogs/`、`linkedin/`、`tweets/`、`research/` 等本地目录。
