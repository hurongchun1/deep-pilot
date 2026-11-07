# Deep Agents HITL：工具审批、中断与恢复

HITL（Human-in-the-Loop）让 Agent 在执行指定操作前停下来，把「准备调用哪个工具、用什么参数」交给调用方，由人来决定批准、修改、拒绝或直接回答。它解决的不是「模型会不会问」，而是「工具执行前能不能被拦住」。

本文按 **deepagents 0.7.8、langchain 1.4.7、langgraph 1.2.19、Python 3.12** 核对接口，中断结构以实际运行结果为准。`model` 表示已创建的模型客户端，示例省略连接地址和密钥。

## 1. 为什么需要执行层暂停

模型可以在回复里写「是否继续执行？」，但那只是一句话，工具该调还是调。真正的审批发生在工具执行之前，由框架暂停整个图，等外部输入后再继续。

三个区别要先建立：

| 做法 | 谁在拦 | 有没有真的阻止执行 |
| --- | --- | --- |
| 提示词要求模型先征求意见 | 模型自己 | 不保证，模型可能直接调用 |
| `deny` 权限规则 | 框架 | 直接拒绝，没有人工介入 |
| `interrupt` 审批 | 框架 + 人 | 暂停等待决定，批准后才执行 |

所以「权限拒绝」和「审批中断」是两种不同结果：前者是终局，后者是待定。

## 2. 怎样接入：interrupt_on

`create_deep_agent(interrupt_on=...)` 是工具级审批的入口。配置后框架会装配人工介入中间件，在工具执行前生成中断。

```python
from deepagents import create_deep_agent
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

@tool
def write_note(path: str, text: str) -> str:
    """把文本写入指定文件。"""
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)
    return f"已写入 {path}"

agent = create_deep_agent(
    model=model,
    tools=[write_note],
    interrupt_on={
        "write_note": {"allowed_decisions": ["approve", "edit", "reject"]},
    },
    checkpointer=InMemorySaver(),      # 没有它无法暂停与恢复
)
```

三个取值：

| 配置 | 行为 |
| --- | --- |
| `True` | 每次调用都中断，开放全部决策 |
| `False` | 不中断，直接执行 |
| `{"allowed_decisions": [...]}` | 中断，但只接受列出的决策类型 |

`allowed_decisions` 决定这次审批能做什么：只写 `["approve", "reject"]` 时，人不允许改参数，界面也不该提供修改入口。需要按参数条件决定是否中断时，可加 `when` 谓词（`langchain>=1.3.3`），只有返回 `True` 的调用才暂停：

```python
interrupt_on={
    "write_file": {
        "allowed_decisions": ["approve", "edit", "reject"],
        "when": lambda request: not request.tool_call["args"].get("file_path", "").startswith("/workspace/"),
    },
}
```

内置文件工具也能触发审批，走的是另一条路——权限规则：

```python
from deepagents import FilesystemPermission

permissions=[
    FilesystemPermission(operations=["write"], paths=["/protected/**"], mode="interrupt"),
]
```

两种入口最终产出**相同结构**的中断。区别在于：`interrupt_on` 按工具名生效，`FilesystemPermission` 按路径生效；两者会合并，同一次审批里可以既有自定义工具、又有受保护路径。写文件类权限要注意语义范围：受保护的不仅是新建内容，也包括覆盖与删除。

## 3. 为什么必须有 checkpointer 和同一个 thread_id

中断不是把进程挂起等待，而是**保存状态后返回**。要能恢复，至少需要两样：

1. **checkpointer**：把当前图状态、下一步节点、待处理中断写下来；
2. **thread_id**：恢复时找回同一份状态。

```python
config = {"configurable": {"thread_id": "note-approval-1"}}

first = agent.invoke({"messages": [{"role": "user", "content": "写一条笔记"}]}, config)
# 此时返回中断，工具尚未执行

second = agent.invoke(Command(resume={"decisions": [{"type": "approve"}]}), config)
# 同一个 config，从断点继续
```

三点后果：

