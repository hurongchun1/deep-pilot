# `RubricMiddleware` 是怎样验收 Agent 结果的

## 一句话理解

`RubricMiddleware` 是挂在 Deep Agent 上的评分中间件。工作 Agent 先给出**候选结果**；中间件再启动评分 Agent，按 Rubric（验收标准）检查候选。评分 Agent 可调用证据工具取得可核查的事实。若结论是 `needs_revision`，中间件把失败项和差距反馈给工作 Agent，让它再生成一轮；只有明确的 `satisfied` 才表示验收通过。

“Agent 不再调用工具”“`invoke()` 返回消息”只说明生成循环结束，不等于通过验收。

## 四个角色及其边界

| 角色 | 在 Task 7 中做什么 | 注意 |
| --- | --- | --- |
| 工作 Agent / Working Model | 根据销售数据生成并修订 JSON 报告 | 不负责宣布自己的结果已通过 |
| Rubric | 规定 JSON 格式、`items`、`total` 和必须取证等条件 | 是标准文本，本身不运行测试 |
| 评分 Agent / Grader Model | 阅读候选与标准，调用工具，逐项给出结论和差距 | 即使与工作模型选用同一个模型实例，也应视为独立的评审角色；自然语言判断不能代替确定性测试 |
| Evidence Tool | 解析最新报告并返回 `ok`、逐项通过状态和失败原因 | 提供事实，不决定应用是否交付 |

`RubricMiddleware(tools=[check_report])` 中的工具只给评分 Agent 用；如工作 Agent 也需调用工具，要另行在 `create_deep_agent(tools=[...])` 中提供。

## 一次运行的顺序

```text
调用方传入任务 + 非空 Rubric
          ↓
工作 Agent 生成候选报告
          ↓
工作 Agent 自然停止，中间件启动评分 Agent
          ↓
评分 Agent 对最新候选调用 check_report
          ↓
  needs_revision：失败项和 gap 写回对话 → 工作 Agent 修订 → 重新取证
  satisfied：结束评分 → 应用验收门检查证据 → 接收
  其他终止状态：结束评分 → 应用验收门拒绝
```

中间件提供的是**运行时修订循环**：它在当前请求里把具体失败信息送回工作 Agent。它不是“再写一次提示词”，也不能凭模型自检保证正确。代码测试、JSON 解析、Schema 校验等能确定的事实，仍要由工具执行。

## 怎样写 Rubric

Rubric 应拆成可判定、可取证、可修订的标准。Task 7 可以使用以下内容：

```text
- 报告是有效 JSON 对象。
- items 与输入商品、金额及顺序一致。
- total 是数值，且等于金额之和 80。
- 返回 satisfied 之前，必须用 check_report 检查最新候选。
- 只有工具返回 ok=true，且上述三项逐项通过，才能返回 satisfied。
```

前三条是业务要求；后两条约束评分过程，防止评分模型只读文本就声称通过。失败反馈要说明具体差距，例如“缺少 `total`，正确值应为 80”，这样下一轮才知道改什么。测试工具必须验证的是**当前候选**；旧候选的通过记录不能给新候选背书。

## 如何装配

以下是装配示意，`working_model`、`grader_model`、`check_report`、`task` 和 `rubric` 需先按实际环境定义：

```python
from deepagents import RubricMiddleware, create_deep_agent
from langchain.messages import HumanMessage

evaluations = []

def record_evaluation(ev):
    evaluations.append(ev)
    print(ev["iteration"], ev["result"], ev["criteria"])

rubric_middleware = RubricMiddleware(
    model=grader_model,
    tools=[check_report],
    max_iterations=2,
    on_evaluation=record_evaluation,
)

agent = create_deep_agent(
    model=working_model,
    middleware=[rubric_middleware],
)

start = len(evaluations)
result = agent.invoke({
    "messages": [HumanMessage(content=task)],
    "rubric": rubric,
})
this_run = evaluations[start:]
```

