# Task 7：Grading Rubrics 运行时验收实验

本目录对应 [《Deep Agents 实战》第 13 章](https://datawhalechina.github.io/deepagents-in-action/chapters/ch13-grading-rubrics/)。学习目标是区分“Agent 已生成候选答案”和“候选答案已经通过验收”，观察 `RubricMiddleware` 如何把失败证据反馈给 Agent，并在有限预算内重新评审。

**当前状态：已实现并运行无密钥小实验。** [rubric_smoke.py](experiments/rubric_smoke.py) 覆盖证据工具、两轮修订、一轮预算和不传 Rubric 四个场景；后两项扩展练习仍在下文列出。[第 13 章学习总结](ch13-grading-rubrics-summary.md)解释 `agent.invoke()`、Rubric、中间件和检查工具的关系；中间件参数与流程详见 [RUBRIC_MIDDLEWARE.md](RUBRIC_MIDDLEWARE.md)。

## 运行小实验

在 `task7` 目录执行，首次运行会安装本目录锁定的依赖。无需 AgentSeek、模型密钥、前端或远程服务：

```powershell
uv sync --python 3.12 --frozen
uv run --frozen python -X utf8 experiments/rubric_smoke.py
```

脚本使用 `deepagents==0.7.22`。工作模型与评分模型的**回复由脚本预设**，但 `RubricMiddleware`、Agent 图、`check_report` 工具执行、反馈注入和回调都真实运行。脚本默认关闭 LangSmith 追踪，运行过程中不会调用真实模型 API。它验证的是框架机制，不能证明真实模型会自己想到正确修订。

本机实测（2026-10-31）：

| 场景 | 工作模型调用 | 工具检查 | 评分结论 | 交付 |
| --- | ---: | --- | --- | --- |
| 两轮修订 | 2 次 | 缺 `total` → 补上 `total: 80` 并通过 | `needs_revision → satisfied` | 是 |
| 一轮预算 | 1 次 | 缺 `total`，`ok=false` | `max_iterations_reached` | 否 |
| 没有 Rubric | 1 次 | 未调用 | 无评分 | 否 |

脚本末尾输出 `PASS：三种场景均符合预期。`；其中证据工具的缺项、完整报告、非法 JSON 三种输入也在场景运行前做了断言。

## 实验目标与案例

先用 JSON 销售报告做主实验，避免执行模型生成的 Python 代码。输入为茶 30 元、咖啡 50 元；工作 Agent 应返回一个 JSON 对象：

```json
{
  "items": [
    {"name": "茶", "amount": 30},
    {"name": "咖啡", "amount": 50}
  ],
  "total": 80
}
```

Rubric 拆为三条可检查的标准：① 输出是有效 JSON 对象；② `items` 与输入商品、金额及顺序一致；③ `total` 是数值 80。评分前必须对**最新候选**调用 `check_report`；工具返回 `ok=true` 且逐项标准都通过，才能给出 `satisfied`。

准备两份候选：`BAD_REPORT` 有正确的 `items`，但缺少 `total`；`GOOD_REPORT` 补上 `total: 80`。证据工具解析 JSON，返回 `{"ok": bool, "criteria": [...]}`，每个失败项附 `gap`，例如“缺少或错误的 total；应为 80”。

## 具体实验

每个已实现的场景都新建 Agent 和模型，记录工作模型调用次数、证据工具实际收到的内容、`on_evaluation` 回调和最终是否接收。真实模型的能力留作 live 对照练习。

| 编号 | 操作 | 要观察和断言的事实 | 预期验收结论 |
| --- | --- | --- | --- |
| 1. 先验证证据工具 | 直接将缺 `total`、完整报告、非法 JSON 分别交给 `check_report` | 缺项只让第 3 条失败，`gap` 写明 80；完整报告 `ok=true`；非法 JSON 不通过 | 先确认测试本身可信，不调用模型 |
| 2. 两轮反馈修订 | 挂载 `RubricMiddleware(max_iterations=2)`，预设工作回复依次为 `BAD_REPORT`、`GOOD_REPORT`，每轮评分都调用工具 | 第 0 轮 `needs_revision`；反馈指出 `total` 缺失；工作模型确实被再次调用；第 1 轮工具收到 `GOOD_REPORT` 并返回 `ok=true` | `satisfied`，可以接收 |
| 3. 一轮预算 | 仅将上一个实验的 `max_iterations` 改为 1，保持其他输入不变 | 工具发现缺项；没有第二份候选；最终消息可能仍存在，但回调结论是 `max_iterations_reached` | 不接收 |
| 4. 没有 Rubric | 保留中间件，但在全新运行中不传 `rubric` | 有候选消息；评分工具调用次数和回调记录都为 0 | 没有验收证据，不接收 |
| 5. 证据对应最新候选（待做） | 让第 1 轮返回完整报告，但故意把旧的 `BAD_REPORT` 检查记录当作最后证据 | 验收门比较最新候选与工具输入，发现不一致；不能拿旧证据证明新答案合格 | 不接收；修正为重新取证后才能接收 |
| 6. 真实模型对照（待做） | 配置支持工具调用和结构化输出的工作模型、评分模型，使用同一任务与 Rubric | 记录它是否主动调用证据工具、实际候选和修订次数；检查每轮证据是否对应当前候选 | 由实际评审和工具记录决定，不能预设必然两轮通过 |

实验 5 是额外的故障注入练习。生产代码应直接在验收门核对最后工具输入与最新候选，不依赖评分模型口头声称“我检查过”。

## 实现方式与后续练习

1. `assess_report(report)` 用纯 Python 检查三项标准；`check_report` 将它包装成评分 Agent 可调用的工具，并记录每次输入与结果。
2. 两个 `ScriptedModel` 分别预设工作回复和评分请求。通过 `create_deep_agent(middleware=[...])` 挂载中间件；调用时传入 `messages` 和非空 `rubric`，用 `on_evaluation` 保存每轮结论。
3. `accepted()` 统一执行应用验收门：检查最后结论、最后工具证据与最新候选是否一致。可以改动一处断言或预算，再观察脚本何处失败。
4. 如需扩展，再做实验 5 的旧证据故障注入、实验 6 的真实模型对照。真实模型调用可能产生费用，轮数不固定。

核心验收门：**最后一轮为 `satisfied`，并且有针对最新候选的实际、通过的工具证据，才接收结果**。没有回调、预算耗尽、`failed` 或 `grader_error` 都不接收。

## 可选的正文代码案例

理解 JSON 实验后，可再做第 13 章的 `find_duplicates(values)`：要求重复值各返回一次、按第二次出现位置排序、支持嵌套列表、不修改输入。先用 `set` 版本演示普通整数通过而嵌套列表报 `TypeError`；再用相等性比较修订，重新运行基本、空列表、无重复、不可哈希四组测试。这个案例涉及执行候选源码；教学代码里的 `exec` 不是沙箱，不要在当前进程执行不可信代码。

## 实验记录模板

每次运行记录：

| 字段 | 记录内容 |
| --- | --- |
| 环境 | Python、`deepagents`、LangChain/LangGraph 版本；offline 或 live |
| 输入 | 任务文本、Rubric、迭代上限、运行标识 |
| 工作过程 | 每份候选、工作模型被调用的次数、收到的差距反馈 |
| 证据 | 工具名称、输入对应的候选、`ok`、逐项 `criteria` 和 `gap` |
| 评审 | `grading_run_id`、`iteration`、`result`、`explanation` |
| 放行 | 验收门返回值及理由；是否与预期一致 |

参考：[章节正文](https://datawhalechina.github.io/deepagents-in-action/chapters/ch13-grading-rubrics/)、[配套 Notebook](https://github.com/datawhalechina/deepagents-in-action/blob/main/notebooks/ch13/01-rubric-revision.md)、[LangChain 官方文档](https://docs.langchain.com/oss/python/deepagents/rubric)。API 目前是 Beta；本目录已在 `uv.lock` 中固定依赖版本。升级依赖后应重跑实验，核对状态和事件字段。
