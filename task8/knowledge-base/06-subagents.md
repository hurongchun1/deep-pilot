# Deep Agents Subagent：委派、上下文隔离与继承边界

Subagent 让主 Agent 把一段工作交给另一个独立的 Agent 执行，只收回最终结果。它隔离的是**对话上下文**：子 Agent 的搜索、试错和中间工具结果留在自己的运行里，不进入主 Agent 的消息历史。

本文按 **deepagents 0.7.8、Python 3.12** 核对接口与继承规则。代码只保留委派配置与关键调用；`model` 表示已创建的模型客户端，`backend` 表示已配置的 Backend，省略连接地址、密钥和消息打印循环。

## 示例约定

声明式子 Agent 的 `name`、`description`、`system_prompt` 是最小必要字段。文中子 Agent 的工具和模型若不写，会继承主 Agent，示例为了聚焦继承规则会显式写明。

## 1. 委派解决什么问题

主 Agent 的每一次工具调用和工具结果都留在自己的消息历史里。一次研究任务可能包含多次检索、逐篇读取和反复试错，这些内容进入主对话后，既占上下文，也会干扰后续判断。子 Agent 把这些过程收在自己的运行里，只回一段结论。

| 适合委派 | 不适合委派 |
| --- | --- |
| 需要多次检索、整理、交叉验证的研究任务 | 一步就能完成的查询 |
| 需要独立系统提示词或工具子集的专项任务 | 需要主 Agent 看清每一步过程的场景 |
| 希望换一个模型执行的部分工作 | 已经接近完成、只剩一句话的收尾 |
| 主 Agent 只做协调、子 Agent 分批执行的流程 | 子任务与主任务强耦合、上下文无法用文字交代清楚 |

三点需要先明确：

1. **隔离的是消息，不是文件。** 共享 Backend 时，子 Agent 可以读写主 Agent 看到的那批文件。
2. **不是无条件省钱。** 一次委派至少多一轮模型调用和结果传递，简单任务反而更贵。
3. **委派是模型的选择。** 配置了子 Agent 不等于每次都会用，要看实际 `task` 调用。

## 2. 委派的实际入口：task 工具

子 Agent 不是被代码直接调用的函数，而是通过一个名为 `task` 的工具暴露给主 Agent：

```text
主 Agent 生成 task 调用
    ↓
subagent_type 选择子 Agent，description 交代任务
    ↓
子 Agent 在独立消息上下文中运行
    ↓
只把最后一条消息作为工具结果返回主 Agent
    ↓
主 Agent 继续汇总
```

`task` 的参数只有两项：

| 参数 | 作用 |
| --- | --- |
| `subagent_type` | 要调用哪个子 Agent，取值来自注册时声明的 `name` |
| `description` | 交给子 Agent 的任务说明，会成为它唯一的用户消息 |

`description` 同时承担两个职责：给子 Agent 交代任务，也给主 Agent 提供路由依据（`task` 工具的描述里会列出所有可用子 Agent 的名称与描述）。写「做研究」无法让人判断何时该用，写「需要多次检索并交叉验证后给出带出处的结论时使用」才能被正确选中。

如果传入不存在的 `subagent_type`，工具会返回一段错误文本并列出允许的类型，而不是抛出异常。模型可以据此重试。

## 3. 声明式 SubAgent：字段与继承规则

最常用的是字典声明：

```python
from deepagents import create_deep_agent

researcher = {
    "name": "researcher",
    "description": "需要多次检索并交叉验证后给出带出处结论时使用。",
    "system_prompt": (
        "拆解问题为多个检索方向，交叉验证后给出三条结论，"
        "每条附来源；不复述原始搜索结果。"
    ),
    "tools": [internet_search],
    "skills": ["/skills/research/"],
}

agent = create_deep_agent(
    model=model,
    skills=["/skills/main/"],
    subagents=[researcher],
)
```

字段与「不写时的行为」：

| 字段 | 必填 | 不写时的行为 |
| --- | --- | --- |
| `name` | 是 | — 也是 `subagent_type` 的取值 |
| `description` | 是 | — 参与主 Agent 的路由 |
| `system_prompt` | 是 | — 不继承主 Agent 的提示词 |
| `tools` | 否 | 继承主 Agent 全部工具；**指定即完全替换，不合并** |
| `model` | 否 | 继承主 Agent 模型；可传模型对象或 `"provider:model"` 字符串 |
| `skills` | 否 | **不继承**；写了才装配独立的 SkillsMiddleware |
| `permissions` | 否 | 继承父规则；指定后整体替换 |
| `interrupt_on` | 否 | 继承主 Agent 配置，可按子 Agent 覆盖 |
| `middleware` | 否 | 不继承主 Agent 的自定义中间件 |
| `response_format` | 否 | 不设则回自由文本；设了回符合 schema 的 JSON |

四个容易出错的点：

