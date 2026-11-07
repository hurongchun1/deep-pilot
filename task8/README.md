# Task Planner：通用任务规划助手

把用户的目标、时间和约束拆成可执行的行动计划，适用于学习、开发、活动等任务。不需要修改代码或准备固定的两份资料。它生成计划、保存文件并做结构检查，不实际替用户执行任务。

课程学习、实验结果及引用来源汇总见 [Task08 打卡笔记](CHECKIN.md)。

## 从哪里开始看

1. 先看下面的三个输入示例，理解助手的用途。
2. 看 [学习计划样例](artifacts/learning-plan-offline.md)、[开发计划样例](artifacts/development-plan-offline.md)、[活动计划样例](artifacts/event-plan-offline.md)。这些是离线预设内容，不是真实模型输出。
3. 看 [agent.py](agent.py) 的 `build_graph()`，理解模型、工具、中间件和 Skill 如何组合。
4. 看 [tools.py](tools.py)、[规划 Skill](skills/task-planning/SKILL.md) 和[提纲](skills/task-planning/references/plan-outline.md)，理解执行方法。
5. 看 [集成测试](tests/test_integrated_demo.py) 和 [离线脚本](experiments/offline_demo.py)，理解如何验证。

## 可以怎样使用

| 场景 | 用户输入示例 | 计划产物 |
| --- | --- | --- |
| 学习 | 我会 Python 基础，用两周学 pandas 清洗 CSV，每天 1 小时，最终交付脚本和数据对照 | 学习阶段、练习产物、时间安排、验收与调整 |
| 开发 | 一个周末做本地命令行待办工具，支持新增、列出、完成，JSON 存储，不做登录和网页 | 范围确认、实现依赖、验证步骤、交付标准 |
| 活动 | 一周内筹备 10 人线下读书会，活动 90 分钟，预算未定 | 筹备清单、建议议程、风险与待确认事项 |

也可以直接输入其他任务，例如“未来四周整理个人作品集，每周可投入 3 小时”。三个案例用于演示，不是系统支持的任务白名单。

每份计划包含：任务目标、已知条件、行动步骤、验收标准、风险与调整、待确认事项、信息来源。缺少日期时使用相对安排；建议与用户给出的事实分开；未知预算和负责人列为待确认。

## 应用如何工作

用户目标 → 读取规划 Skill 与提纲 → 拆解步骤 → `save_plan` 保存 → `read_plan` 读回 → `check_plan` 检查 → 返回文件。

| 组成 | 作用 |
| --- | --- |
| 业务工具 | 可选地列出和读取资料，保存、读回及检查计划，按明确指令保存偏好 |
| `TodoListMiddleware` | 跟踪规划和保存检查的进度 |
| `MemoryMiddleware` | 加载 AGENTS.md 和已保存的语言、语气或格式偏好 |
| `task-planning` Skill | 按需加载通用规划方法和章节提纲 |
| `FilesystemBackend(virtual_mode=True)` | 映射 Skill、记忆和计划的虚拟路径到 task8 目录 |

用户消息是主要输入。有补充资料时，可创建 `sources/` 并放入 Markdown 文件，在任务中指明即可；助手可以通过 `list_sources` 发现文件、用 `read_source` 读取。新增文件无需修改工具白名单。

仅当用户明确说“请记住以后用某种格式”时才保存偏好。目标、预算和期限属于当前任务，不自动保存为长期记忆。新会话会从 `memory/preferences.md` 加载保存的偏好。

## 本地运行（无需模型密钥）

项目内的 Python 导入统一使用 `task8.*` 包名（例如 `from task8.tools import save_plan`）。
IDE 打开仓库根目录 `deep-pilot`，并选择 `task8/.venv` 中的 Python 解释器。
首次使用或更新打包配置后执行下面的 `uv sync --frozen`，将当前包安装到该环境。
两个实验脚本也支持在 IDE 中直接运行：入口会根据自身文件位置添加仓库根目录，
不依赖 IDE 的工作目录。仍需选择已安装项目依赖的 Python 3.12 或 3.13 解释器。

在 `task8` 目录执行：

```powershell
uv sync --frozen
uv run --frozen pytest tests -q
uv run --frozen python -X utf8 experiments/offline_demo.py
```

默认运行 learning、development、event 三个案例，也可单独运行：

```powershell
uv run --frozen python -X utf8 experiments/offline_demo.py --scenario development
```

生成 `artifacts/<场景>-plan-offline.md` 和 `evidence/offline-<场景>.json`。离线模式使用预设模型回复，但 Agent 图、中间件、Skill 读取、跨会话偏好和文件工具真实运行。它验证工具链，不能证明真实模型会自主拆解任务或选择工具。离线运行在临时工作区保存偏好，不修改项目的偏好文件。

## 真实模型：输入自己的目标

真实模型可使用 `OPENAI_API_KEY` 配合 `AGENTSEEK_MODEL`、`OPENAI_API_BASE`；也可直接使用环境变量 `DEEPSEEK_API_KEY`，此时默认模型为 `deepseek-flash`，默认地址为 DeepSeek 官方接口（可用 `DEEPSEEK_API_BASE` 覆盖）。如果复制 `.env.example` 并改用 DeepSeek 密钥，需同时把其中的 `AGENTSEEK_MODEL` 改为 `deepseek-flash`。运行会产生模型服务费用：

```powershell
uv run --frozen python -X utf8 experiments/live_demo.py --scenario learning
uv run --frozen python -X utf8 experiments/live_demo.py --task "未来四周整理个人作品集，每周可投入 3 小时" --slug portfolio-plan
```

`--task` 覆盖预设案例；`--slug` 指定文件名（不含 `.md`），默认 `task-plan`。重复使用相同名称会覆盖对应计划。脚本先演示明确保存格式偏好，再在新会话规划。成功后生成 `artifacts/<slug>.md` 和 `evidence/planner-live-<run-id>.json`，进入运行后失败也会保留已观察到的精简证据。配置或参数校验失败发生在运行前，不生成证据。完整模型请求和响应可通过可选的 LangSmith 追踪查看。

若从项目根目录启动，先执行 `cd task8`；虚拟环境已激活时也可运行 `python -m experiments.live_demo --scenario learning`。出现“真实运行未覆盖全部必需步骤”时，报错末尾和当次 `evidence/planner-live-<run-id>.json` 的 `unmet_checks` 会列出缺少的步骤。模型可能已生成并通过结构检查，但最后没有调用 `write_todos` 把规划待办标记为 `completed`；这属于流程未完成，计划文件仍可在 `artifacts/` 查看。再次运行可使用新 `--slug`，避免覆盖上次计划。

启动 AgentSeek API：

```powershell
uv run --frozen agentseek-api dev --port 2025
```

图入口为 `./agent.py:graph`，图名称为 `task_planner`。本目录只提供后端，API 文档地址为 <http://127.0.0.1:2025/docs>。

## 验证边界

`check_plan` 仅检查七个必要章节及非空正文，不检查日期合理性、事实准确性、排期可行性或来源是否支持结论。工具返回 `ok=true` 只能说明结构通过。真实模型是否按要求规划，需查看当次工具记录并人工审阅计划。

通用任务规划版已提供离线验证及一次 `deepseek-flash` 真实模型学习场景运行，产物见 `artifacts/learning-plan-live.md`，证据见 `evidence/planner-live-4aad1ec7cc74.json`。