- 没有 checkpointer，中断没有落脚点，恢复无从谈起；
- 换一个 `thread_id` 恢复，读到的是另一条线程，看起来「什么都没发生」；
- `InMemorySaver` 只在当前进程有效，进程退出后中断无法再恢复；跨进程续办需要持久化 checkpointer。

中断可以跨越很长时间，只要 checkpointer 和 thread_id 还在。这不是「弹窗等人点按钮」的同步阻塞。

## 4. 中断时返回什么

未恢复时，`invoke` 的返回值里带 `__interrupt__`，其中每个元素包含待审批内容和审批选项：

```python
payload = first["__interrupt__"][0].value
```

实际结构（0.7.8 运行结果）：

```text
{
  "action_requests": [
    {
      "name": "write_note",
      "args": {"path": "...note.md", "text": "待审批内容"},
      "description": "Tool execution requires approval\n\nTool: write_note\nArgs: {...}"
    }
  ],
  "review_configs": [
    {"action_name": "write_note", "allowed_decisions": ["approve", "edit", "reject"]}
  ]
}
```

读取时要注意：

- `action_requests` 与 `review_configs` 是**两个列表**，按索引或按 `action_name` 对应，不能假设顺序天然一致；
- 参数键在不同实现里可能叫 `args` 或 `arguments`，稳妥写法是先取 `arguments`、缺失时回退 `args`；
- `allowed_decisions` 以本次实际返回为准：文件权限触发的审批默认包含 `respond`，而自定义的 `interrupt_on` 只包含你声明的那几种；
- 一次模型回复里如果有多个待审批工具调用，会打包进同一个中断，`action_requests` 有多项。

如果返回里没有 `__interrupt__`，说明这次没有触发审批：要么工具没被调用，要么配置未命中。不能凭「模型说要确认」推断已经中断。

## 5. 人怎样提交决定

四种决策，用途不同：

| 决策 | 效果 | 适用 |
| --- | --- | --- |
| `approve` | 按原始参数执行 | 确认无误 |
| `edit` | 换成人工修改后的参数执行 | 参数需要调整 |
| `reject` | 不执行，把拒绝理由作为反馈交给模型 | 不同意这次操作 |
| `respond` | 不执行工具，把人的回答当成工具结果 | 工具本身就是「向人提问」 |

`approve` 与 `edit`：

```python
decision = {"type": "approve"}

decision = {
    "type": "edit",
    "edited_action": {
        "name": "write_note",                 # 必须带工具名
        "args": {"path": "...", "text": "人工修改后的内容"},
    },
}
```

`reject` 要写清原因，否则模型可能换个方式再试：

```python
decision = {
    "type": "reject",
    "message": "用户拒绝写入该文件。不要重试，改为询问是否需要保存到其他位置。",
}
```

`respond` 只适合询问型工具。用它拒绝一个有副作用的操作，会让模型以为工具调用**成功执行**了，这是最容易出错的一处：拒绝就是 `reject`。

批量审批时，`decisions` 的数量与顺序必须与 `action_requests` 一一对应。

## 6. 恢复后怎样继续

用同一个 `thread_id` 发起 `Command(resume=...)`，图从被中断的位置继续，不需要重新提交用户任务，也不需要重建 Agent 对象。

以一份只写临时文件的工具做对照，实测四种路径的结果：

| 决策 | 审批前文件 | 恢复后文件 | 内容 |
| --- | --- | --- | --- |
| approve | 不存在 | 存在 | 原参数 `待审批内容` |
| edit | 不存在 | 存在 | 人工改后的 `人工修改后的内容` |
| reject | 不存在 | 不存在 | — |

这组对照说明两件事：**审批发生在副作用之前**（审批前文件确实不存在）；**决策直接决定副作用**（拒绝路径没有任何写入发生）。

文件权限触发的审批同样如此：批准后目标文件才出现，拒绝则原目录保持原样。

判断流程是否真的完成，要看三处：`__interrupt__` 是否已消失、工具消息是否为成功结果、磁盘或外部状态是否真的改变。模型最后一句「已批准并执行」不构成证据。