- **`tools` 是替换不是追加。** 只给一个检索工具，子 Agent 就失去了主 Agent 的其他业务工具。但内置文件工具由 FilesystemMiddleware 装配，不受 `tools` 列表影响，所以它仍然能读写文件。
- **`skills` 不继承。** 主 Agent 配了 `/skills/main/`，子 Agent 拿不到；要自己写路径。反过来，一旦写了，子 Agent 的技能状态与主 Agent 完全分开。
- **`middleware` 不继承。** 主 Agent 挂了 TodoListMiddleware，子 Agent 没有 `write_todos`；需要就在子 Agent 的 `middleware` 里单独加。
- **`system_prompt` 必须独立写。** 主 Agent 的角色设定不会传下去，子 Agent 的职责、输出格式和字数限制都要自己声明。

## 4. 编译式 SubAgent：包装已有的图

当子任务本身是一张已经编译好的 LangGraph 图（有分支、循环、自定义状态），用 `CompiledSubAgent` 直接包装，不必改写成字典：

```python
from deepagents import CompiledSubAgent, create_deep_agent
from langchain.agents import create_agent

analysis_graph = create_agent(
    model=analysis_model,
    tools=[statistical_analysis, generate_chart],
    system_prompt="你是数据分析专家，输出统计结论与图表路径。",
)

analyzer = CompiledSubAgent(
    name="data-analyzer",
    description="需要对数据做统计分析与可视化时使用。",
    runnable=analysis_graph,
)

agent = create_deep_agent(model=model, subagents=[analyzer])
```

它和声明式有三点不同：

1. **没有继承。** 模型、工具、中间件、权限全部由你在图里配好，`create_deep_agent` 不会补齐。
2. **必须返回 `messages`。** 结果状态里没有 `messages` 键会直接报错，因为回传的就是最后一条消息。
3. **不能同时使用动态 `response_format`。** 编译式图的结构在构建时就固定了，运行期再指定输出 schema 会抛 `ValueError`。

## 5. 默认的 general-purpose：继承范围比想象中窄

即使不传任何子 Agent，`create_deep_agent` 也会自动加一个名为 `general-purpose` 的子 Agent。它的能力面接近主 Agent，但不是「完全复制」：

| 继承 | 不继承 |
| --- | --- |
| 主 Agent 的 `model` | 主 Agent 自定义的 `system_prompt`（用框架自带提示词） |
| 显式传入的 `tools` | 主 Agent 独有的自定义中间件（如 TodoListMiddleware） |
| `skills` | 主 Agent 的对话历史 |
| `permissions`、`interrupt_on` | 子 Agent 自己的状态（`todos` 不互通） |

中间件的继承规则更窄：只继承主 Agent 对**默认中间件同名的覆盖**，不会把仅为主 Agent 新增的中间件带过去。

这解释了两种常见现象：主 Agent 配了待办能力，子 Agent 却不会规划；主 Agent 配了写作风格提示词，子 Agent 的输出语气完全不同。想改变子 Agent 的行为，要在它自己的 `system_prompt` 或 `middleware` 里配。

**覆盖默认实现**的方式是提供一个同名声明：

```python
agent = create_deep_agent(
    model=model,
    subagents=[{
        "name": "general-purpose",          # 同名即替换默认实现
        "description": "处理各类需要独立上下文的委派任务。",
        "system_prompt": "为委派任务制定计划，执行后只返回结论与证据位置。",
        "tools": [internet_search],
        "model": stronger_model,            # 也可以换模型
    }],
)
```

一旦提供了同名 spec，框架不再自动添加默认实现，也不会重复构建两套配置。

## 6. 禁用 general-purpose

有些场景不需要默认子 Agent：主 Agent 的工具都很轻、或者希望模型只能显式委派给自己定义的子 Agent。禁用需要两步，缺一不可。

```python
from deepagents import create_deep_agent
from deepagents.profiles import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    register_harness_profile,
)

register_harness_profile(
    key="openai:gpt-4.1-mini",              # 键格式为 provider 或 provider:model
    profile=HarnessProfile(
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
    ),
)

agent = create_deep_agent(model=model, subagents=[])   # 也不再传任何同名子 Agent
```

三个约束：

- **按模型生效。** 键是 `provider` 或 `provider:model`，换一个模型要重新注册；同键重复注册是叠加合并，不是覆盖替换。
- **不禁用就仍然存在。** 只注册 profile 而继续留着同名 spec，等于自己定义了那个子 Agent。
- **`task` 工具会一起消失。** 禁用默认子 Agent 且没有其他同步子 Agent 时，框架不再装配 SubAgentMiddleware，模型也就没有委派入口了。异步子 Agent 不受此影响。

不要试图用 `excluded_middleware` 去掉 SubAgentMiddleware，那会触发配置校验错误；关闭默认子 Agent 只能走 `GeneralPurposeSubagentProfile(enabled=False)`。

## 7. 隔离边界：消息、文件、权限分别到哪一层

「子 Agent 有独立上下文」容易被理解成「什么都是独立的」，实际分层不同：

