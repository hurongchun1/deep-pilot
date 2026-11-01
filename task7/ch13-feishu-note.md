# Deep Agent 第13章学习与实验总结

## 验证内容

这一章我想弄清楚：Agent 返回一份答案之后，怎样判断它是否真的满足任务要求？工作 Agent 自然停止，只说明它完成了当前生成过程；如果答案漏掉必要字段，仍需要另一个验收环节。我用 `RubricMiddleware` 做了一组销售报告实验，观察评分、反馈修订和最终放行。内容分三轮整理：

1. **先检查证据工具**：确认缺项、完整报告和非法 JSON 会得到不同的检查结果。
2. **再看两轮修订**：观察第一次评分怎样指出差距，工作 Agent 是否收到反馈并生成新候选。
3. **最后改变运行条件**：把评分预算改为一轮，再去掉 Rubric，检查“有最终消息”是否足以交付。

实验脚本是 `task7/experiments/rubric_smoke.py`。工作模型与评分模型的回复由 `ScriptedModel` 预设；Agent 图、`RubricMiddleware`、`check_report` 工具、反馈注入和评分回调实际运行。这样可以稳定观察中间件流程，但不能据此证明真实模型一定会修好答案。

## 第一轮：检查工具能不能提供可靠证据

### 验证什么

任务要求根据茶 30 元、咖啡 50 元生成 JSON 报告，保留商品明细，并给出总额 80。我先检查负责验收的工具：如果它自己不能区分错误和正确报告，评分 Agent 即使调用了工具，也得不到可信的依据。

### 改了什么

我把要求拆成三条：报告是 JSON 对象，`items` 与输入明细一致，`total` 等于金额之和。`assess_report()` 用 Python 解析并逐项判断；`check_report` 把这段检查包装成评分 Agent 可调用的工具。失败项返回 `passed=false` 和具体的 `gap`。预期商品与金额来自本次任务，在脚本中固定为 `SALES`，不让评分模型自行填写“正确答案”。

关键代码：

```python
SALES = [{"name": "茶", "amount": 30}, {"name": "咖啡", "amount": 50}]

def assess_report(report: str) -> dict:
    try:
        data = json.loads(report)
    except json.JSONDecodeError:
        data = None
    is_object = isinstance(data, dict)
    items_ok = is_object and data.get("items") == SALES
    total = data.get("total") if is_object else None
    total_ok = type(total) in (int, float) and total == 80
    # 脚本随后把三项检查整理为 criteria，并为失败项附上 gap。
```

### 预测结果

缺少 `total` 的报告应只在总额这一项失败，并指出应为 80；完整报告应通过；非法 JSON 应被拒绝。

### 实际结果

三种输入都通过了预设断言。缺项报告得到 `ok=false`，差距是“缺少或错误的 total；应为 80”；完整报告得到 `ok=true`；非法 JSON 也没有被当作合格报告。这一步确认后，我才把工具交给评分 Agent 使用。

## 第二轮：评分反馈能不能触发修订

### 验证什么

我想看到第一份候选缺少 `total` 时，评分 Agent 是否检查最新候选，中间件是否把失败项交回工作 Agent，以及第二份候选能否重新取证并通过。

### 改了什么

创建 Agent 时，我挂载 `RubricMiddleware`，给评分 Agent 配置 `check_report`，并把最大评分轮数设为 2。调用 Agent 时再传入本次任务的 `messages` 和非空 `rubric`。工作模型依次返回缺项报告、完整报告；评分模型每轮先请求工具检查，再根据工具结果返回逐项结论。`on_evaluation` 保存每轮记录。

关键代码：

```python
middleware = RubricMiddleware(
    model=grader,
    tools=[make_evidence_tool(records)],
    max_iterations=2,
    on_evaluation=lambda ev: evaluations.append(deepcopy(ev)),
)
agent = create_deep_agent(model=working, middleware=[middleware])
result = agent.invoke({
    "messages": [HumanMessage(content=TASK)],
    "rubric": RUBRIC,
})
```

这里的 `rubric` 是验收标准文本，`check_report` 才是执行检查的工具。`tools=[check_report]` 配给评分 Agent；工作 Agent 若需要自己的工具，还要在创建 Agent 时另外配置。只在普通提示里写“请自检”，不会自动形成这一轮评分与修订流程。

