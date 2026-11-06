# Deep Agents Memory：短期状态、长期记忆与会话隔离

Agent 的记忆需要解决三件事：当前会话怎样延续、哪些信息允许跨会话使用、保存的信息怎样进入模型上下文。保存、加载与使用是不同步骤，不能只配置一个存储对象就认为三者全部完成。

本文按 **deepagents 0.7.8、Python 3.12** 核对接口。示例只保留记忆组件与会话调用的关键代码。model 表示已创建的模型客户端，workspace 表示已存在工作目录的绝对 Path；省略模型连接、重复初始化和消息打印循环。

## 1. 长期记忆与短期记忆怎样区分

主要依据是信息的使用范围，不是有没有写到数据库，也不是经过了多久。

| 类型 | 作用范围 | 示例 |
| --- | --- | --- |
| 短期记忆 | 当前会话或任务 | 之前聊过的早餐、当前修改要求、临时任务进度和草稿 |
| 长期记忆 | 在允许的范围内跨会话复用 | 用户语言偏好、项目背景、开发规则、长期积累的知识 |

“这次修改后运行测试”是当前任务要求；“以后这个项目的修改都要运行测试”可以成为项目规则；“以后所有项目都这样”才适合考虑更广的偏好范围。不能把当前任务要求自动升级成所有会话共享的规则。

长期也不代表所有用户共享。用户、项目、组织或 Agent 可以拥有不同的记忆范围，加载时只使用当前身份和任务允许访问的内容。

## 2. state、checkpointer、Backend 和中间件各负责什么

| 组件 | 职责 | 不能混同的事情 |
| --- | --- | --- |
| 图状态 state | 承载 messages、todos、files 等当前执行数据 | 不等于某个具体数据库 |
| checkpointer | 保存和恢复图状态快照 | 不自动筛选值得跨会话保存的信息 |
| thread_id | 标识要延续的会话状态 | 自身不是存储，也不是用户认证 |
| StateBackend | 将虚拟文件操作映射到 state.files | 不负责保存全部聊天消息 |
| StoreBackend | 将文件操作映射到 Store 和 namespace | 不自动把所有数据注入提示词 |
| MemoryMiddleware | 从指定来源加载文件，并按配置加入系统提示 | 不自动保存整段对话或所有偏好 |

会话消息的延续可以直接配置 checkpointer，不需要为了 messages 额外手写一个 StateBackend。StateBackend 参与的是虚拟文件的读写；这些文件又随图状态一起被 checkpoint 保存。

记忆文件也可以通过 FilesystemBackend 保存在磁盘，不必一定使用 StoreBackend。若采用 StoreBackend，是否重启后保留取决于底层 Store，而不是类名里有 Store 就自动具备数据库持久化。

## 3. 示例约定

文件型示例中，workspace 下已准备 AGENTS.md 和 memory 目录；AGENTS.md 放工作规则，memory/preferences.md 放用户偏好。后文直接展示如何保存和加载，不再展开创建目录等通用文件操作。

## 4. 短期记忆：通过 checkpointer 延续会话

同一个图和 checkpointer 下，使用相同 thread_id 可以恢复会话状态；新的 thread_id 不直接继承旧会话的 messages。

### 核心代码

```python
from deepagents import create_deep_agent
from langgraph.checkpoint.memory import InMemorySaver

agent = create_deep_agent(model=model, checkpointer=InMemorySaver())
config_a = {"configurable": {"thread_id": "breakfast-a"}}
config_b = {"configurable": {"thread_id": "breakfast-b"}}

agent.invoke({"messages": [{"role": "user", "content": "我今天早餐吃了燕麦和鸡蛋。"}]}, config_a)
continued = agent.invoke({"messages": [{"role": "user", "content": "我早餐吃了什么？"}]}, config_a)
separate = agent.invoke({"messages": [{"role": "user", "content": "你有我的早餐记录吗？"}]}, config_b)
# continued 延续 a 的历史；separate 使用 b 的独立历史。
```

新会话可能猜测常见早餐，因此验证隔离应查看实际消息历史，不能把模型猜中内容当作拿到了旧 thread 状态。

InMemorySaver 保存于进程内存；程序结束后不保留。使用 Postgres 等持久化 checkpointer 可以恢复已保存会话，但它依然是按 thread 组织的短期状态，不因此变成用户级共享偏好。

## 5. 长期记忆：保存文件，再在新会话加载

长期记忆至少包含两条链：

```text
写入：用户明确要求记住 → 模型调用保存工具 → 存储更新
加载：新会话开始 → 读取指定记忆文件 → 放入状态副本 → 加入模型系统提示
```

MemoryMiddleware 主要负责第二条链。写入可以通过明确的自定义工具、内置文件编辑工具或应用逻辑实现，不强制要求一个固定名字的 save_preference。

### MemoryMiddleware 的参数

