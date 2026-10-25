# 第 7 章术语卡

这份参考资料供 `skill-guide` 被选中后使用；它不是启动时自动注入的提示词。

## Skill 的最小结构

一个 Skill 是目录，不是单独的 Markdown 文件。例如：

```text
skills/
└── skill-guide/
    ├── SKILL.md
    ├── references/concepts.md
    └── assets/guide-outline.md
```

`SKILL.md` 的 YAML frontmatter 至少包含 `name` 和 `description`。`name` 应与目录名一致；`description` 要写清任务触发场景，因为 Agent 在读取正文前主要依靠描述判断是否使用该 Skill。

## 三层加载

| 层级 | 何时进入上下文 | 本实验中的证据 |
| --- | --- | --- |
| Level 1：元数据 | Agent 启动并扫描 Skill 目录时 | 首轮提示词包含 `skill-guide` 的描述和路径，但不含正文特征句 |
| Level 2：正文 | Agent 调用 `read_file` 读取 `SKILL.md` 后 | 第二轮提示词出现“区分 Skill 指令、普通工具与持久记忆” |
| Level 3：资源 | Agent 再读取 `references/` 或 `assets/` 后 | 第三轮出现本术语卡，第四轮出现学习笔记模板 |

## 与相邻机制的区别

- **Tool** 提供原子操作，如 `read_file` 或 `save_report`。Skill 告诉 Agent 何时组合这些操作，以及怎样判断完成。
- **Memory** 保存跨对话的偏好或长期上下文。Skill 保存可复用的任务流程和资料，两者用途不同。
- `skills=["/skills/"]` 指向包含多个 Skill 子目录的父目录。它对应本地 `task5/skills/`，不是某个 `SKILL.md` 文件。
- 多个来源出现同名 Skill 时，`skills` 列表后面的来源覆盖前面的来源。

参考：[《Deep Agents 实战》第 7 章](https://datawhalechina.github.io/deepagents-in-action/chapters/ch07-skills/)。
