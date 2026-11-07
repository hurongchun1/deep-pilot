# 05｜Skills：把做事方法变成按需加载的知识

## 适用内容

Skill 适合存放可重复使用的任务流程、判断标准、模板和参考材料。Tool 是一个原子动作；Skill 告诉 Agent 在这类任务中何时组合哪些动作、什么时候算完成；Memory 记录跨会话仍适用的偏好或背景。

Task 8 的 `task-planning` Skill 规定：从用户目标提取产物、时间和限制；区分已知事实、建议与待确认；再保存、读回、检查计划。它不把某个学习案例的期限硬编码为所有规划任务的规则。

## 目录与三层加载

一个 Skill 目录至少有 `SKILL.md`，其 YAML frontmatter 包含 `name` 和 `description`；还可有 `references/`、`assets/`、`scripts/`。`skills=["/skills/"]` 指向包含 Skill 子目录的父目录。

| 层级 | 何时进入模型上下文 | 内容 |
| --- | --- | --- |
| 1 元数据 | 发现 Skill 时 | 名称、描述、路径 |
| 2 正文 | Agent 选中并读取 `SKILL.md` 后 | 操作说明 |
| 3 资源 | Agent 按需读取后 | 术语卡、模板、脚本等 |

`description` 是发现阶段的重要匹配依据，应写出触发场景和不适用场景。资源文件不会仅因为位于目录里就自动进入上下文。渐进式加载节省的是不相关任务对正文与资源的上下文消耗；元数据自身仍有成本。

## 怎样验证生效

Task 5 离线脚本比较四轮提示词，验证正文、术语卡和模板是在相应 `read_file` 之后才出现。真实模型实验另看它是否自主读取 Skill 和资源。两类证据不同：脚本验证加载机制，真实轨迹验证某次模型选择。

Skill 的读写权限也要单独考虑。项目实验发现，拒绝读取某个 Skill 文件，不会自动隐藏启动提示词中已经暴露的元数据；“可见性”和“可读写性”是不同边界。Skill 中若有可执行脚本，还要确认执行环境是否真的隔离。

## 自测问题

一个 Skill 文件完整存在，Agent 却从不使用它：先检查父目录路径、frontmatter `description`、真实模型读取轨迹中的哪几项？什么内容应写进 Skill，什么应写进 Tool 或 Memory？

**项目证据**：`task5/notes/ch07-skills-learning-note.md`；`task5/EXPERIMENTS.md`；`task8/skills/task-planning/SKILL.md`。**课程**：[第 7 章 Skills](https://datawhalechina.github.io/deepagents-in-action/chapters/ch07-skills/)。
