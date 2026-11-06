# Deep Agents Backend：存储方式、接入与权限控制

Backend 决定 Agent 的文件存放在哪里，以及是否具备命令执行能力。本文按“用途 → 关键参数 → 核心接入代码 → 行为与边界”介绍五种常用实现。

示例接口核对版本为 **deepagents 0.7.8、Python 3.12**。示例只展示 Backend 的关键构建与 Agent 接入，省略模型连接、测试数据准备和重复打印。

## 示例约定

`model` 表示已创建的模型客户端；`workspace` 表示选定的、已存在工作目录的绝对 Path。示例提到的输入文件应已放在该目录中。代码只聚焦组件配置与调用，不是从零启动的完整程序；不依赖配套源码文件。

## 1. Backend 与 Agent 的关系

```text
用户消息
    ↓
Deep Agent 调用模型
    ↓
模型请求 read_file、write_file 等内置工具
    ↓
工具通过 Backend 操作数据
    ↓
工具结果回到模型，继续处理或给出最终回答
```

通过 `create_deep_agent(backend=...)` 接入 Backend 后，框架提供的文件工具使用该实现。普通自定义工具如果直接调用 `Path.write_text()`，则不会自动经过 Backend。

直接执行 `backend.read()` 可以观察存储行为，但完整接入还应包含模型、Agent 构建和实际工具请求。

| Backend | 文件位置 | 共享或隔离依据 | 命令执行 |
| --- | --- | --- | --- |
| FilesystemBackend | 本地磁盘 | 实际根目录和文件路径 | 不提供 |
| LocalShellBackend | 本地磁盘 | 运行环境与操作系统权限 | 提供 execute |
| StateBackend | 图状态的 files 字段 | checkpointer 与 thread_id | 不提供 |
| StoreBackend | LangGraph Store | Store 实例与 namespace | 不提供 |
| CompositeBackend | 根据路径选择其他 Backend | 各路由对应的实现 | default 支持时可委派执行 |

## 内置文件工具：模型怎样操作 Backend

Backend 是文件操作的实现接口，不只代表一种内存虚拟文件系统。模型看到的七项常用文件工具由 FilesystemMiddleware 提供，再委派给当前 Backend。