### 预测结果

第一轮工具应发现 `total` 缺失，评分返回 `needs_revision`；中间件把差距反馈给工作 Agent。第二轮工具应收到补上 `total: 80` 的新候选，评分返回 `satisfied`。

### 实际结果

脚本中工作模型调用了 2 次，评分模型调用了 4 次（每轮一次工具请求、一次结构化结论）。第 0 轮工具返回 `ok=false`，中间件反馈包含 `total` 和 `80`；第 1 轮工具检查了完整报告，返回 `ok=true`。回调结论依次是 `needs_revision → satisfied`，应用验收门接收了第二份报告。

这不是“先生成多份答案再挑一份”。只有上一轮要求修订且仍有预算，工作 Agent 才会再次运行。实验用预设回复保证第二份报告正确；真实模型能否根据差距修好，需要另做真实模型对照。

## 第三轮：有最终消息，是否就能交付

### 验证什么

我想检查两种边界：评分预算只够一轮时，错误候选会不会因为运行结束而被接收？保留中间件但不传 Rubric 时，工作 Agent 的回复会不会被误认为已验收？

### 改了什么

第一个场景只把 `max_iterations` 改为 1，其他输入保持一致。第二个场景新建一次运行，不传 `rubric`。两个场景都继续使用同一个应用验收规则：必须有本次评分记录，最后一轮为 `satisfied`，并且最后一次工具检查确实对应最新候选、结果为 `ok=true`。

### 预测结果

一轮预算会留下缺 `total` 的候选，但应以 `max_iterations_reached` 结束，不能交付。不传 Rubric 时，工作 Agent 可以返回候选，评分工具和回调都不应启动，也不能交付。

### 实际结果

两种边界都符合预测：

| 场景 | 工作模型调用 | 评分与证据 | 最终是否交付 |
| --- | ---: | --- | --- |
| 两轮修订 | 2 次 | `needs_revision → satisfied`；第二份候选检查通过 | 是 |
| 一轮预算 | 1 次 | 缺 `total`；`max_iterations_reached` | 否 |
| 没有 Rubric | 1 次 | 无评分记录，工具未调用 | 否 |

脚本最终输出 `PASS：三种场景均符合预期。`。一轮预算和没有 Rubric 的场景都有工作 Agent 的消息，但都没有足够的验收依据。这让我把“生成结束”和“可以交付”分开判断。

## 总结

这一章让我理解了 `RubricMiddleware` 的位置：它在工作 Agent 自然停止后，依据本次传入的 Rubric 启动评分；如果有未通过的标准且还有预算，就把差距反馈给工作 Agent，再评审新的候选。

**首先，几个对象各负责什么？** `agent.invoke()` 启动一次运行，`messages` 描述任务，`rubric` 描述怎样算通过，`RubricMiddleware` 组织评分与修订，`check_report` 提供可核对的事实。Rubric 不是工具；工具返回 `ok`、逐项 `passed` 和失败 `gap`，也不独自决定是否交付。

**然后，评分结果怎样使用？** `on_evaluation` 能记录每轮 `iteration`、`result`、`criteria` 和 `gap`。`satisfied` 表示评分通过；`needs_revision` 表示仍需修改；`max_iterations_reached`、`failed` 和 `grader_error` 都不能当作通过。应用还需要检查证据是否对应最新候选，不能只看 `result["messages"]` 里有没有最后一条消息。

**最后，Rubric 该怎样写？** 我会从任务中提炼可判定、可取证、可修订的条件。格式、明细和金额适合交给确定性的工具；文字质量可以让评分模型判断，但不能用主观判断代替本来能执行的检查。中间步骤的权限与副作用仍要在相应位置控制，最终 Rubric 主要验收交付物。

这样看下来，Rubric 定义完成条件，证据工具核对事实，评分 Agent 给出逐项结论，中间件组织修订，应用验收门决定放行。本实验验证了这条运行链路；真实模型修订能力、旧证据故障注入和更复杂任务，仍需要另外测试。

实验代码：`task7/experiments/rubric_smoke.py`。参考：[《Deep Agents 实战》第13章](https://datawhalechina.github.io/deepagents-in-action/chapters/ch13-grading-rubrics/)与[LangChain 官方文档](https://docs.langchain.com/oss/python/deepagents/rubric)。
