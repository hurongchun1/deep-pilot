# 第 7 章实验：Skills 何时进入上下文

对应章节：[Skills — 可复用的 Agent 能力包](https://datawhalechina.github.io/deepagents-in-action/chapters/ch07-skills/)；项目起点：[AgentSeek content-builder 模板](https://github.com/agentseek-ai/agentseek-templates/tree/main/templates/deepagents/content-builder)。模板本来就有 `blog-post` 与 `social-media` 两个 Skill，本目录增加 `skill-guide`，用内容创作任务展示第 7 章机制。

## 实验目标

1. 启动时，模型只看到 Skill 的 `name`、`description` 与路径，不预先接收完整正文。
2. 模型选择 Skill 后，通过 `read_file` 读取 `SKILL.md`。
3. 正文指向的 `references/`、`assets/` 内容在需要时继续读取。
4. 配置多个父目录时，同名 Skill 以后列目录中的版本为准。

`experiments/ch07_progressive_disclosure.py` 直接从 `deepagents` 导入 `create_deep_agent` 和 `FilesystemBackend`，不使用模板后端的 `task5.agent`。脚本化模型预设三次 `read_file` 调用，运行的仍是真实的 Agent 图、Skills 中间件和文件系统后端。测试检查四轮模型上下文，而不依据最后一句“已完成”来判断加载是否发生。该脚本证明加载机制，不证明真实模型总会正确选择 Skill；真实模型选择要看其工具调用轨迹。

## 与第 7 章的对应

| 章节概念 | 本目录位置或验证方式 |
| --- | --- |
| YAML frontmatter 与描述匹配 | `skills/skill-guide/SKILL.md` 的 `name`、`description` |
| Level 1 元数据 | 离线实验首轮模型消息 |
| Level 2 正文 | 读取 `/skills/skill-guide/SKILL.md` 后的模型消息 |
| Level 3 资源 | 读取 `references/concepts.md`、`assets/guide-outline.md` 后的模型消息 |
| FilesystemBackend | 离线脚本直接配置项目根目录与 `skills=["/skills/"]`；模板后端也使用同一目录 |
| 多源覆盖、运行时路径 | `build_graph(..., skill_sources=[...])` 与 `tests/test_skills.py` |

第 7 章还介绍 `StateBackend`、`StoreBackend`、子 Agent 的 Skill 配置和文件权限。这些是部署方式或权限边界，当前内容创作工程使用本地 `FilesystemBackend`；需要无磁盘注入、跨线程共享或写入审批时，再按章节示例选择对应后端与权限配置。

## 运行与判读

```powershell
cd task5
uv run --frozen python experiments/ch07_progressive_disclosure.py
uv run --frozen pytest tests/test_skills.py -q
```

离线脚本成功会输出 `PASS`。它依次检查：首轮没有 Skill 正文、第二轮已有正文但没有术语卡、第三轮有术语卡但没有模板、第四轮才有模板。测试中的共享目录和项目目录都声明 `skill-guide`；最终提示词应只包含项目目录的描述。

一次成功运行应看到以下中文摘要（脚本同时用断言核对真实提示词，不只打印文字）：

```text
第 1 轮：Skill 部分只有 skill-guide 的名称、描述和路径。
第 2 轮：读取 SKILL.md 后，提示词出现 Skill 正文。
第 3 轮：读取 concepts.md 后，提示词出现中文术语卡。
第 4 轮：读取 guide-outline.md 后，提示词出现中文学习笔记模板。
PASS：Skill 元数据、正文和资源按需进入模型上下文。
```

这里的第一轮说明 Skill **可被发现**，第二至四轮说明文件内容是由实际 `read_file` 返回后才进入后续消息。脚本化模型按预设顺序发起读取，所以此结果不表示真实模型能独立做出相同选择。多源覆盖由 `tests/test_skills.py` 另行验证：同名 Skill 的项目级描述出现，共享级描述未出现。

真实模型实验需先按 `README.md` 配置 `.env`。检查 `read_file` 的实际调用、返回内容和保存的文章。不要把 Skill 的 `description` 写成泛泛的“帮助写作”：它是启动阶段的匹配依据。也不要把单个 `SKILL.md` 文件路径传给 `skills` 参数；该参数要指向包含 Skill 子目录的父目录。
