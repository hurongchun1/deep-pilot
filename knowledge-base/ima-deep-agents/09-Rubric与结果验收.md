# 09｜Rubric：把“生成完了”变成“有证据地通过”

## 四个角色

| 角色 | 职责 |
| --- | --- |
| 工作 Agent | 生成和修订候选产物 |
| Rubric | 写明本次任务可判定的验收标准 |
| 评分 Agent / `RubricMiddleware` | 按标准评审、反馈差距并组织有限轮修订 |
| Evidence Tool | 读取最新产物，返回可核对的事实 |

Rubric 是标准文本，不是执行检查的工具。`agent.invoke()` 发起运行；挂载的中间件读取本次传入的非空 `rubric`，在工作 Agent 停止后组织评分。只在提示词里写“请自检”，不会自动产生这一评分循环。

## 一次修订如何发生

Task 7 的销售报告实验让工作 Agent 先产出缺少 `total` 的 JSON。评分 Agent 调用 `check_report` 检查最新候选，得到缺失项和正确总额；中间件把 `gap` 反馈给工作 Agent，预算允许时才进行下一轮修订。`max_iterations` 是评分次数上限，不保证一定修好。

可以把明确可检查的条件交给代码：JSON 能否解析、字段是否齐全、总额是否等于输入金额之和。主观质量可由评分模型辅助判断，但不能替代确定性证据。预期答案应来自本次可信输入，而非让评分模型自己编一个“正确值”。

## 交付门槛

本次应有评审记录；最终结论为 `satisfied`；所需检查工具确实针对**最新候选**运行且通过。`needs_revision`、`max_iterations_reached`、`failed`、`grader_error` 或缺少证据都不应当作通过。`result["messages"]` 即使存在最终消息，也可能只是未通过的候选。

`on_evaluation` 适合记录每轮评分、失败项和 `gap`；它不替应用决定是否交付。Rubric 验收也不能替代权限、沙箱、人工审批和长期离线评测。

## 自测问题

一个 Agent 输出了完整 JSON，评分预算却耗尽：你能否交付？如果检查工具看的是第一版而不是最新版本，评分为 `satisfied` 是否足够？

**项目证据**：`task7/ch13-grading-rubrics-summary.md`；`task7/RUBRIC_MIDDLEWARE.md`；`task7/experiments/rubric_smoke.py`。**文档**：[Deep Agents Rubric](https://docs.langchain.com/oss/python/deepagents/rubric)。
