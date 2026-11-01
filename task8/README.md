# Release Pilot：青柠清单 v1.2 上线计划助手

这是一个独立的 AgentSeek 后端应用。用户给出“为青柠清单 v1.2 制定上线计划”的任务后，Agent 读取本地产品简报和发布约束，生成可执行的分阶段发布计划，保存 Markdown 文件，读回并做结构检查。输入资料是**虚构项目资料**；应用不执行真实部署或回滚。图入口为 `./agent.py:graph`。

## 应用如何工作

| 组成 | 在发布计划任务中的作用 | 可检查的结果 |
| --- | --- | --- |
| 工具 | 读取两份资料，保存、读回和检查计划；仅在明确要求时保存格式偏好 | 工具消息、计划文件和检查结果 |
| 中间件 | `TodoListMiddleware` 规划步骤；`MemoryMiddleware` 加载固定指引和保存的偏好 | `todos` 状态、新会话模型请求 |
| Skill | `release-plan` 提供发布计划方法，参考文件给出计划结构 | 模型是否读取 Skill 正文和提纲 |
| 记忆 | 将明确要求的格式偏好写入 `/memory/preferences.md`，供新会话加载 | 保存后的文件与新会话请求 |
| 文件后端 | `FilesystemBackend(virtual_mode=True)` 映射 Skill、记忆和计划的虚拟路径 | 实际文件与对应虚拟路径 |

`check_plan` 只检查章节、资料来源标记和放量阶段文本。它不能证明上线计划一定正确，更不能证明未来发布已经成功。模型是否实际调用工具应查看运行记录，不能只看最终回答。

## 本地运行

在 `task8` 目录中执行：

```powershell
uv sync --frozen
uv run --frozen pytest tests -q
uv run --frozen python -X utf8 experiments/offline_demo.py
```

离线测试和实验无需模型密钥。预设模型依次保存偏好，再在新会话规划、读取 Skill 与资料、保存计划、读回并检查。Agent 图、中间件、工具和文件后端真实运行。`offline_demo.py` 还将产物保存为 `artifacts/qingning-release-plan-offline.md`，把精简记录保存为 `evidence/offline-release-plan.json`。预设回复不能证明真实模型会自行选择正确工具。

真实模型入口需要在 `.env` 配置 `OPENAI_API_KEY`、`AGENTSEEK_MODEL` 和 `OPENAI_API_BASE`：

```powershell
Copy-Item .env.example .env
uv run --frozen python -X utf8 experiments/live_demo.py
```

真实模型脚本会先处理明确的格式偏好，再在新会话制定计划。成功时生成 `artifacts/qingning-release-plan.md` 和 `evidence/live-<run-id>.json`；失败也会保留已经取得的证据并报错。模型服务可能收费。完整请求与响应可另开 LangSmith 追踪；本地证据 JSON 只保存精简工具轨迹和文件哈希。

**真实模型运行记录（2026-11-01）：**使用已有模型配置中的 `deepseek-flash` 跑通。模型先调用 `save_preference`；新会话的模型请求中出现保存的格式偏好。计划会话调用了 `read_file`、`write_todos`、两次 `read_source`、`save_plan`、`read_plan` 和 `check_plan`，相关工具返回状态均为 `success`。最后的结构检查为 `ok=true`，证据中的 SHA-256 与当前文件一致。查看[真实模型生成的上线计划](artifacts/qingning-release-plan.md)和[本次精简证据](evidence/live-0bbfc76a4460.json)。这说明本次模型确实走通工具链；结构检查仍不能证明未来发布会成功。

启动 AgentSeek API：

```powershell
uvx agentseek==0.1.2 doctor
uvx agentseek==0.1.2 dev
```

也可以运行 `uv run --frozen agentseek-api dev --port 2025`，然后打开 <http://127.0.0.1:2025/docs>。本目录只提供后端，不包含前端。

## 本次验证与边界

本地离线测试与实验验证同一个 Agent 图的工具、待办中间件、Skill、跨会话格式偏好和文件后端。真实模型是否选择正确工具、计划内容是否准确，须由新场景的真实运行记录判断。

项目资料：[产品简报](sources/product-brief.md)、[发布约束](sources/release-constraints.md)、[Skill](skills/release-plan/SKILL.md)。
