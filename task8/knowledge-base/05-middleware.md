# Deep Agents Middleware：生命周期、任务规划与上下文管理

中间件是 LangChain Agent 的扩展机制，Deep Agents 使用它组合文件工具、记忆、Skill、待办和上下文管理等能力。它允许程序在指定节点介入，或包装一次模型/工具调用。

本文按 **deepagents 0.7.8** 及当前配套 LangChain 实现核对。代码只保留知识点的关键位置；model 表示已创建的模型客户端，backend 表示已配置的 Backend。源码片段用于说明内部机制，不是要求重新实现框架。

## 1. 两类 hook 的区别

### Node-style：在执行节点介入

| hook | 时机 | 常见用途 |
| --- | --- | --- |
| before_agent | 一次 Agent 运行开始前 | 加载当前运行所需资料或初始化观察记录 |
| before_model | 每次调用模型前 | 检查状态、准备输入 |
| after_model | 每次模型返回后 | 检查工具请求或更新状态 |
| after_agent | 一次正常 Agent 运行结束后 | 收尾处理与结果记录 |

一次 invoke 可能包含多轮模型与工具调用，所以 before_model/after_model 可能执行多次。before_agent/after_agent 的“一次”对应一次运行，不等于整个 thread 一生只运行一次，也不表示异常退出必然执行正常收尾。

### Wrap-style：包围模型或工具调用

| hook | 包装对象 | 常见用途 |
| --- | --- | --- |
| wrap_model_call | 一次模型调用 | 修改请求、观察响应、重试或短路 |
| wrap_tool_call | 一次工具调用 | 检查参数、处理结果、访问控制或日志 |

准确名称是 wrap_model_call 和 wrap_tool_call，不是 wrap_agent、wrap_model。wrap-style 同样有明确时机；区别是它拿到 handler，可以控制是否执行、执行前后做什么，而不是“不关心生命周期”。

同步 hook 有相应异步形式，例如 awrap_model_call、awrap_tool_call。使用异步入口时要按当前版本实现相应 hook，不假定任意同步实现都会自动适用。

## 2. 最小使用方式

### 在模型调用前观察状态

```python
from deepagents import create_deep_agent
from langchain.agents.middleware import before_model

@before_model
def show_message_count(state, runtime):
    print("本轮消息数：", len(state["messages"]))
    return None

agent = create_deep_agent(model=model, middleware=[show_message_count])
result = agent.invoke({"messages": [{"role": "user", "content": "请说明你能做什么。"}]})
```

返回 None 表示该 hook 不提交状态更新；有状态更新需求时返回框架支持的更新结构，不是任意修改一个局部字典就认为已经持久保存。

### 包装一次模型调用

```python
from deepagents import create_deep_agent
from langchain.agents.middleware import wrap_model_call

@wrap_model_call
def trace_model(request, handler):
    print("进入模型调用")
    response = handler(request)
    print("模型调用正常返回")
    return response

agent = create_deep_agent(model=model, middleware=[trace_model])
```

handler 表示继续后续调用链。不调用它可以短路，多次调用可以用于有明确策略的重试，但也可能重复请求或副作用；仅记录日志时应正常调用一次并返回结果。

多个 wrapper 会嵌套。当前接口约定列表前面的包装器位于外层，例如 A/B 的正常进入退出顺序是 A 进入、B 进入、B 返回、A 返回。node-style 的调度规则与 wrapper 嵌套不是同一个概念，应按实际 hook 日志观察。

## 3. 为什么要加入任务规划能力

多步骤任务中，结构化待办让当前目标和进度更加明确，但不是替代实际执行的调度器。

| 复杂任务容易出现的问题 | 待办能提供的帮助 | 仍然不能保证什么 |
| --- | --- | --- |
| 遗漏用户要求或忘记下一步 | 列出子任务和待完成项 | 模型必然把所有需求拆分正确 |
| 重复做已经做过的操作 | 显式区分进行中和已完成 | 自动消除所有循环或重复调用 |
| 做完部分工作就声称全部完成 | 暴露剩余事项，便于核对 | completed 必然有真实完成证据 |
| 执行过程中目标发生变化 | 更新计划和后续步骤 | 每次调整都合理或结果一定高质量 |

任务写一半停止可能来自输出上限、上下文超限、网络错误或执行限制。TodoListMiddleware 不能单独解决这些问题，也不会保证任务永不终止。

简单任务可以直接完成，不必为了形式先创建一份待办。

## 4. TodoListMiddleware 怎样实现

它主要组合了四类机制：提供状态字段、注册工具、补充模型提示，以及检查不合适的并发待办请求。

```text
注册 TodoListMiddleware
    ├── state 增加 todos
    ├── 向模型提供 write_todos 工具
    ├── 模型调用前补充待办使用规则
    └── 模型返回后检查同轮多个 write_todos 请求

模型请求 write_todos
    ↓
工具返回 Command，更新 todos 并追加 ToolMessage
    ↓
模型看到执行反馈，继续实际任务
```