| 参数 | 含义 |
| --- | --- |
| backend | 访问记忆文件的 Backend；这里显式构造中间件时必须提供 |
| sources | 记忆文件路径列表，例如 /AGENTS.md 和 /memory/preferences.md |
| system_prompt | 可选的记忆格式模板；不传则使用默认模板 |

sources 是参数名，不等于项目里某个名为 sources 的目录。AGENTS.md 常放开发者维护的工作规则，preferences.md 可放用户明确保存的偏好；二者都能作为来源，但来源与授权不同。

自定义 system_prompt 字符串必须包含 `{agent_memory}`。传空字符串 `""` 会触发校验错误；传 None 表示不追加记忆提示片段，但内容仍可加载进 memory_contents。中间件的模板与 Agent 自己的 system_prompt 也不是同一个配置。

课程中也可能使用 create_deep_agent 的 `memory=["/memory/preferences.md"]`。在核对版本中，这个参数会为该来源装配 MemoryMiddleware；它是简化接入方式，不是另一种记忆存储。下面为了展示 backend、sources 和模板的关系，显式配置中间件，不再重复传 memory。

### 核心代码：工具保存偏好，新 thread 加载

```python
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.middleware.memory import MemoryMiddleware
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

preference_path = workspace / "memory/preferences.md"

@tool
def save_format_preference(value: str) -> str:
    """保存用户明确要求以后使用的输出格式。"""
    preference_path.write_text(f"format: {value}\n", encoding="utf-8")
    return "已保存格式偏好。"

backend = FilesystemBackend(root_dir=workspace, virtual_mode=True)
agent = create_deep_agent(
    model=model,
    backend=backend,
    tools=[save_format_preference],
    checkpointer=InMemorySaver(),
    middleware=[MemoryMiddleware(
        backend=backend,
        sources=["/AGENTS.md", "/memory/preferences.md"],
        system_prompt="<agent_memory>\n{agent_memory}\n</agent_memory>",
    )],
)
agent.invoke({"messages": [{"role": "user", "content": "请调用 save_format_preference，记住以后用中文分节 Markdown。"}]},
             {"configurable": {"thread_id": "remember"}})
planned = agent.invoke({"messages": [{"role": "user", "content": "请给我一周学习计划。"}]},
                       {"configurable": {"thread_id": "new-plan"}})
```

这里保存的是明确的格式偏好，不是完整聊天。该演示工具只更新一个格式字段，不是支持多字段并发合并的通用存储服务。真实多用户应用还需要按身份隔离目录或使用 namespace。

FilesystemBackend 的文件在固定目录中可以跨程序运行保留；是否加载到某个会话，仍由来源配置和加载时机决定。

两个 thread 共用偏好文件，但不共用上一轮聊天历史。仅看回答是中文不能证明偏好成功加载，因为用户输入本身也是中文；应结合工具结果、文件内容、memory_contents 和实际模型请求判断。

## 6. 用 CompositeBackend 组合会话文件与共享记忆

当临时草稿应按 thread 隔离，而偏好应按用户跨 thread 共享，可以组合：

```text
普通路径      → StateBackend → 当前 thread 的 files
/memories/   → StoreBackend → 当前用户 namespace 中的文件
MemoryMiddleware → 从 /memories/preferences.md 加载偏好
```

下面用 InMemoryStore 演示范围控制。它支持本进程内跨 thread 共享，不保证程序重启后保留。数据库持久化可以替换底层实现，但不改变职责划分。

### 核心代码：按用户身份加载不同记忆

```python
from dataclasses import dataclass
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from deepagents.backends.utils import create_file_data
from deepagents.middleware.memory import MemoryMiddleware
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

@dataclass(frozen=True)
class UserContext:
    user_id: str

store = InMemoryStore()
store.put(("user-a", "memory"), "/preferences.md", create_file_data("format: 中文分节 Markdown"))
store.put(("user-b", "memory"), "/preferences.md", create_file_data("format: 简短英文段落"))
backend = CompositeBackend(
    default=StateBackend(),
    routes={"/memories/": StoreBackend(
        namespace=lambda runtime: (runtime.context.user_id, "memory"),
    )},
)
agent = create_deep_agent(
    model=model, backend=backend, store=store,
    context_schema=UserContext, checkpointer=InMemorySaver(),
    middleware=[MemoryMiddleware(backend=backend, sources=["/memories/preferences.md"])],
)
agent.invoke({"messages": [{"role": "user", "content": "请介绍你的能力。"}]},
             {"configurable": {"thread_id": "user-a-chat"}}, context=UserContext("user-a"))
agent.invoke({"messages": [{"role": "user", "content": "请介绍你的能力。"}]},
             {"configurable": {"thread_id": "user-b-chat"}}, context=UserContext("user-b"))
```