## 7. 和其他组件怎样协作

| 组件 | 在审批流程中的职责 |
| --- | --- |
| 工具 | 提供被审批的动作本身 |
| `interrupt_on` / `FilesystemPermission` | 声明哪些动作需要人工介入 |
| 人工介入中间件 | 在工具执行前产生中断，按决定放行或拒绝 |
| checkpointer | 保存中断现场并支持恢复 |
| Backend | 批准后真正落地的文件操作 |
| 调用方界面 | 展示待审批操作、收集人的决定 |

审批不改变各组件原有职责：它只是在「工具即将执行」这一层加了一个闸门。

## 8. 失败与重复执行的边界

- **拒绝不等于回滚。** 拒绝的是这一次待审批调用；此前已经发生的外部副作用不会自动撤销。
- **暂停不等于进程阻塞。** 中断是被保存后返回，进程可以退出，恢复依靠 checkpointer 与 thread_id。
- **恢复不是重跑整个任务。** 它从断点继续，用的是原线程保存的状态；另开线程再发一次任务是另一回事。
- **底层 `interrupt()` 会重放节点。** 在工具级审批里，模型生成的工具调用已在状态中，恢复时直接复用；但如果你在自定义节点里先用 `interrupt()` 再执行写操作，恢复会从节点开头重放，`interrupt()` 之前的副作用可能执行两次。幂等或前置校验要自己保证。
- **不要用裸 `try/except` 包住 `interrupt()`。** 它靠抛异常暂停，宽泛捕获会把中断吞掉。
- **审批不保证成功。** 批准只是允许尝试，工具仍可能因参数、权限或外部服务失败。

## 容易混淆的地方

| 易混淆概念 | 应怎样区分 |
| --- | --- |
| 模型询问与框架中断 | 文字上问「是否继续」不阻止任何执行；只有 `__interrupt__` 才代表真的暂停 |
| 工具可用与操作获批 | 注册工具只是提供能力，每次调用是否放行由审批决定 |
| 暂停与完成 | 返回中断时任务尚未完成，仍在等待人的决定 |
| 保存状态与保存工作目录 | checkpointer 保存执行状态，不备份、也不回滚磁盘文件 |
| 恢复与重跑 | 恢复使用原线程断点；重跑是另起一次任务 |
| 拒绝与撤销 | 拒绝只拦下这一次调用，不撤销此前已发生的副作用 |
| 权限拒绝与审批中断 | `deny` 是终局拒绝；`interrupt` 是待定，等人工决定 |
| approve 与执行成功 | 批准代表允许尝试，工具仍可能失败 |
| reject 与 respond | `reject` 表示不执行并反馈理由；`respond` 会把人的话当成成功结果 |
| 硬编码批准与真实审批 | 代码里写死 `approve` 只演示恢复接口，不代表完成了人工审阅 |

## 示例验证范围

工具级审批的三种决策（approve / edit / reject）与文件权限触发的审批，已用预设模型完成离线运行验证：审批前目标文件均不存在；approve 按原参数写入、edit 按修改后参数写入、reject 完全没有写入；文件权限中断的结构与自定义工具一致，批准后文件才出现。

真实模型是否发起待审批调用、`when` 条件中断、跨进程持久化恢复、子 Agent 的独立审批配置均未在本文整理时运行，不写成已验证结果。中断结构的字段名以 0.7.8 实际返回为准，升级后应重新核对。

## 参考资料

- [Deep Agents：Human-in-the-loop](https://docs.langchain.com/oss/python/deepagents/human-in-the-loop)
- [LangChain：Human-in-the-loop middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in#human-in-the-loop)
- [Datawhale《Deep Agents 实战》：Human-in-the-Loop](https://datawhalechina.github.io/deepagents-in-action/chapters/ch09-human-in-the-loop/)
- deepagents 0.7.8 的 `HumanInTheLoopMiddleware`、`FilesystemPermission` 中断生成逻辑与 `create_deep_agent` 实现。接口与默认决策集可能随版本变化。