关键点：`RubricMiddleware` 构造好以后，还要放进 `middleware=[...]`；Rubric 是**每次调用的状态输入**，调用时必须传入非空字符串。仅挂载中间件但不传 Rubric，在新的运行状态下不会开始评分。若用了 Checkpointer 并复用旧 `thread_id`，旧 Rubric 可能仍在状态里，不能靠省略字段来“清空”标准。

## 关键参数

| 参数 | 用途 | 在实验中的观察点 |
| --- | --- | --- |
| `model` | 指定评分模型，必填 | 工作模型和评分模型可以不同；评分模型需能调用工具并输出结构化结论 |
| `tools` | 评分 Agent 的取证工具 | 确认它收到的是最新候选；工具执行成功与业务检查 `ok=true` 是两件事 |
| `system_prompt` | 补充评分 Agent 的行为指令 | 可要求先取证再给结论；不能替代 Rubric 或测试 |
| `max_iterations` | 限制一次 Rubric 尝试的评分轮数 | `2` 最多评分两轮，并非保证修订两次；用完仍不通过就终止 |
| `on_evaluation` | 每轮评审后收到 `RubricEvaluation` | 用来记录日志和指标；回调不是业务放行开关 |

## 五种结论怎么处理

| 结论 | 含义 | 下一步 | 可交付？ |
| --- | --- | --- | --- |
| `satisfied` | 逐项标准通过 | 结束评分，应用再核对最新证据 | 证据也通过时才可以 |
| `needs_revision` | 至少一项需要修改 | 预算允许时，反馈差距并再调用工作 Agent | 否 |
| `max_iterations_reached` | 仍需修改，但评分次数已经用完 | 停止循环 | 否 |
| `failed` | 评分 Agent 认为标准无法评估 | 停止循环，检查 Rubric 或任务 | 否 |
| `grader_error` | 评分调用链出错，例如模型服务或结构化输出失败 | 停止循环，排查异常 | 否 |

`max_iterations` 统计评分轮次，从 `iteration=0` 开始。第一次就通过，后续轮次不会发生。`needs_revision` 是触发下一轮修订的中间结果；达到预算上限后看到的是终止状态。增加预算只会允许更多尝试，不能修复错误的测试或含糊的标准。

## 观察与最终放行

`on_evaluation` 每轮提供 `grading_run_id`、`iteration`、`result`、`explanation`、`criteria` 等信息。`criteria` 可看各条标准的 `passed`，失败项可看 `gap`。同一次评分尝试的多个轮次共享 `grading_run_id`；它与 Checkpointer 的 `thread_id` 不同。

回调适合留日志，事件流可显示 `rubric_evaluation_start` / `rubric_evaluation_end` 以做实时进度提示。它们帮助观察流程；**放行决定应由调用方在整次运行后作出**。最小规则是：本次有评审记录，且最后一轮为 `satisfied`。Task 7 还应核对工具确实执行、最后一份工具输入对应最新候选、工具 `ok=true`。任何缺失、异常或未知结果默认不接收。

## 不能从实验推出什么

- 预设模型的离线实验能证明框架确实调用了评分工具、注入反馈并再次运行工作 Agent；因为第二份候选是预设的，不能证明真实模型理解反馈或一定能修好。
- `RubricMiddleware` 改善当前任务的验收过程，不是正确性的绝对证明。测试覆盖不足时，`satisfied` 也可能漏掉问题。
- 章节的 Python 代码示例用 `exec` 执行候选实现，只适合作教学演示。不可信代码应在隔离环境执行，限制文件、网络、时间和资源。
- 每多一轮修订，就可能增加工作模型、评分模型和工具调用，需记录延迟与费用；长期效果还要靠多样本离线评测。

参考：[LangChain 官方说明](https://docs.langchain.com/oss/python/deepagents/rubric)、[课程第 13 章](https://datawhalechina.github.io/deepagents-in-action/chapters/ch13-grading-rubrics/)、[课程配套实验](https://github.com/datawhalechina/deepagents-in-action/blob/main/notebooks/ch13/01-rubric-revision.md)。`RubricMiddleware` 仍是 Beta API，示意代码正式执行前应按锁定版本验证。
