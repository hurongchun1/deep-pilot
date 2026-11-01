# 第十三章学习总结：Grading Rubrics 运行时验收

这一章让我理解了“Agent 已经生成答案”和“答案已经通过验收”是两件事。工作 Agent 不再调用工具、返回最终消息，只说明当前生成循环结束；它仍可能漏掉边界要求。`RubricMiddleware` 在工作 Agent 自然停止后启动评分，把未通过的标准和具体差距交回工作 Agent 修订，并限制最多评分多少轮。

**首先，`agent.invoke()`、`rubric`、`RubricMiddleware` 和检查工具是什么关系？**

这四个名称处于不同层次。开发者先创建并挂载中间件，再调用这个 Agent。`agent.invoke()` 是启动运行的方法；它接收用户任务和本次验收标准。中间件从运行状态读取非空 `rubric`，在工作 Agent 生成候选结果后启动评分 Agent。`rubric` 是标准文本，不是工具；`check_report` 这类函数才是可执行的检查工具。

| 名称 | 开发者在哪里设置 | 负责什么 | 不代表什么 |
| --- | --- | --- | --- |
| `RubricMiddleware` | 创建 Agent 时放入 `middleware=[...]` | 配置评分模型、可用证据工具、评分预算和回调，并执行评分与修订流程 | 它本身不是检查报告的工具 |
| `agent.invoke()` | 每次发起任务时调用 | 启动已挂载中间件的 Agent，并传入本次运行状态 | 它本身不是验收标准 |
| `messages` | `invoke()` 的输入 | 告诉工作 Agent 本次要做什么 | 不能证明工作结果已经合格 |
| `rubric` | `invoke()` 的输入 | 告诉评分 Agent 本次怎样算通过；非空时启动新的评分循环 | 它是标准文本，不是“Rubric 工具” |
| Evidence Tool | 创建中间件时传入 `tools=[...]` | 实际检查代码、JSON、文件等，并返回结构化事实 | 不直接决定最终是否交付 |

在本章学习场景里，上述配置完全可以由开发者预设：例如把 Rubric 写成常量，每次调用时传入。Rubric 也可以按任务变化，但应与本次用户要求和可用证据一致。只在普通 Prompt 里写“请自检”，不会自动得到中间件的评分循环；只传 `rubric` 而没有挂载读取它的中间件，也不会得到本章的验收机制。

```python
from deepagents import RubricMiddleware, create_deep_agent
from langchain.messages import HumanMessage

RUBRIC = """
- 报告是有效 JSON 对象。
- items 与输入明细一致。
- total 等于输入金额之和。
- 评分前调用 check_report 检查最新候选。
"""

evaluations = []
middleware = RubricMiddleware(
    model=grader_model,           # 评分模型，需预先定义
    tools=[check_report],         # 评分模型可调用的工具，需预先定义
    max_iterations=2,
    on_evaluation=evaluations.append,
)
agent = create_deep_agent(model=working_model, middleware=[middleware])

result = agent.invoke({
    "messages": [HumanMessage(content="根据销售数据生成 JSON 报告")],
    "rubric": RUBRIC,
})
```

这段代码展示装配关系；`working_model`、`grader_model` 和 `check_report` 需要另外定义。`RubricMiddleware(tools=[...])` 中的工具只给评分 Agent 用，工作 Agent 若需用工具，要另行配置在 `create_deep_agent(tools=[...])`。新运行中不传非空 Rubric，中间件不会开始评分；使用 Checkpointer 延续旧线程时，不应依赖省略字段来清除之前的 Rubric。

**然后，评分和修订是怎样发生的？**

| 顺序 | 执行者 | 本章销售报告实验中的动作 |
| --- | --- | --- |
| 1 | 工作 Agent | 根据任务生成一份候选报告，第一份故意缺少 `total` |
| 2 | `RubricMiddleware` | 在工作 Agent 自然停止后启动评分 Agent，并提供 Rubric 与运行记录 |
| 3 | 评分 Agent | 按标准调用 `check_report`，检查最新候选 |
| 4 | Evidence Tool | 返回 `ok=false`，指出 `total` 缺失，应为 80 |
| 5 | 评分 Agent 与中间件 | 形成 `needs_revision`；中间件把失败项和 `gap` 注入对话 |
| 6 | 工作 Agent | 收到反馈后才生成第二份报告，补上 `total: 80` |
| 7 | 评分 Agent 与应用 | 对第二份候选重新取证；若最终为 `satisfied` 且证据对应最新候选，应用才接收 |

