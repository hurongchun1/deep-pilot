# 第 3 章实验：虚拟文件系统与 Backend

这组实验直接使用 `task2` 锁定的 `deepagents==0.7.8`。`ch03_lab.py` 用预设回复代替模型决策，**文件工具、Backend、LangGraph 图仍是真实实现**，运行时不调用模型 API。最后的 `live_ch03.py` 才使用 `.env` 中的真实模型，可能产生 API 费用。

## 准备

在新的 PowerShell 窗口运行。`uvx agentseek dev` 可以继续留在另一个窗口，但以下脚本不需要网关，也不需要访问浏览器的 `/agent`。

```powershell
cd D:\project\pythonProjects\deep-pilot\task2
$env:PYTHONIOENCODING='utf-8'
$env:LANGSMITH_TRACING='false'
uv run --no-sync python experiments\ch03_lab.py tools
```

`--no-sync` 使用已经由 `agentseek task sync` 安装的 `.venv`，避免每次实验重新解析依赖。如果提示缺少依赖，先执行 `uvx agentseek task sync`。若 PowerShell 仍显示中文乱码，先运行 `chcp 65001` 再试。

## 实验 1：七个文件工具与 grep 的三种模式

```powershell
uv run --no-sync python experiments\ch03_lab.py tools
```

| 观察点 | 运行前预测 | 实际应看到 |
| --- | --- | --- |
| `write_file` | 建立 `/notes/plan.md` | `Updated file`；文件在 State 中，没有同名 Windows 文件 |
| `ls` | 列出目录 | `/notes/plan.md` |
| `read_file(offset=1, limit=2)` | 读第二、三行 | 显示第 2、3 行及剩余行提示。`offset` 从 0 开始，显示行号从 1 开始 |
| `edit_file` | 精确替换首个 TODO | 显示替换 1 处；编辑前脚本已读过该文件 |
| `glob` | 按文件名找 | 返回 `.md` 路径，搜索的是路径名 |
| `grep(files_with_matches)` | 找有 TODO 的文件 | 只返回路径 |
| `grep(content)` | 看 TODO 的位置 | 返回文件路径、行号和匹配行 |
| `grep(count)` | 看还有几个 TODO | 返回每个文件的匹配数，此例为 1 |
| `delete` | 删除文件 | 随后的 `read_file` 报找不到文件 |

