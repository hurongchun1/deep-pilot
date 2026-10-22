# 第 5 章笔记：子 Agent 与上下文隔离

> 来源：[Deep Agents 实战 · 第 5 章](https://datawhalechina.github.io/deepagents-in-action/chapters/ch05-subagents/)｜基线：Deep Agents v0.7
>
> 本笔记修正了原总结的三处事实错误：
>
> 1. 字典方式的必填字段是 `name` / `description` / `system_prompt`，不是 `name` / `skill` / `description`；
> 2. general-purpose 是**常驻**子 Agent，新增其他子 Agent 不会顶掉它；
> 3. `CompiledSubAgent` 要求传入图的 State 必须包含 `messages` 键。

## 1. 动机：为什么需要子 Agent

### 1.1 上下文膨胀

以「搜索 LangGraph 技术文档」为例，一个子任务可能包含：

- 5 次网络搜索，每次返回 3000+ tokens；
- 多次 `write_file` 保存中间结果；
- 多次 `read_file` 回顾整理。

这些工具调用记录会全部堆进主 Agent 的上下文。但主 Agent 根本不需要知道这些细节，它只需要最终的研究摘要。

### 1.2 Context Quarantine：隔离的是上下文，不是数据

工作流程只有四步：

1. 主 Agent 通过 `task` 工具委派：`task(subagent_type="researcher", description="...")`；
2. 子 Agent 在**独立上下文**中执行，中间的工具调用与返回不进入主 Agent 对话；
3. 共用 Backend 时，**文件仍然可以共享**——隔离不等于数据隔离；
4. 子 Agent 完成后，只把最终结果作为 ToolMessage 返回给主 Agent。

因此信息通道只有两条：

- **进**：`task` 的 `description`（委派任务说明）；
- **出**：子 Agent 的最终结果。

优点是把中间过程挡在主上下文之外；代价是主 Agent 看不到中间过程，调试需要靠 streaming / trace（`name` 会写入 `lc_agent_name` 元数据）。

> 项目经理的比喻：项目经理不需要参加每一场技术讨论会，只需要看到负责人提交的总结报告。

### 1.3 隔离 vs 压缩：两类机制的分工

| 机制 | 出处 | 触发方式 | 局限 |
| --- | --- | --- | --- |
| 大结果自动卸载 | 第 3 章 | 工具输入/输出超过 20,000 tokens（`tool_token_limit_before_evict`）→ 写入文件 + 保留预览 | 大结果已经进过一次上下文 |
| 对话历史总结 | 第 3 章 | 达到摘要阈值后，旧消息存入 Backend，模型输入换成「摘要 + 近期消息」 | 有信息损耗，且需要额外的摘要调用 |
| 上下文隔离 | 本章 | 委派时就把执行过程分区 | 子 Agent 若回传大量原始数据，隔离直接失效 |

补充（源码核实）：声明式子 Agent 的默认中间件栈本身就包含 Filesystem 与 summarization 中间件，所以子 Agent 内部同样会卸载/压缩——这正是把「脏活」关在子 Agent 里的意义：压缩成本与信息损耗不转嫁给主 Agent。

## 2. 适用场景

| 场景 | 是否用子 Agent | 理由 |
| --- | --- | --- |
| 需要多次搜索和整理的研究任务 | ✅ | 大量中间结果会膨胀主 Agent 上下文 |
| 需要特殊工具或指令的专业任务 | ✅ | 子 Agent 可以有自己的工具集和系统提示词，且只拿到最小权限 |
| 需要不同模型能力的任务 | ✅ | 轻量模型做快查、强推理模型做深度分析 |
| 需要高层协调的复杂任务 | ✅ | 主 Agent 专注协调，子 Agent 专注执行 |
| 单步简单查询 | ❌ | 委派开销大于收益（多一次模型调用 + 序列化 + 子 Agent 启动） |
| 需要主 Agent 看到子 Agent 完整调用过程 | ❌ | 主 Agent 只收到最终结果，过程不可见 |

一句话判据：**中间过程又长又脏、主 Agent 只关心结论 → 用；主 Agent 需要看过程，或一步就能做完 → 不用。**

## 3. 两种构建方式

### 3.1 字典方式（最常用）

必填三个字段，各司其职：

| 字段 | 作用 |
| --- | --- |
| `name` | 唯一标识符，主 Agent 通过 `task(subagent_type=...)` 指定委派给谁；同时作为流式输出和追踪中的 `lc_agent_name` 元数据 |
| `description` | 主 Agent 据此决策「何时委派、委派给谁」 |
| `system_prompt` | 子 Agent 自己的指令，**不继承**主 Agent |

> 示意片段：`internet_search` 是应用自定义工具（非 Deep Agents 内置），`/skills/...` 代表项目中实际存在的 Skill 目录。

```python
from deepagents import create_deep_agent

research_subagent = {
    "name": "researcher",
    "description": "深入研究特定主题，需要多次搜索、交叉验证和综合时使用",
    "system_prompt": """你是一位专业研究员。你的任务是：
1. 把研究问题拆解为多个搜索查询
2. 用 internet_search 搜索相关信息
3. 整理发现，写成简洁摘要
4. 列出关键发现和信息来源

注意：返回结果控制在 500 字以内，只返回核心发现。""",
    "tools": [internet_search],        # 可选：省略则继承主 Agent；显式指定则完全替换
    "skills": ["/skills/research/"],   # 可选：不继承主 Agent
}

agent = create_deep_agent(
    model="google_genai:gemini-3.1-pro-preview",
    skills=["/skills/main/"],          # 只给主 Agent 和 general-purpose
    subagents=[research_subagent],     # researcher 只拿到 /skills/research/
)
```

#### 字段全表与继承规则

| 字段 | 必填 | 继承主 Agent？ | 规则 |
| --- | --- | --- | --- |
| `name` | ✅ | — | 唯一标识符，同时写入追踪元数据 |
| `description` | ✅ | — | 主 Agent 的路由依据 |
| `system_prompt` | ✅ | ❌ 不继承 | 每个子 Agent 必须独立定义 |
| `tools` | 可选 | ✅ 默认继承 | 显式指定后**完全替换（不合并）** |
| `model` | 可选 | ✅ 默认继承 | 支持 LangChain 模型对象或 `"provider:model"` 字符串 |
| `middleware` | 可选 | ❌ 不继承 | 子 Agent 自己的中间件 |
| `interrupt_on` | 可选 | ✅ 默认继承 | 子 Agent 的人工审批配置，可覆盖主 Agent |
| `skills` | 可选 | ❌ 不继承 | 指定后运行独立的 SkillsMiddleware，技能状态与主 Agent 完全隔离 |
| `response_format` | 可选 | ❌ 不继承 | 结构化输出 schema，需 deepagents>=0.5.3 |
| `permissions` | 可选 | ✅ 默认继承 | 显式提供后**整体替换**，不是叠加 |

三个实操易错点：

1. **`tools` 是替换不是追加**：写了 `tools=[internet_search]`，主 Agent 显式传入的其他工具不会自动带上。但内置文件工具（`read_file` / `write_file` / `ls` / `grep` 等）由 FilesystemMiddleware 注入，不属于 `tools` 参数，所以仍然可用（源码核实）。
2. **`permissions` 同样整体替换**：省略时继承父规则，显式提供后不会与父规则叠加。只读审计类子 Agent 必须写一套闭合的权限规则，否则容易意外放开写入。
3. **`skills` 只有 general-purpose 会继承**：主 Agent 的 `skills=` 会传给 general-purpose，其他声明式子 Agent 必须自己配 `skills`。

#### 结构化返回：`response_format`

默认主 Agent 收到子 Agent 最后一条消息的自由文本。指定 Pydantic schema 后，主 Agent 始终收到合法 JSON，便于程序化处理：

```python
from pydantic import BaseModel, Field

class ResearchFindings(BaseModel):
    summary: str = Field(description="研究摘要")
    confidence: float = Field(description="置信度 0-1")
    sources: list[str] = Field(description="信息来源 URL 列表")

research_subagent = {
    "name": "researcher",
    "description": "研究特定主题并返回结构化发现",
    "system_prompt": "深入研究给定主题，返回你的发现。",
    "tools": [internet_search],
    "response_format": ResearchFindings,  # 需要 deepagents>=0.5.3
}
# 主 Agent 的 ToolMessage 将收到：
# '{"summary": "...", "confidence": 0.87, "sources": ["https://..."]}'
```

### 3.2 CompiledSubAgent：集成 LangGraph 工作流

适用于多步骤、带分支/循环逻辑的工作流，或已经有现成 LangGraph 图的场景：

```python
from deepagents import create_deep_agent, CompiledSubAgent
from langchain.agents import create_agent

# 用 LangChain 创建一个自定义 Agent 图
custom_graph = create_agent(
    model=model,
    tools=[statistical_analysis, generate_chart],
    system_prompt="你是数据分析专家，擅长统计分析和可视化。",
)

# 包装为 CompiledSubAgent
data_subagent = CompiledSubAgent(
    name="data-analyzer",
    description="执行复杂的数据分析任务，包括统计分析和图表生成",
    runnable=custom_graph,  # 传入编译好的 LangGraph 图
)

agent = create_deep_agent(
    model=model,
    subagents=[data_subagent],
)
```

> ⚠️ 硬性约束：传入的 LangGraph 图的 **State 中必须包含 `messages` 键**，否则对接失败。这是自定义图包装时最容易踩的坑。

### 3.3 字典 vs CompiledSubAgent

| 场景 | 推荐方式 | 理由 |
| --- | --- | --- |
| 大多数情况 | 字典方式 | 简单直观，配置灵活 |
| 子 Agent 需要复杂多步骤工作流 | CompiledSubAgent | 可用 LangGraph 图 API 定义分支、循环 |
| 子 Agent 已有现成 LangGraph 图 | CompiledSubAgent | 直接复用，无需重写 |

## 4. General-purpose 子 Agent

### 4.1 它是常驻的，不会被其他子 Agent 顶掉

**修正原总结**：即使不定义任何子 Agent，Deep Agents 也自带一个 general-purpose；新增其他子 Agent 之后，它依然存在。只有两种情况不会自动添加：

1. 传入一个 `name="general-purpose"` 的**同名 spec** —— 这是覆盖，不是删除；
2. 在 HarnessProfile 中设置 `GeneralPurposeSubagentProfile(enabled=False)` —— 显式禁用。

源码中的自动添加条件（deepagents v0.7，`graph.py`）：

```python
if gp_profile.enabled is not False and not any(
    spec["name"] == GENERAL_PURPOSE_SUBAGENT["name"] for spec in inline_subagents
):
    # 自动追加 default general-purpose
```

若禁用且不传任何同步子 Agent，`task` 工具本身就不会暴露（异步子 Agent 不受影响）。

### 4.2 继承什么、不继承什么

| 项目 | 是否继承主 Agent | 说明 |
| --- | --- | --- |
| 显式传入的 `tools` | ✅ | 默认子 Agent 复用主 Agent 的工具 |
| `model` | ✅ | 默认同模型 |
| `skills` | ✅ | 主 Agent 的 `skills=` 会传给 general-purpose |
| `interrupt_on` / `permissions` | ✅ | 审批与文件权限默认继承 |
| `system_prompt` | ❌ | 使用自己的 `DEFAULT_SUBAGENT_PROMPT`（0.0.6 起不再继承主 Agent 提示词） |
| 仅为主 Agent 新增的 middleware | ❌ | 只继承主 Agent 对默认中间件槽位的同名覆盖 |
| Todo 能力 | ❌ | v0.7 默认栈不含 `TodoListMiddleware`，主 Agent 的 Todo 配置不会传下去 |

所以它更准确的说法是：**能力上的分身（同模型、同工具），行为上的另一个人（不同提示词）**。另外，默认隔离模式下子 Agent 不读写主 Agent 的 todos，双方各自维护任务清单。

### 4.3 禁用姿势

不要用 `excluded_middleware` 排除 `SubAgentMiddleware`——这会直接抛 `ValueError`。正确做法是两步：

```python
from deepagents import create_deep_agent
from deepagents.profiles import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    register_harness_profile,
)

# 第一步：为指定模型注册 Harness Profile
register_harness_profile(
    key="openai:zai-org/GLM-5.2",
    profile=HarnessProfile(
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)
    ),
)

# 第二步：不传任何同步子 Agent
agent = create_deep_agent(
    model=model,
    subagents=[],
)
```

### 4.4 覆盖姿势与单独启用 Todo

用同名 spec 覆盖提示词、模型或工具：

```python
agent = create_deep_agent(
    model=model,
    tools=[internet_search],
    subagents=[
        {
            "name": "general-purpose",  # 覆盖默认子 Agent
            "description": "通用助手，处理各种委派任务",
            "system_prompt": "你是一个通用助手。",
            "tools": [internet_search],
            "model": ChatOpenAI(  # 子 Agent 用更强的模型
                model="zai-org/GLM-5.2",
                api_key=os.environ["SILICONFLOW_API_KEY"],
                base_url="https://api.siliconflow.cn/v1",
            ),
        },
    ],
)
```

需要让子 Agent 也使用 `write_todos` 时，必须在它自己的 `middleware` 里单独启用：

```python
from langchain.agents.middleware import TodoListMiddleware

agent = create_deep_agent(
    model=model,
    middleware=[TodoListMiddleware()],  # 主 Agent 的规划能力
    subagents=[
        {
            "name": "general-purpose",
            "description": "处理需要规划的委派任务",
            "system_prompt": "为委派任务制定计划，执行后返回结果。",
            "middleware": [TodoListMiddleware()],  # 子 Agent 单独启用
        },
    ],
)
```

两处 Todo 配置相互独立：主 Agent 设置的 `tool_description` 等参数不会自动应用到子 Agent。其他声明式子 Agent 同理。

## 5. 多子 Agent 协作样板

实际项目中最常见的模式：主 Agent 做协调者，多个专业子 Agent 串联执行。

```python
import os
from langchain_openai import ChatOpenAI
from deepagents import create_deep_agent
from langchain.agents.middleware import TodoListMiddleware

model = ChatOpenAI(
    model="zai-org/GLM-5.2",
    api_key=os.environ["SILICONFLOW_API_KEY"],
    base_url="https://api.siliconflow.cn/v1",
)

subagents = [
    {
        "name": "data-collector",
        "description": "从多个来源收集原始数据，包括网络搜索和 API 调用",
        "system_prompt": "你是数据收集专家。搜索并整理相关数据，返回结构化的数据摘要。",
        "tools": [internet_search, api_call],
    },
    {
        "name": "data-analyzer",
        "description": "对收集到的数据进行统计分析，提取关键洞察",
        "system_prompt": "你是数据分析专家。分析数据并提取 3-5 个关键发现，控制在 300 字以内。",
        "tools": [statistical_analysis],
    },
    {
        "name": "report-writer",
        "description": "根据分析结果撰写专业报告",
        "system_prompt": "你是技术写作专家。根据提供的分析结果撰写清晰、专业的报告。",
        "tools": [format_document],
    },
]

agent = create_deep_agent(
    model=model,
    middleware=[TodoListMiddleware()],
    system_prompt="""你是一位项目协调者。面对复杂任务时：
1. 先用 write_todos 制定计划
2. 将数据收集委派给 data-collector
3. 将分析工作委派给 data-analyzer
4. 将报告撰写委派给 report-writer
5. 整合各子 Agent 的输出，形成最终结果""",
    subagents=subagents,
)
```

执行流程：

1. 主 Agent 用 `write_todos` 制定计划；
2. `task(subagent_type="data-collector", ...)` → 返回数据摘要；
3. `task(subagent_type="data-analyzer", ...)` → 返回关键发现；
4. `task(subagent_type="report-writer", ...)` → 返回报告；
5. 主 Agent 整合输出。

每一步子 Agent 都在独立上下文中工作，主 Agent 只看到精炼结果。注意：串行委派不是并行，并行属于第 6 章 Async Subagent 的内容。

## 6. 最佳实践 5 条

1. **description 要具体、行为导向**：主 Agent 靠它决策路由。
   `"执行深度网络研究，需要多次搜索、交叉验证和综合分析时使用"` ✅
   `"做研究"` ❌
2. **system_prompt 要详细**：必须包含工具使用指导、输出格式和字数限制，这直接决定回传给主 Agent 的质量。
3. **工具集要精简**：最小权限原则，只给子 Agent 它真正需要的工具。
4. **不同子 Agent 用不同模型**：快查用轻量模型，深度分析用强推理模型。
5. **返回结果要精简**：在 `system_prompt` 中明确「不要返回原始数据、中间计算过程、详细工具输出」，并给出字数上限。

第 5 条是隔离能否成立的关键：**如果子 Agent 把大量原始数据返回给主 Agent，就失去了上下文隔离的意义。**

## 7. 常见问题排查

### 7.1 子 Agent 没被调用，主 Agent 自己做了所有工作

- 原因：主 Agent 无法从 `description` 判断何时该委派。
- 解法一：把 `description` 改得更具体、更行为导向；
- 解法二：在主 Agent 的 `system_prompt` 中明确要求委派，例如「面对复杂任务时，使用 `task()` 委派给对应子 Agent，保持自身上下文干净」。

### 7.2 上下文依然膨胀

- 原因：子 Agent 返回了大量原始数据。
- 解法一：在子 Agent 的 `system_prompt` 中强制简洁返回，限定字数；
- 解法二：让子 Agent 先把原始数据 `write_file` 到文件，只返回分析摘要。

### 7.3 调用了错误的子 Agent

- 原因：多个子 Agent 的 `description` 过于相似，主 Agent 无法区分。
- 解法：在 `description` 中写清使用边界。例如 `quick-researcher` 写「简单快速查询，1-2 次搜索，适合基本事实或定义」，`deep-researcher` 写「复杂深入研究，多次搜索与综合分析，适合生成全面报告」。

## 8. 小结

1. 核心动机是 Context Quarantine：子 Agent 在独立上下文中工作，主 Agent 只收到精炼结果；文件可通过共享 Backend 互通。
2. 字典方式必填 `name` / `description` / `system_prompt`；`tools` 默认继承、显式即替换；`skills` 不继承；`model` 默认继承。
3. general-purpose 默认常驻，只有同名覆盖或 `enabled=False` 才会不自动添加；它不继承主 Agent 的 `system_prompt`，Todo 需单独启用。
4. CompiledSubAgent 适合复杂图工作流，State 必须包含 `messages`。
5. `response_format` 让子 Agent 返回 JSON（>=0.5.3）；最佳实践的核心是「描述具体、提示详细、工具精简、模型匹配、返回精炼」。

### 版本提醒

| 行为 | 版本要求 |
| --- | --- |
| 子 Agent 不继承主 Agent `system_prompt` | 自 0.0.6 起（预发布从 0.0.6rc3） |
| `response_format` 结构化输出 | deepagents>=0.5.3 |
| 默认 general-purpose / 声明式子 Agent 不含 Todo | v0.7 默认配置 |
| `backend=` 工厂函数写法移除 | v0.7 已移除，需直接传 Backend 实例 |