真实运行不是一次生成多份答案再挑选。只有前一轮返回 `needs_revision` 且还有预算，工作 Agent 才会再次运行。Task 7 的离线实验预设了两次模型回复，是为了稳定验证中间件确实触发第二次调用；它不证明真实模型一定会理解反馈或修好答案。

**Rubric 和检查工具的标准该怎样写？**

从用户任务提炼可判定、可取证、可修订的条件。以销售报告为例：“JSON 可解析”“明细与本次输入一致”“总额等于本次输入金额之和”都能用 Python 检查。工具应返回 `ok`、逐项 `passed` 和失败时的 `gap`；评分前要先独立验证工具。预期输入应由应用根据本次任务确定，不让评分模型随意填写一个“正确答案”。

工作 Agent 可能选择不同工具和路径，但最终验收通常检查**结果是否满足任务要求**，不要求事先猜测每一步工具调用。图式工作流中，中间节点的数据格式、权限和副作用更适合在对应节点直接检查；`RubricMiddleware` 可以只验收最终交付物。开放任务若没有清楚的完成条件，也不必强行使用它。文字质量等主观标准可交给评分模型判断，但这种判断不能代替确定性的测试证据。

**最后，怎样观察评分并决定是否交付？**

`on_evaluation` 在每轮评分后收到一个 `RubricEvaluation`。它可记录 `grading_run_id`、从 0 开始的 `iteration`、`result`、`explanation`、逐项 `criteria` 及 `unverified`。`criteria` 中的失败项带 `gap`，说明下一轮要改哪里。`unverified=True` 表示评分模型声称通过，但逐项评审覆盖不足，中间件把结论改成了更保守的状态；它不等于已证明候选答案本身有错。

| 结论 | 表示什么 | 后续行为 | 应用是否接收 |
| --- | --- | --- | --- |
| `satisfied` | 评分通过且未被中间件降级 | 结束评分 | 在所需证据也通过时接收 |
| `needs_revision` | 仍有标准需要修改 | 有预算时反馈并继续 | 否 |
| `max_iterations_reached` | 仍需修改，但评分预算已用完 | 结束运行 | 否 |
| `failed` | 评分模型认为 Rubric 无法评估 | 结束运行 | 否 |
| `grader_error` | 评分调用链发生异常 | 结束运行 | 否 |

`result["messages"]` 中可能保留工作 Agent 的最后一份候选答案；即使预算耗尽或评分异常，也可能有这份“最终消息”。评分结论应读取本次评审记录，不能只判断消息是否存在。`on_evaluation` 用于日志、指标和审计；事件流用于显示评分开始与结束的实时进度；Checkpointer 按 `thread_id` 延续状态。`grading_run_id` 标识一次评分尝试，与 `thread_id` 不是一回事。

应用验收门应采用失败关闭规则：本次必须有评审、最后一轮必须是 `satisfied`，并按任务核对工具确实检查了**最新候选**且检查通过。没有记录、证据过期、预算耗尽或评分出错时都不交付。回调记录发生了什么，不负责替应用做业务放行。

这样看下来，Rubric 定义完成条件，检查工具提供事实，评分模型逐项评审，中间件组织反馈和修订，应用验收门决定交付。它改善当前任务的验收过程，但不能替代不可信代码的沙箱、工具权限、必要的人工审批和长期效果的离线评测。

本目录可运行的对照见 [README.md](README.md) 与 [rubric_smoke.py](experiments/rubric_smoke.py)。参考：[课程第 13 章](https://datawhalechina.github.io/deepagents-in-action/chapters/ch13-grading-rubrics/)和[LangChain 官方说明](https://docs.langchain.com/oss/python/deepagents/rubric)。