### 状态：任务内容与状态

每个 todo 包含 content 和 status，状态为 pending、in_progress、completed。当前源码的 PlanningState 声明：

```python
class PlanningState(AgentState):
    todos: Annotated[NotRequired[list[Todo]], OmitFromInput]
```

这是源码中的字段片段，AgentState、Todo 等是框架类型。todos 进入图状态，并不等于自动写入长期记忆；同 thread 是否能延续，仍与 checkpointer 配置有关。

### 工具：通过 Command 更新状态

下面保留当前 _write_todos 的关键逻辑，省略泛型注解：

```python
from langchain_core.messages import ToolMessage
from langgraph.types import Command

def _write_todos(runtime, todos):
    return Command(update={
        "todos": todos,
        "messages": [ToolMessage(
            f"Updated todo list to {todos}", tool_call_id=runtime.tool_call_id,
        )],
    })
```

Command 同时更新任务列表与消息记录；tool_call_id 关联模型的工具请求和执行反馈。它不是只返回一句“已更新”的字符串。

当前 write_todos 接收的是新列表，替换整个 todos，不是自动按任务名称合并。因此更新一个条目时，也需要保留仍有意义的其他条目。

### 注册：中间件自带工具

构造函数中的关键注册片段如下，相关函数与输入模型均来自该中间件模块：

```python
self.tools = [StructuredTool.from_function(
    name="write_todos",
    description=tool_description,
    func=_write_todos,
    coroutine=_awrite_todos,
    args_schema=WriteTodosInput,
    infer_schema=False,
)]
```

所以业务 tools.py 中可以找不到 write_todos；它由中间件提供。使用 TodoListMiddleware 时无需再手工实现一个同名工具。

### 模型包装：补充规则，而不是替模型规划

wrap_model_call 构造包含待办规则的新系统消息，再通过 `handler(request.override(system_message=new_system_message))` 继续调用。规则说明何时规划、怎样更新、结束后仍需给用户实际答案。

提示词鼓励模型规划，但任务拆分和工具选择仍由模型完成。中间件不会因为用户提出目标，就自己计算一份完整任务计划。

### after_model：检查同轮重复更新

当前实现检查同一模型回复中是否含多个 write_todos 请求，若存在则返回对应错误消息。原因是它们都要替换整份列表，并行更新会产生先后含义不清的问题。

这个检查不是所有业务工具的通用并发锁，也不证明多进程或多个 Agent 共享状态时自动安全。

### 接入 Deep Agent 的核心代码

```python
from deepagents import create_deep_agent
from langchain.agents.middleware import TodoListMiddleware

agent = create_deep_agent(
    model=model,
    middleware=[TodoListMiddleware()],
    system_prompt="复杂任务先规划，并根据实际执行结果更新待办，最后给出产物。",
)
result = agent.invoke({"messages": [{
    "role": "user", "content": "请用待办规划：阅读需求、拟定实现步骤、列出验证方法。",
}]})
print(result.get("todos", []))
```

这里显式加入中间件，避免依赖不同版本的默认装配。看到了 completed 只说明状态被这样声明，还应结合实际产物和执行记录核对。

## 5. 超大工具结果：卸载，不是摘要

FilesystemMiddleware 可以处理过大的工具返回文本。当前默认 tool_token_limit_before_evict=20000，尺寸判断采用近似字符预算，例如每 token 约 4 字符，并非对所有模型精确分词后的统一硬限制。

```text
某次工具返回文本过大
    ↓
原始文本写入当前 Backend
    ↓
工具消息改为文件路径、读取说明和头尾预览
    ↓
模型需要细节时再分页 read_file
```

需要纠正几个具体点：

- 主要对象是工具结果，不是“模型最终回答超过 20000 token”。
- 这是保存原文并缩短内联消息，不是让模型对该结果生成语义摘要。
- 返回的是 Backend 路径，不一定是可以打开的 HTTP URL。
- 当前预览取头 5 行与尾 5 行，中间标记省略，不是固定前 10 条内容。
- 并非所有工具统一走这条路径：ls/glob/grep/read_file 等有自己的输出处理或分页策略，当前实现把七个内置文件工具排除在普通大结果卸载之外。
- 文件写到哪里、保存多久，取决于 Backend；写入默认 StateBackend 不等于存成永久磁盘文件。

### 调整卸载阈值的核心代码

```python
from deepagents import create_deep_agent
from deepagents.middleware.filesystem import FilesystemMiddleware

agent = create_deep_agent(
    model=model,
    backend=backend,
    middleware=[FilesystemMiddleware(
        backend=backend,
        tool_token_limit_before_evict=20000,
    )],
)
```

