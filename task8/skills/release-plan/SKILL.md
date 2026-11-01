---
name: release-plan
description: 当用户要求为青柠清单 v1.2 制定上线计划、灰度发布方案或回滚预案时使用。
---

# 产品上线计划方法

先读取 `sources/product-brief.md` 与 `sources/release-constraints.md`，再读取本 Skill 的 `references/plan-outline.md`。把资料中明确给出的事实、计划中的待执行动作和需要确认的事项分开写。

用 `write_todos` 规划读取资料、起草计划、保存、读回和检查。计划必须覆盖 10% → 50% → 100% 放量、每阶段观察条件、负责人角色、暂停与回滚触发条件。不要把尚未发生的发布写成“已完成”。

用 `save_plan` 保存 Markdown，再用 `read_plan` 读回，最后用 `check_plan` 检查已保存文件。只有工具返回 `ok=true`，才说结构检查通过；这不代表业务指标已经达标。
