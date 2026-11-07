# Task08 打卡笔记：通用任务规划助手

## 做了什么

我做了一个通用任务规划助手。用户可以直接描述学习、开发或活动目标；Agent 根据目标和约束生成行动计划，保存为 Markdown，读回后做结构检查。需要补充资料时才读取 `sources/`。

代码入口见 [agent.py](agent.py)、[tools.py](tools.py) 和 [task-planning Skill](skills/task-planning/SKILL.md)，运行说明见 [README.md](README.md)。

## 关键实现：五项能力如何组合

### 1. 规划中间件

我在 `create_deep_agent()` 中加入 `TodoListMiddleware`，要求 Agent 用 `write_todos` 跟踪理解需求、拆解、保存与检查这几个步骤。

```python
# agent.py，节选
middleware=[
    TodoListMiddleware(),
    MemoryMiddleware(
        backend=backend,
        sources=["/AGENTS.md", "/memory/preferences.md"],
        system_prompt="<agent_memory>\n{agent_memory}\n</agent_memory>",
    ),
],
```

对应的系统提示词要求“多步骤任务先用 write_todos”。待办状态说明 Agent 做到了哪一步，但不能替代对计划文件的检查。参考课程[第 4 章：任务规划与分解](https://datawhalechina.github.io/deepagents-in-action/chapters/ch04-task-planning/)。

### 2. Skill

Agent 挂载 `/skills/`，再读取 [task-planning Skill](skills/task-planning/SKILL.md) 和[参考提纲](skills/task-planning/references/plan-outline.md)。Skill 规定从用户输入提取目标、时间、产物与限制，区分已知事实和建议，并按顺序保存、读回、检查计划。

```python
# agent.py，节选
return create_deep_agent(
    model=chat_model,
    skills=["/skills/"],
    backend=backend,
    # 其他配置见源码
)
```

```markdown
<!-- skills/task-planning/SKILL.md，节选 -->
3. 使用 `write_todos` 跟踪理解需求、拆解步骤、保存和检查。
5. 使用 `save_plan` 保存，再用 `read_plan` 读回，最后用 `check_plan` 检查。
```

这套方法适用于学习、开发、活动等输入，具体步骤仍由用户的目标决定。参考课程[第 7 章：Skills](https://datawhalechina.github.io/deepagents-in-action/chapters/ch07-skills/)。

### 3. Tools

我把资料发现、计划保存、读回、结构检查和偏好保存封装为工具。最关键的是让计划真正落盘，再检查刚保存的文件。

```python
# agent.py，节选
tools=[list_sources, read_source, save_plan, read_plan, check_plan, save_preference]
```

```python
# tools.py，节选
@tool
def save_plan(slug: str, content: str) -> str:
    """将 Markdown 行动计划保存为 artifacts/<slug>.md。"""
    if not content.strip():
        raise ValueError("计划内容不能为空")
    target = _plan_path(slug)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"已保存 artifacts/{slug}.md"

@tool
def read_plan(slug: str) -> str:
    """读回 artifacts/<slug>.md 中已保存的行动计划。"""
    return _plan_path(slug).read_text(encoding="utf-8")
```

`check_plan` 使用以下章节清单核对文件；实现中还会检查每节正文是否为空。

```python
# tools.py，节选
REQUIRED_HEADINGS = (
    "任务目标", "已知条件", "行动步骤", "验收标准", "风险与调整",
    "待确认事项", "信息来源",
)
```

`ok=true` 只表示结构通过，不表示内容准确或计划可行。

### 4. Memory

我用 `MemoryMiddleware` 在新会话加载 `/AGENTS.md` 和 `/memory/preferences.md`。只有用户明确要求记住语言、语气或格式时才调用 `save_preference`；普通任务目标和期限不写入长期记忆。

```python
# agent.py，节选
MemoryMiddleware(
    backend=backend,
    sources=["/AGENTS.md", "/memory/preferences.md"],
    system_prompt="<agent_memory>\n{agent_memory}\n</agent_memory>",
)
```

```python
# tools.py，节选
if key not in {"language", "tone", "format"}:
    return "参数错误：key 只能填写英文标识 language、tone 或 format；请改正后重试。"
```

实验中写入的偏好是“行动计划使用中文、分节 Markdown 格式”，见 [preferences.md](memory/preferences.md)。真实模型曾先尝试无效键 `plan_format`，随后改为有效的 `format`。参考课程[第 8 章：长期记忆](https://datawhalechina.github.io/deepagents-in-action/chapters/ch08-long-term-memory/)。

### 5. Backend

我用 `FilesystemBackend` 给 Agent 的内置文件能力和 `MemoryMiddleware` 提供存储位置；`virtual_mode=True` 让它们用 `/skills/`、`/memory/` 这样的虚拟路径访问 Task08 项目中的文件。

```python
# agent.py，节选
backend = FilesystemBackend(root_dir=root, virtual_mode=True)
return create_deep_agent(
    model=chat_model,
    backend=backend,
    skills=["/skills/"],
    # 其他配置见源码
)
```

计划由 `save_plan` 写入 `artifacts/`，偏好由 `save_preference` 写入 `memory/`。配置 Backend 提供访问基础，并不意味着计划会自动保存。

## 实现后得到了什么

在 `task8` 目录执行：

```powershell
uv sync --frozen
uv run --frozen pytest tests -q
uv run --frozen python -X utf8 experiments/offline_demo.py
```

2026-11-02 本地重新运行测试，结果为 **19 passed**。离线脚本覆盖学习、开发、活动三个输入。可查看[离线学习计划](artifacts/learning-plan-offline.md)、[开发计划](artifacts/development-plan-offline.md)、[活动计划](artifacts/event-plan-offline.md)和对应的[运行证据](evidence/README.md)。证据中的 `mode=scripted` 表示模型回复预设；它验证 Agent 图、中间件、Skill 读取、跨会话偏好加载及文件工具流程，**不能证明真实模型会自主完成这些步骤**。

真实模型入口是 `experiments/live_demo.py`，支持 `--task` 直接传入其他目标。本次用环境变量 `DEEPSEEK_API_KEY` 调用 DeepSeek 官方兼容接口，模型为 `deepseek-flash`。一次成功运行生成了[两周 pandas 学习计划](artifacts/learning-plan-live.md)和[精简运行证据](evidence/planner-live-4aad1ec7cc74.json)：模型读取了 Skill 和提纲，使用 `write_todos`，依次保存、读回并检查计划，`check_plan` 返回 `ok=true`。

随后一次使用默认文件名 `task-plan` 的真实运行也生成了[计划文件](artifacts/task-plan.md)，且 `check_plan` 返回 `ok=true`，但最后一项待办仍是 `in_progress`。因此，`live_demo.py` 按“所有待办均完成”的严格条件抛出异常；过程保存在[失败运行证据](evidence/planner-live-95e5229bee65.json)。这个报错不表示计划没有生成，而是说明这次执行没有完成全部验收步骤。

## 学习心得与边界

这次实践让我分清了五项能力的职责：规划中间件记录过程，Skill 规定方法，Tools 生成并检查产物，Memory 保存跨会话偏好，Backend 提供文件访问基础。它们组合后，同一个 Agent 就能处理不同类型的规划任务，不必为每个案例写一套固定流程。

我也看到“文件已生成”“结构检查通过”“Agent 已完成全部步骤”是三个不同的判断。真实模型可能尝试无效参数，也可能忘记更新最后一个待办，所以运行证据要同时记录工具调用、检查结果和待办状态。结构检查只确认格式；计划是否符合用户目标、资料是否可靠、时间安排是否可行，仍需人工审阅。

## 参考资料

- Datawhale《Deep Agents 实战》[第 4 章：任务规划与分解](https://datawhalechina.github.io/deepagents-in-action/chapters/ch04-task-planning/)
- Datawhale《Deep Agents 实战》[第 7 章：Skills](https://datawhalechina.github.io/deepagents-in-action/chapters/ch07-skills/)
- Datawhale《Deep Agents 实战》[第 8 章：长期记忆](https://datawhalechina.github.io/deepagents-in-action/chapters/ch08-long-term-memory/)
- [课程源码仓库](https://github.com/datawhalechina/deepagents-in-action)
- [DeepSeek API 接入说明](https://api-docs.deepseek.com/guides/codex)