| 工具 | 主要用途 | 关键参数与边界 |
| --- | --- | --- |
| read_file | 读取文本或受支持的媒体文件 | 文本使用 file_path、offset、limit，按行分页；offset 从 0 开始 |
| ls | 列出目录直接包含的文件与子目录 | path 指定目录，不等同于递归搜索整个目录树 |
| glob | 按路径模式查找文件 | pattern 和可选 path，例如 *.py、**/*.md；匹配文件名或路径，不搜索正文 |
| write_file | 创建或覆盖文本文件 | file_path、content；现有文件可能整体被替换 |
| edit_file | 对现有正文做精确文本替换 | file_path、old_string、new_string、replace_all；不是按行号随意插入 |
| grep | 在文件内容中查找文本 | pattern、path、glob、output_mode、max_count；本版本 pattern 是字面字符串，不是任意正则 |
| delete | 删除文件或受支持的目录目标 | file_path；目录删除在本地实现中可递归，不应理解为可恢复的回收站操作 |

execute 是执行型 Backend 才能提供的额外能力，不属于这七项纯文件工具。

### read_file：偏移的是行，不是字节

模型请求中的参数可以是：

```python
read_args = {"file_path": "/notes.md", "offset": 100, "limit": 50}
```

它表示从第 101 行开始最多取 50 行。此字典只展示参数结构，不会自行执行工具。当前默认 offset=0、limit=100；显示的行号从 1 开始，编辑时不要把显示行号一起写回正文。

对图片、PDF 等受支持格式，返回可能是媒体内容块，而不是文本行。Backend 可以提供 base64 编码数据，但模型是否能处理该格式还取决于模型能力和服务接口。不能把“可以传递二进制内容”理解为“模型能理解任意二进制文件”；文本分页参数也不能直接套到所有媒体格式。

### ls 与 glob：目录列举和路径搜索不同

ls 列举一个目录的直接内容；glob 按模式搜索路径。底层 Backend 的 ls 结果可以含大小等元信息，但当前内置 ls 工具主要向模型返回路径列表，不能保证展示文件大小。需要大小时应确认实际工具结果，或为该需求提供明确工具。

### write_file 与 edit_file：整体覆盖和局部修改不同

当前核对版本的写入行为可以直接从底层接口观察：

```python
backend.write("/demo-note.md", "第一版正文")
backend.write("/demo-note.md", "第二版正文")  # 覆盖整个文件
backend.edit("/demo-note.md", old_string="第二版", new_string="修订版")
```

这段直接调用 Backend，不经过模型。write 的 content 是全文；edit 的 old_string/new_string 是文本，旧文本不唯一时默认会报错，需要明确是否 replace_all。模型从 read_file 看到的行号是显示信息，不属于待替换的原文。

### grep：匹配文件、匹配行与统计结果不同

```python
grep_args = {
    "pattern": "TODO",
    "path": "/",
    "glob": "*.py",
    "output_mode": "content",  # 也可以是 files_with_matches 或 count
    "max_count": 100,
}
```

files_with_matches 返回包含匹配的文件，content 返回匹配行，count 返回按文件的匹配统计。当前实现按匹配行组织结果，不要把一行中同一词出现两次直接算成两条匹配行。上限或截断意味着结果可能不完整，不能把“只返回 100 项”理解成“全部只有 100 项”。

### 最小 Agent 接入

```python
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

agent = create_deep_agent(
    model=model,
    backend=FilesystemBackend(root_dir=workspace, virtual_mode=True),
)
result = agent.invoke({"messages": [{
    "role": "user", "content": "先列出根目录，再查找包含 TODO 的 Python 文件，按需读取匹配位置。",
}]})
```

不必把七个内置工具再次手工放入 tools 列表。具体是否可用，还受 Backend 能力、文件权限和工具可见性配置影响；模型选择了工具也不代表执行成功，应查看返回结果。

## 2. FilesystemBackend：让 Agent 访问本地文件

适合读取项目资料、编辑本地文件、保存产物。文件通常在进程结束后仍保留；例子中的 workspace 指向实际项目目录。

### 关键参数

| 参数 | 含义 |
| --- | --- |
| root_dir | 文件路径解析的根目录，建议传绝对 Path |
| virtual_mode | True 时按虚拟根目录解释路径，并检查解析目标；0.7.8 默认 True |
| max_file_size_mb | 部分搜索操作的文件大小阈值，不是所有读写操作统一的大小上限 |

`virtual_mode=True` 时，虚拟 `/notes.md` 对应 `root_dir/notes.md`。`virtual_mode=False` 时，真实绝对路径可以不受 root_dir 限制，root_dir 主要影响相对路径解析。

### 核心接入代码

```python
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

backend = FilesystemBackend(root_dir=workspace, virtual_mode=True)
agent = create_deep_agent(model=model, backend=backend)
result = agent.invoke({"messages": [{
    "role": "user", "content": "用 read_file 读取 /notes.md。",
}]})
```

这里不是手动把 read_file 注册进 tools；Deep Agents 根据 Backend 装配内置文件能力。模型提出调用，框架再通过 FilesystemBackend 执行。

虚拟路径有助于固定路径语义和限制文件接口的访问范围，但不是操作系统沙箱。Backend 的 read/write 也有自己的结果对象：应检查 error；当前核对实现的 write 会创建或覆盖整个文件；局部替换应使用 edit，而不是把整份正文重新写一遍。

## 3. LocalShellBackend：让 Agent 执行主机命令

LocalShellBackend 在文件操作之外提供 execute。适合受控开发环境中的命令运行、脚本调用和测试执行。

### 关键参数

| 参数 | 含义 |
| --- | --- |
| root_dir | 文件操作根目录，同时是命令的工作目录 |
| virtual_mode | 文件操作的虚拟路径语义，不限制任意 shell 命令 |
| timeout | 默认执行超时秒数，可按次覆盖 |
| max_output_bytes | 捕获输出的字节上限，超出截断 |
| env | 子进程环境变量 |
| inherit_env | 是否继承当前进程环境，0.7.8 默认 False |

### 核心接入代码

```python
from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend

backend = LocalShellBackend(
    root_dir=workspace,
    virtual_mode=True,
    timeout=10,
    max_output_bytes=2000,
    inherit_env=False,
)
agent = create_deep_agent(model=model, backend=backend)
result = agent.invoke({"messages": [{
    "role": "user", "content": "用 execute 执行 echo hello，告诉我结果。",
}]})
```

execute 的运行结果需要结合输出、退出码和是否截断判断；命令已经运行不代表执行成功。

`virtual_mode=True` 不会把 shell 限制在 root_dir。LocalShellBackend 在宿主机执行命令，需要真正隔离时应选择沙箱环境；文件路径规则不能代替进程隔离。继承环境还可能把当前进程中的凭据传给子进程，应按需配置。

## 4. StateBackend：让文件跟随当前会话状态

StateBackend 将文件保存在图状态的 files 字段，不自动落盘。0.7.8 中直接构造 `StateBackend()`，读写时需要图执行上下文。

它与 checkpointer 的关系是：

```text
StateBackend → 读写 state.files
checkpointer → 保存和恢复图状态
thread_id    → 选择某个会话的状态
```

StateBackend 本身没有 root_dir 参数，不需要为每个 thread 手动创建文件夹。没有 checkpointer 仍可在一次运行中使用状态；后续独立调用不能仅凭相同 thread_id 恢复旧数据。

### 核心接入代码

```python
from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from langgraph.checkpoint.memory import InMemorySaver

agent = create_deep_agent(
    model=model, backend=StateBackend(), checkpointer=InMemorySaver(),
)
config_a = {"configurable": {"thread_id": "a"}}
config_b = {"configurable": {"thread_id": "b"}}
agent.invoke({"messages": [{"role": "user", "content": "用 write_file 将‘草稿’保存到 /draft.md。"}]}, config_a)
continued = agent.invoke({"messages": [{"role": "user", "content": "用 read_file 读取 /draft.md。"}]}, config_a)
separate = agent.invoke({"messages": [{"role": "user", "content": "用 read_file 尝试读取 /draft.md。"}]}, config_b)
```

若第一轮实际成功写入，同一个 checkpointer 下的会话 a 可以延续状态；会话 b 不直接共享这份 files。需要根据真实工具消息判断，而不是只比较模型文字。

InMemorySaver 将快照保存在内存，进程结束后不保留。跨进程恢复需要持久化 checkpointer；短期会话状态即使持久化，也不自动变成跨会话共享偏好。

## 5. StoreBackend：让不同会话访问共享数据

StoreBackend 使用 LangGraph Store，并通过 namespace 区分数据范围。它不直接决定哪些内容应该被记住，保存策略仍由应用和工具决定。

### 关键参数

| 参数 | 含义 |
| --- | --- |
| namespace | 0.7.8 必填工厂函数，接收运行时并返回字符串元组 |
| store | 可直接传入 Store；省略时在图执行上下文中取得 |

下面将 Store 传给 Agent，Backend 在运行时从图上下文取得它。这与直接传给 StoreBackend 是两种接入方式，不需要重复传入。

### 核心接入代码

```python
from deepagents import create_deep_agent
from deepagents.backends import StoreBackend
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.memory import InMemorySaver

store = InMemoryStore()
backend = StoreBackend(namespace=lambda _runtime: ("demo-user", "files"))
agent = create_deep_agent(
    model=model, backend=backend, store=store, checkpointer=InMemorySaver(),
)
agent.invoke({"messages": [{"role": "user", "content": "用 write_file 将‘偏好中文’写入 /profile.md。"}]},
             {"configurable": {"thread_id": "a"}})
loaded = agent.invoke({"messages": [{"role": "user", "content": "用 read_file 读取 /profile.md。"}]},
                      {"configurable": {"thread_id": "b"}})
```

两个 thread 的聊天状态分别保存，但它们访问相同 Store、相同 namespace，所以可以读取共享文件。这里不会自动把文件注入系统提示；读取 Store 文件与 MemoryMiddleware 加载指定记忆来源是不同机制。

namespace 不是磁盘文件夹。更换 namespace 可以区分不同用户的数据；实际应用应从可信身份生成范围，而不是让所有用户共用示例的 demo-user。

InMemoryStore 只在内存中保存，跨 thread 共享不等于进程重启后永久保留。需要重启后保留时，应选择持久化 Store。相同 namespace 但换成全新的内存 Store，也不会自动拥有原数据。

## 6. CompositeBackend：在一个 Agent 中组合多种 Backend

CompositeBackend 根据路径选择目标实现。它不独立保存文件，也不会自动复制各路由的数据。

### 关键参数与路由规则

| 参数 | 含义 |
| --- | --- |
| default | 没有路径命中时使用的 Backend |
| routes | 路径前缀到 Backend 的映射 |
| artifacts_root | 部分中间件卸载内容的根路径，0.7.8 默认 /，不是全部文件的总根目录 |

路径按最长前缀匹配，命中的前缀会被剥离。例如 `/shared/profile.md` 路由到共享 Store 时，目标收到的是 `/profile.md`。

### 核心接入代码

```python
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend, StoreBackend
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

backend = CompositeBackend(
    default=StateBackend(),
    routes={
        "/workspace/": FilesystemBackend(root_dir=workspace, virtual_mode=True),
        "/shared/": StoreBackend(namespace=lambda _rt: ("demo-user", "files")),
    },
)
agent = create_deep_agent(
    model=model, backend=backend, store=InMemoryStore(), checkpointer=InMemorySaver(),
)
result = agent.invoke({"messages": [{
    "role": "user", "content": "用 write_file 将‘产物’保存到 /workspace/result.md。",
}]}, {"configurable": {"thread_id": "a"}})
```

这组路由可处理三类路径：

| Agent 使用的路径 | 目标 Backend | 实际位置 |
| --- | --- | --- |
| /draft.md | default：StateBackend | 当前 thread 的 files |
| /workspace/result.md | FilesystemBackend | workspace/result.md |
| /shared/profile.md | StoreBackend | Store 中对应 namespace 下的 /profile.md |

若再配置 `/workspace/reports/`，它比 `/workspace/` 更长，会优先匹配；目标收到去除完整前缀后的路径。路由名称不同也不保证底层隔离，两条路由可以指向同一存储范围。

命令执行不按文件路径路由。CompositeBackend.execute 委派给 default；只在某条 routes 中放 LocalShellBackend，不代表 execute 自动运行在那条路由中。

## 7. FilesystemPermission：为内置文件工具配置权限

FilesystemPermission 通过 `create_deep_agent(permissions=...)` 接入，在内置文件工具层检查操作，而不是给每个 Backend 自动加上通用权限控制。

| 字段 | 含义 |
| --- | --- |
| operations | read 或 write；读取涵盖列举与搜索，写入涵盖编辑和删除 |
| paths | glob 路径模式，例如 /docs/** |
| mode | allow 允许、deny 拒绝、interrupt 暂停等待审批 |

规则按声明顺序取第一条匹配项；没有匹配时默认允许。这与 CompositeBackend 按最长路径前缀选择目标是两套规则。

### 核心接入代码：资料只读、产物可写

```python
from deepagents import FilesystemPermission, create_deep_agent
from deepagents.backends import FilesystemBackend

agent = create_deep_agent(
    model=model,
    backend=FilesystemBackend(root_dir=workspace, virtual_mode=True),
    permissions=[
        FilesystemPermission(operations=["read"], paths=["/docs/**", "/artifacts/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/artifacts/**"], mode="allow"),
        FilesystemPermission(operations=["read", "write"], paths=["/**"], mode="deny"),
    ],
)
result = agent.invoke({"messages": [{
    "role": "user", "content": "尝试用 write_file 创建 /docs/new.md，被拒绝就告诉我原因。",
}]})
```

最后一条是兜底拒绝；没有它，其他未命中的路径仍可能被允许。兜底放最前面则会先命中，后续允许规则不能生效。

如果模型没有尝试写资料区，不能仅凭文件不存在就断言拒绝规则得到验证。应同时查看对应工具请求与拒绝结果。

权限边界：

- 内置文件工具遵循这些规则；自定义工具直接访问磁盘、直接调用 Backend 和任意 shell 命令，不自动受其保护。
- 与 CompositeBackend 配合时，按工具看到的虚拟路径设置规则，不把真实磁盘路径与虚拟前缀混用。
- interrupt 用于等待人工审批，需要 checkpointer 和中断恢复流程；不能只改 mode 就假设操作会自动继续。
- 需要控制自定义工具时，应在实际访问路径上实施限制，而不是假设 permissions 已覆盖。

## 8. 如何选择与组合

- 需要 Agent 操作实际项目目录：使用 FilesystemBackend。
- 还需要在受控主机环境运行命令：使用 LocalShellBackend；需要隔离执行则选择沙箱方案。
- 文件只属于当前会话：使用 StateBackend，按恢复需求配置 checkpointer。
- 文件需跨会话共享：使用 StoreBackend，规划 Store 生命周期与 namespace。
- 不同路径需要不同存储：使用 CompositeBackend，将会话草稿、共享数据和磁盘产物分别路由。
- 需要限制内置文件工具的访问：配置 FilesystemPermission，并确认其不覆盖的调用路径。

Backend 提供存储与执行接口；工具提供具体操作入口，模型选择是否调用，中间件与状态机制参与执行过程。理解接入后的协作关系，比只记住五个类名更重要。

## 容易混淆的地方

| 容易混淆的概念 | 应怎样区分 |
| --- | --- |
| 构建 Backend 与接入 Agent | 创建对象只是配置能力，传给 create_deep_agent 的 backend 后，内置文件工具才使用它 |
| Backend 与工具 | 工具是模型可请求的操作入口，Backend 是文件或执行能力的实际实现 |
| root_dir 与 virtual_mode | root_dir 指定解析基准；virtual_mode 决定虚拟路径语义，关闭后不能把根目录当访问边界 |
| 虚拟路径限制与沙箱 | 文件接口的路径检查不等于进程隔离，尤其不能限制任意 shell 命令 |
| StateBackend 与 checkpointer | 前者管理 state.files，后者保存与恢复图状态；thread_id 自身不保存数据 |
| StoreBackend 与 MemoryMiddleware | 前者提供按 namespace 存取文件的能力，后者读取配置来源并注入提示；保存文件不等于自动进入模型上下文 |
| 跨 thread 共享与重启持久化 | 同一内存 Store 可跨 thread 共享，但进程结束后不会自动保留 |
| namespace 与磁盘目录 | namespace 是 Store 的逻辑范围，不是自动创建的磁盘文件夹，也不替代用户身份授权 |
| Composite 路由与文件复制 | 路由只决定操作交给谁，不自动把文件复制到所有实现 |
| 路由顺序与权限顺序 | Composite 按最长前缀，权限按第一条匹配规则；两者不能混用理解 |
| 文件权限与所有访问方式 | FilesystemPermission 主要约束内置文件工具，不自动覆盖直接 Backend 调用、自定义磁盘工具或 shell |
| 工具请求与执行成功 | 模型提出调用后仍可能参数错误或权限拒绝，要结合工具结果、实际文件或状态判断 |

## 版本与验证范围

本文核心代码的语法与 Agent 构建配置已核对，真实模型请求未在本文整理过程中运行；不将模型一定调用指定工具写成既定结果。

五种 Backend 的底层存储、真实 LangGraph 状态操作、namespace 隔离、路径路由及本地工作目录查询已另行运行验证。它们支持对机制的解释，但不能替代 Agent 真实模型调用的验证。数据库重启持久化、interrupt 恢复和沙箱隔离不在本文示例验证范围内。

## 参考资料

- [Deep Agents：Backends](https://docs.langchain.com/oss/python/deepagents/backends)
- [Deep Agents：Permissions](https://docs.langchain.com/oss/python/deepagents/permissions)
- deepagents 0.7.8 的 Backend、create_deep_agent 和 FilesystemMiddleware 实现。在线文档可能更新，复用示例时应核对实际版本。