容易混淆的地方：当前工具名是 **`delete`**；`grep` 按**字面量**查找，不把 `.*` 当正则表达式；当前 Agent 工具的 `content` 模式只输出匹配行，不自动带前后文。`ls` 的 Agent 可见文本也没有展开全部元数据，Backend 的结构化结果和工具展示文本要分开看。[课程对应章节](https://datawhalechina.github.io/deepagents-in-action/chapters/ch03-virtual-filesystem/#grep%E4%B8%89%E7%A7%8D%E8%BE%93%E5%87%BA%E6%A8%A1%E5%BC%8F)

## 实验 2：State、线程与 checkpointer

```powershell
uv run --no-sync python experiments\ch03_lab.py state
```

脚本创建 `StateBackend()` 和 `InMemorySaver()`。在 `thread-A` 写 `/scratch/state.txt`，同一个 `thread_id` 的下一轮能读到；`thread-B` 读不到。

这里的 **Agent State** 是 LangGraph 图运行时维护的状态对象。`StateBackend` 把虚拟文件放到其中的 `files` 字段，它不是一个 Windows 文件夹。`thread_id` 选中哪一份状态；checkpointer 决定状态能否跨多次 `invoke` 保存。这个实验的 `InMemorySaver` 只在当前 Python 进程内有效，关闭脚本就消失。模板原本的 `build_agent()` 没传 checkpointer，所以不能直接假定模板在两个独立调用之间保留 State 文件。[官方说明](https://docs.langchain.com/oss/python/deepagents/backends#statebackend)

## 实验 3：CompositeBackend 路由

```powershell
uv run --no-sync python experiments\ch03_lab.py routing
```

同一个 Agent 的虚拟路径分别走三种实现：

| 虚拟路径 | 具体 Backend | 本实验中实际保存在哪里 | 新 thread 能读吗 | 退出脚本后呢 |
| --- | --- | --- | --- | --- |
| `/scratch/temp.txt` | 默认 `StateBackend` | `thread-A` 的 `State.files` | 不能 | `InMemorySaver` 消失 |
| `/workspace/disk.txt` | `FilesystemBackend` | [lab-output/ch03/disk.txt](../lab-output/ch03/disk.txt)，真实磁盘 | 能 | 文件仍在 |
| `/memories/preference.txt` | `StoreBackend` | `InMemoryStore` 的 `('ch03', 'demo-user')` 命名空间，键是 `/preference.txt` | 能 | 内存 Store 消失 |

`CompositeBackend` 负责按路径前缀选择 Backend，并把 `/memories/` 前缀剥掉后交给 StoreBackend，所以 Store 里看到的是 `/preference.txt`。这里把 `store=InMemoryStore()` 传给 `create_deep_agent`，供 `StoreBackend` 运行时取用；如果在 `StoreBackend(store=...)` 直接传，也是在提供同一种 `BaseStore` 实例。固定的 `demo-user` 只供单用户本机实验，多用户场景应使用可信的用户身份生成 namespace。**跨 thread** 和 **重启后持久** 是两回事；换成持久化的 Store 实现后才能跨进程保留。[官方 Backend 与 Store 示例](https://docs.langchain.com/oss/python/deepagents/backends#storebackend-langgraph-store)

## 实验 4：大工具结果自动卸载

```powershell
uv run --no-sync python experiments\ch03_lab.py offload
```

预设工具返回约 10 万字符。工具消息被替换为 `/large_tool_results/large` 路径和预览；完整内容保存在 StateBackend 的 `files` 中，可以再用 `read_file` 分段读取。当前代码用约 **4 字符 = 1 token** 的粗略字符门槛判断，默认 `tool_token_limit_before_evict=20000`，所以不应把 20,000 当作每种语言都精确的分词边界。0.7.8 实测预览包含**开头和末尾**，课程中的“前 10 行”是示意，记录笔记时以当前版本输出为准。这个实验只证明**工具结果卸载**，不等于触发了对话历史摘要。

## 实验 5：权限与 Shell 能力

```powershell
uv run --no-sync python experiments\ch03_lab.py permissions
uv run --no-sync python experiments\ch03_lab.py shell
```

`FilesystemPermission(operations=['write'], paths=['/policies/**'], mode='deny')` 使 `/policies/rule.md` 写入失败，`/scratch/allowed.md` 正常写入。`operations` 可选 `read`/`write`；`mode='interrupt'` 要配合人工恢复流程，当前实验仅验证 `deny`。

`LocalShellBackend` 继承本地文件 Backend 的能力，并额外提供 `execute`。`root_dir` 是命令执行的工作目录，**`virtual_mode=True` 对文件工具限制路径，但对 Shell 命令不构成隔离**。实验只检查能力，不执行宿主机命令。[官方安全说明](https://docs.langchain.com/oss/python/deepagents/backends#localshellbackend-local-shell)

## 实验 6：让真实模型自己决定调用工具（可选）

```powershell
uv run --no-sync python experiments\live_ch03.py
```

这一步直接复用模板的 `build_agent()` 和 `.env`。观察工具返回和最终 `Agent State.files`；不同模型可能决定不同的调用顺序，所以以实际 Trace 为准。`BUB_MODEL=openai:...` 里的 `openai:` 表示 OpenAI 兼容的 LangChain 适配器，实际服务由 `BUB_API_BASE` 决定。不要把 `.env` 或 API Key 粘贴到笔记。

如果同一轮模型同时发出 `write_file` 和 `ls`，`ls` 可能暂时返回 `No files found`。这表示并行调用的读取发生在写入生效前，后续再 `ls` 可以读到。脚本会打印每一轮模型发出的工具名，便于把这种时序问题和“文件没有保存”区分开。

本机两次实测展示了这种差异：一次先在同一轮发出 `write_file` 与 `ls`，首次 `ls` 为空；另一次先单独 `write_file`，随后同一轮执行 `ls`、`read_file`、`grep`，均成功。第二次的模型总结把实际 4 次工具调用误写成 5 次，因此应以脚本打印的调用分组、工具消息和计数作为证据，不以模型最后的文字统计为准。

## 本章尚未由脚本触发的机制

**自动摘要**与大结果卸载是两套机制。当前 0.7.8 的默认摘要触发条件：若模型 profile 给出 `max_input_tokens`，使用输入窗口的 85%；否则回退到固定 170,000 tokens。摘要会把旧对话存入 Backend，并缩短后续发给模型的消息。要实测摘要，需要给模型大量历史或专门调低摘要阈值，并区分“图状态里保留的消息”和“下一次实际发送给模型的消息”。本实验没有制造长对话，因此不能从 `offload` 输出推断摘要已经发生。

**沙箱 Backend 和自定义 Backend** 分别需要外部隔离执行环境或实现 `BackendProtocol`；本机模板没有配置这些外部资源，当前只验证了内置 Backend 的行为。

## 打卡笔记记录模板

每个实验可记四项：**验证什么 → 运行前预测 → 实际输出证据 → 原因与边界**。尤其记录 `thread_id`、checkpointer 类型、Store 类型、虚拟路径和物理存储位置；只写“持久化”容易把跨轮、跨 thread、跨进程三种能力混为一谈。
