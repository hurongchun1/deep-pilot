# 07｜子 Agent：委派任务并隔离中间过程

## 为什么用

多次搜索、查资料和整理会产生大量中间消息。把独立子任务交给子 Agent，主 Agent 主要接收摘要或结构化结果，可以减少主上下文承载的细节。这里隔离的是**对话上下文和工作过程**，不是自动的数据权限隔离；子 Agent 能访问什么仍取决于其 Tool、Backend 和权限配置。

适合研究、专业分析、不同模型分工和复杂任务的局部执行。单步查询使用子 Agent 往往增加调用与协调成本。委派时要写清任务、所需证据、产出格式和何时返回，避免只说“去研究一下”。

## 与其他上下文管理机制的区别

| 机制 | 作用时机 | 重点 |
| --- | --- | --- |
| 大结果卸载 | 工具结果过大时 | 完整结果写入文件，主上下文保留路径与预览 |
| 历史摘要 | 对话变长后 | 用摘要压缩旧消息，有信息损失 |
| 子 Agent 隔离 | 委派开始时 | 中间执行过程留在子 Agent，主 Agent 接收结果 |

子 Agent 若把大量原始材料完整回传，隔离收益会降低。主 Agent 需要引用原始证据时，可要求子 Agent 返回可定位的来源和关键摘录，而不是无来源的结论。

## 配置注意

本项目的 0.7 笔记区分声明式子 Agent 与已有 LangGraph 图包装的子 Agent。声明式配置中的 `description` 影响主 Agent 是否委派；`system_prompt` 要独立定义。Tools、Skills、Middleware 和权限是否继承，不能凭直觉，需要核对当前版本的配置规则与实验轨迹。特别是权限覆盖后，检查子 Agent 的实际能力，避免扩大访问范围。

## 自测问题

研究 Agent 要查十个来源，主 Agent 只需要带证据的三条结论：委派输入和返回格式应怎么写？如果子 Agent 看到了不该看的文件，问题应从哪些配置层排查？

**项目证据**：`task4/notes/ch05-subagents.md`；`task4/experiment/multi_subagent.py`；`task5/EXPERIMENTS.md`。**课程**：[第 5 章子 Agent](https://datawhalechina.github.io/deepagents-in-action/chapters/ch05-subagents/)。