Deep Agents 默认已经装配文件中间件；这里展示核对版本中的同名配置替换，不是要求额外重复堆叠多个相同中间件。结果实际落点通常位于 Backend 的 artifacts root 下的 large_tool_results 路径。

## 6. 对话接近窗口上限：用摘要控制模型输入

当有效输入接近模型窗口预算时，Deep Agents 的 SummarizationMiddleware 会对较早的历史生成摘要，并保留近期消息。

在核对版本的默认工厂中：

| 模型信息 | 默认触发与保留方式 |
| --- | --- |
| profile 提供 max_input_tokens | 在约 85% 的输入容量触发，保留约 10% 容量对应的近期内容 |
| 未取得该窗口信息 | 回退为 170000 token 触发、保留最近 6 条消息等固定设置 |

这些是当前默认配置，不是“所有模型到 80% 必然压缩”。接入窗口较小的兼容服务时尤其需要核对模型信息或明确设定阈值。

```text
对话输入达到触发条件
    ↓
对较早历史生成摘要，将被压缩历史保存到 Backend
    ↓
模型收到：摘要 + 历史文件路径说明 + 保留的近期消息
    ↓
继续任务，需要细节时再读历史
```

默认历史文件路径形如 `/conversation_history/{session_id}.md`，是 Backend 中的路径。保存的是被压缩的历史，不能简单写成“只把摘要存文件”。摘要内容会帮助接续任务，但“目标、产物、下一步”不构成所有版本统一的三个固定返回字段。

当前 Deep Agents 正常摘要路径通过摘要事件构建发给模型的消息，保留原始 state.messages；不能把它与所有实现中的“删除状态消息”混为一谈。上下文溢出后的回退还有其他处理分支，不在这里展开。

### 明确配置摘要策略的核心代码

```python
from deepagents import create_deep_agent
from deepagents.middleware.summarization import SummarizationMiddleware

agent = create_deep_agent(
    model=model,
    backend=backend,
    middleware=[SummarizationMiddleware(
        model=model,
        backend=backend,
        trigger=("tokens", 8000),
        keep=("messages", 6),
    )],
)
```

8000 是示例自选阈值，不是框架默认值。Deep Agents 默认有摘要能力；显式替换时应完整考虑模型、Backend、trigger 与 keep，不能把多个摘要器随意叠加。

卸载与摘要可以协作：前者减少单次工具文本占用，后者压缩累计历史。框架还存在长用户消息卸载、旧工具参数裁剪等优化，不能把这两项当成所有上下文处理的穷尽清单。

## 容易混淆的地方

| 易混淆概念 | 应怎样区分 |
| --- | --- |
| node-style 与 wrap-style | 前者在节点介入，后者包围具体调用并控制 handler |
| wrap_agent 与实际接口 | 此处使用 wrap_model_call / wrap_tool_call，没有相应的 wrap_agent hook |
| 一次 invoke 与一次模型调用 | 一次运行可以有多轮模型与工具循环 |
| 返回状态更新与修改请求 | 更新 state 与 request.override 是不同层面的操作 |
| 注册待办与自动执行任务 | 中间件提供工具和规则，不会自动完成清单里的业务动作 |
| completed 与真实完成 | 待办状态是声明，需要执行证据支持 |
| 任务规划与无限续写 | 待办不能消除输出限制、上下文限制和网络故障 |
| 工具结果卸载与摘要 | 卸载保留原文并返回引用；摘要用模型提炼较早历史 |
| 20000 与所有模型硬限制 | 这是当前工具结果配置的近似预算，不是模型统一输出上限 |
| 85% 与固定不变的规则 | 触发依赖配置和模型 profile，不是所有版本或模型都一样 |
| 文件引用与长期记忆 | 临时卸载文件不自动成为跨会话共享的用户偏好 |
| 头尾预览与完整结果 | 预览只呈现一部分，需要时通过路径再读原文 |

## 核对与验证范围

接口名称、待办注册和状态更新逻辑、工具结果卸载阈值、预览方式及摘要默认值按当前安装源码核对。关键配置已进行构建检查；直接工具执行、Command 结果和卸载文件行为已做局部验证。

真实模型规划质量、自动摘要生成和连续长任务未在本文整理时运行，不将状态与配置检查描述成真实模型已成功完成整个流程。源码片段只是解释核心机制，省略了异步分支、泛型与外围错误处理。

## 参考资料

- [LangChain：Custom middleware](https://docs.langchain.com/oss/python/langchain/middleware/custom)
- [Deep Agents：Context engineering](https://docs.langchain.com/oss/python/deepagents/context-engineering)
- 当前环境中的 langchain.agents.middleware.todo、deepagents.middleware.filesystem、deepagents.middleware.summarization 与 deepagents.graph 实现。默认行为与返回格式可能随依赖版本变化。