| 层面 | 是否隔离 | 说明 |
| --- | --- | --- |
| 对话消息 | 隔离 | 交给子 Agent 的只有一条由 `description` 构造的用户消息 |
| 中间工具结果 | 不回传 | 主 Agent 只收到子 Agent 的最后一条消息 |
| `todos` | 隔离 | 不传入也不回传，双方各自维护任务清单 |
| 文件 | 不隔离 | 共享 Backend 时读写同一批文件；后端不同则各自隔离 |
| 文件权限 | 默认继承 | 子 Agent 未写 `permissions` 时沿用父规则，不会自动收紧 |
| 模型与工具 | 可配置 | 不写则继承，写了即替换 |

因此「子 Agent 读到了不该读的文件」应检查 Backend 与 `permissions`，而不是检查子 Agent 的注册信息；「子 Agent 看不到上一轮对话」则是设计使然，必须在 `description` 里交代背景。

## 8. 结果怎样回传，怎样判断委派发生过

默认情况下，主 Agent 收到的工具结果就是子 Agent 最后一条消息的文本。如果配置了 `response_format`，则收到符合 schema 的 JSON，便于后续程序化处理。

要证明委派真的发生，需要同时具备三样证据：

```python
result = agent.invoke({"messages": [{"role": "user", "content": "查三个来源，给出三条带出处的结论。"}]})

for message in result["messages"]:
    print(type(message).__name__, getattr(message, "tool_calls", None), str(message.content)[:120])
```

1. 主 Agent 发出过 `task` 调用，参数里的 `subagent_type` 与 `description` 可读；
2. 对应的工具结果里有子 Agent 的返回内容；
3. 主 Agent 的消息历史里**没有**子 Agent 的中间工具调用。

只有第一项而结果为空，说明子 Agent 没跑完；只有最终回答而没有 `task` 调用，说明模型没委派，回答是它自己编的。

若子 Agent 把原始检索结果整段回传，主上下文照样膨胀，委派收益归零。可以要求它在 `system_prompt` 里只回结论与来源，或先把原始材料写入文件、只回传路径。

## 9. 常见问题与排查方向

| 现象 | 优先检查 |
| --- | --- |
| 从不委派 | `description` 是否写成触发场景；主 Agent 提示词是否要求委派 |
| 委派了但上下文没变小 | 子 Agent 是否回传了原始材料或长篇过程 |
| 选错子 Agent | 多个 `description` 是否过于相似，是否写清了适用与不适用 |
| 子 Agent 少了工具 | `tools` 是否写成了子集（指定即替换） |
| 子 Agent 不会规划 | `middleware` 不继承，需单独添加 |
| 子 Agent 用了错误的技能 | `skills` 不继承，路径是否漏配或指向了别的目录 |
| 禁用了默认子 Agent 后无法委派 | 是否还有同步子 Agent；没有就同时失去了 `task` 工具 |

## 容易混淆的地方

| 易混淆概念 | 应怎样区分 |
| --- | --- |
| 子 Agent 与普通工具 | 工具是一次函数调用；子 Agent 是带独立消息上下文的完整 Agent 运行 |
| 子 Agent 与同一 Agent 的多轮对话 | 子 Agent 每次从一条任务描述开始，不继承主对话历史 |
| 配置子 Agent 与发生委派 | 注册只提供能力；是否调用由模型决定，要看 `task` 调用记录 |
| 隔离上下文与隔离数据 | 消息隔离；文件与权限由 Backend、`permissions` 决定，默认不收紧 |
| `tools` 继承与追加 | 不写是继承全部；写了是完全替换，不合并 |
| `skills` 继承与 `skills` 来源 | 主 Agent 的 `skills` 只给默认子 Agent；自定义子 Agent 必须自配 |
| 默认子 Agent 与完全复制主 Agent | 模型、工具、技能、权限继承；提示词、自定义中间件、对话历史不继承 |
| 禁用默认子 Agent 与保留委派能力 | 禁用后若没有其他同步子 Agent，`task` 工具一并消失 |
| 子 Agent 返回与子 Agent 全部过程 | 主 Agent 只拿到最后一条消息，中间过程留在子 Agent 内 |
| 编译式子 Agent 与声明式子 Agent | 前者是已编译的图，不继承任何配置；后者由框架补齐默认值 |

## 示例验证范围

声明式与默认子 Agent 的配置、`task` 工具注册、结果回传与继承边界，已用预设模型完成离线运行验证：主 Agent 的消息历史中只有一条 `task` 结果；自定义子 Agent 拿不到主 Agent 的 Skill 元数据；默认 `general-purpose` 能拿到；两者都不会把中间消息回传。

`CompiledSubAgent` 的包装写法与 `response_format` 冲突、`register_harness_profile` 的键校验和 `task` 工具消失的条件，按 0.7.8 源码核对，未单独运行。真实模型是否选择委派、`description` 的措辞效果、不同模型的表现差异，均未在本文整理时运行，不写成固定结果。

## 参考资料

- [Deep Agents：Subagents](https://docs.langchain.com/oss/python/deepagents/subagents)
- [Datawhale《Deep Agents 实战》：子 Agent 与上下文隔离](https://datawhalechina.github.io/deepagents-in-action/chapters/ch05-subagents/)
- deepagents 0.7.8 的 `SubAgentMiddleware`、`create_deep_agent` 与 `profiles.harness` 实现。默认行为与字段可能随版本变化，复用前应核对实际安装版本。