路径路由剥离 `/memories/` 前缀，所以 Store 内 key 使用 `/preferences.md`，不是再次拼完整虚拟路径。

context 中的用户身份在本地示例由代码指定；实际服务应由可信入口提供。namespace 用于组织范围，不替代认证。checkpointer 的 thread 也必须与用户关联，不能让不同用户复用同一 thread_id 后以为 namespace 会同时隔离聊天历史。

两个请求分别加载各自用户范围中的偏好。该片段聚焦用户身份与 namespace 的接入；前一节展示偏好工具写入，Backend 主题中的 StateBackend 说明会话草稿文件隔离。

## 7. MemoryMiddleware 怎样把文件送到模型

在核对版本中的关键链路为：

```text
before_agent
    ↓ state 中尚无 memory_contents 时
backend 下载或读取 sources 指定的文件
    ↓
返回 memory_contents 状态更新，由框架合并
    ↓
模型调用前，从 request.state 取出内容
    ↓
_format_agent_memory 替换 {agent_memory}
    ↓
追加系统提示，继续调用模型
```

文件不存在会被跳过，不等于自动创建。sources 指向什么，加载什么；中间件不自动遍历并保存全部聊天。

如果 state 已经存在 memory_contents 键，包括值为空字典时，加载逻辑会跳过重新读取。因此文件被更新后，已有会话的副本不一定立刻刷新；新会话可以重新加载。需要实时刷新时应明确设计刷新机制，而不是假定写文件会广播到所有 state。

中间件的 system_prompt 模板负责包装记忆，Agent 的 system_prompt 负责角色和业务规则。前者可以不自定义；自定义时必须保留占位符。

## 8. 保存多久、共享给谁与上下文多大是不同问题

- 数据库存了多年，也可以只属于原会话；短期范围不等于只能短暂保存在内存。
- 长期记忆进入 state 后，是当前运行的一份副本，不会因载体变化就自动变成会话临时要求。
- PostgreSQL 可以用于持久化 checkpoint，也可以作为 Store 的存储基础；“用了 PostgreSQL”本身不能判断记忆类型。
- 保存了完整历史，不代表每次都应该把全部历史发给模型。上下文窗口、裁剪和摘要是另一层管理问题。
- 摘要是历史压缩，不自动决定哪些内容可以跨会话共享。记忆提炼、写入条件和适用范围仍需要应用规则。

## 容易混淆的地方

| 容易混淆的概念 | 正确区别 |
| --- | --- |
| 长期记忆与全局共享 | 可以按用户、项目或组织限定范围，不是所有会话、所有用户都能读 |
| 短期记忆与 StateBackend | 短期消息属于图状态，StateBackend 具体管理其中的虚拟文件 |
| checkpointer 与 Store | 前者恢复 thread 状态，后者组织可跨 thread 使用的数据 |
| 保存文件与加载记忆 | 写入只改变存储；模型要看到内容，还需要加载或读取 |
| MemoryMiddleware 与保存工具 | 中间件负责读取和注入，工具或应用逻辑负责明确写入 |
| sources 与目录名 | sources 是记忆文件路径列表，不是固定名为 sources 的文件夹 |
| 中间件模板与角色提示 | memory 的模板包装加载内容；Agent 提示描述角色和工作方式 |
| 空字符串与省略模板 | 空字符串不满足占位符校验；省略使用默认值，None 则不追加提示 |
| 内存 Store 与数据库持久化 | 前者可在本进程内跨 thread 共享，但重启后不自动保留 |
| namespace 与用户认证 | namespace 管理数据范围，不能替代对身份和 thread 所有权的校验 |
| 文件最新值与 state 副本 | 修改文件不会自动刷新所有活跃会话中的 memory_contents |
| 模型回复与记忆证据 | “我记住了”或回答风格符合预期，不单独证明写入和加载成功 |

## 示例验证范围

三段核心代码的语法和 Agent 构建配置已检查；文件记忆加载、模板替换与校验、Store 路由及按用户读取的底层行为已直接核对。真实模型的保存、选择和回答流程未在本文整理时运行，不将其写为固定成功结果。

示例使用内存 checkpointer、内存 Store 或工作目录中的文件。未完成 PostgreSQL 部署、进程重启恢复或自动缓存刷新验证。

## 参考资料

- [Datawhale《Deep Agents 实战》：长期记忆](https://github.com/datawhalechina/deepagents-in-action/blob/main/content/ch08-long-term-memory.md)
- [Deep Agents：Memory](https://docs.langchain.com/oss/python/deepagents/memory)
- [LangChain / LangGraph：Memory overview](https://docs.langchain.com/oss/python/concepts/memory)
- deepagents 0.7.8 的 MemoryMiddleware、StateBackend、StoreBackend 与 create_deep_agent 实现。课程及在线文档可能采用更新版本，本文代码按声明版本核对。
