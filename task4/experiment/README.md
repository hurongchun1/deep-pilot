# experiment/ 实验排障记录

本目录是 task4 的手工实验场（`agent_alive.py` + `research_find.py`），用于验证 deepagents 声明式子 agent、结构化输出、TodoListMiddleware 与流式观察。本文档按“**问题从哪里来 → 为什么会这样 → 怎么解决**”记录运行过程中踩过的坑。

## 运行方式

在仓库根目录（`deep-pilot/`）执行：

```powershell
.\venv\Scripts\python.exe task4\experiment\agent_alive.py
```

- 依赖装在**根目录 venv**（langchain、deepagents、tavily-python、python-dotenv）
- 配置来自 `task4/.env`（脚本内 `load_dotenv` 按 `__file__` 定位到父目录，与启动目录无关）

---

## 问题：Thinking mode does not support this tool_choice（HTTP 400）

### 1. 问题从哪里来

**现场报错**（节选）：

```
langchain_openai.chat_models.base.OpenAIInvalidRequestError: Error code: 400 -
{'error': {'message': 'Thinking mode does not support this tool_choice ...
During task with name 'model' and id '...'
During task with name 'tools' and id '...'
```

**报错的三个线索**：

| 线索 | 解读 |
| --- | --- |
| `400` + `tool_choice` | 请求体里带了 `tool_choice`，服务端拒绝 |
| `Thinking mode` | 拒绝的原因是模型处于**思考模式** |
| 任务栈 `model` 套在 `tools` 里面 | 出错的模型调用发生在**子 agent 内部**（`task` 工具在 tools 节点内运行子图），即 `search_subagent` 的调用 |

**涉及代码**：

- `research_find.py`：`search_subagent` 声明了 `"response_format": ResearchFind`（第 51 行）
- `agent_alive.py`：`create_deep_agent(..., subagents=[search_subagent])`（第 44 行）

### 2. 为什么会这样

因果链，每一环都有出处：

**第 1 环：声明式子 agent 带 `response_format`**

deepagents 把 `response_format` 编译进子 agent 的图。

**第 2 环：langchain 对“有结构化输出”的模型调用强制 `tool_choice`**

`venv/Lib/site-packages/langchain/agents/factory.py:1473-1475`：

```python
# Force tool use if we have structured output tools
tool_choice = "any" if structured_output_tools else request.tool_choice
```

`"any"` 在 `venv/Lib/site-packages/langchain_openai/chat_models/base.py:2581-2582` 被转成 `"required"`：

```python
elif tool_choice == "any":
    tool_choice = "required"
```

**第 3 环：DeepSeek 思考模式默认开启，且拒绝 `required`**

官方文档（<https://api-docs.deepseek.com/zh-cn/api/create-chat-completion>）：

> 思考模式下不支持 `required` 和指定具体 tool 的用法，API 会返回 400 错误。请先关闭思考模式。

且 `thinking.type` 可选值为 `enabled`（**默认**）/ `disabled`——即 `deepseek-flash` 不传任何参数就运行在思考模式下。

**第 4 环：相撞**

langchain 强制注入 `tool_choice="required"` × DeepSeek 默认思考模式 → 400。

**为什么没更早暴露**：两个条件都是**隐式**的——`tool_choice` 是 langchain 内部强制注入的，实验代码里看不到；思考模式是服务端默认值，本地无感知。两个隐式条件叠加，直到真发请求才炸。

### 3. 怎么解决

#### 方案 A（已采用）：关思考模式，保留结构化输出

`agent_alive.py:30`：

```python
extra_body = {"thinking": {"type": "disabled"}},
```

- `extra_body` 会被 langchain-openai 原样合并进请求体（`base.py:1146` 定义、`1572` 合并），官方文档即用此参数控制 thinking
- 等价写法：`{"thinking": {"reasoning_effort": "none"}}`
- 代价：主 agent 同样不思考（实验无妨，更快更省 token）；只想关子 agent 的话，在 `SubAgent` spec 里单独挂一个带 `extra_body` 的 model 实例

#### 方案 B：去掉结构化输出，保留思考模式

删除 `search_subagent` 里的 `"response_format": ResearchFind`，子 agent 按 system_prompt 输出纯文本。langchain 不再强制 `tool_choice`（默认 `auto`），思考模式下可用。

**结论：在 DeepSeek 上，结构化输出与思考模式二选一。** 两组恰好构成干净的单变量 A/B 对照：

| 组 | 变量 | 预期结果 |
| --- | --- | --- |
| A | 关思考 + `response_format` | 子 agent 返回 `{summary, confidence, source}` JSON |
| B | 保留思考 + 纯文本 | 子 agent 返回格式化文本 |

---

## 附录：同目录代码踩过的其他坑（均已修）

| # | 现象 | 根因 | 修法 |
| --- | --- | --- | --- |
| 1 | `400 - you passed gpt-3.5-turbo` | `ChatOpenAI` 模型参数名写成 `name`（那是 Runnable 显示名），被静默吞掉，`model` 退回默认值 `gpt-3.5-turbo` | `name=` → `model=` |
| 2 | 修完 1 后模型名仍不对 | `.env` 的 `AGENTSEEK_MODEL=openai:deepseek-flash`，`openai:` 前缀是 `init_chat_model()` 的提供商语法，直传 `ChatOpenAI` 不剥（实测 `model_name` 原样透传） | `.removeprefix("openai:")` |
| 3 | `AttributeError: 'NoneType' object has no attribute 'get'` | `stream_mode="updates"` 下，node-style 钩子返回 `None`（无状态更新，如 PatchToolCalls 无需补齐时）时，chunk 是 `{节点名: None}` | 遍历前判空 `if not update: continue` |
| 4 | 流式输出结构不对 | `stream_mode="messages"` 的 chunk 是 `(消息, metadata)` 元组，不是 dict，与 `chunk.items()` 写法不匹配 | 改用 `"updates"` 匹配遍历写法 |

## 待验证

- [ ] `TAVILY_API_KEY` 是否有效（空 key 时子 agent 搜索会失败）
- [ ] 方案 A / B 的 A/B 对照运行与记录
