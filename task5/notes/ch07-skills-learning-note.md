# 第 7 章 Skills 学习笔记：三层加载是怎么回事

> 素材来源（均为本次实际读取的文件）：
> `/skills/skill-guide/SKILL.md`、`/skills/skill-guide/references/concepts.md`、
> `/skills/skill-guide/assets/guide-outline.md`、`/COURSE.md`、`/experiments/ch07_progressive_disclosure.py`。
> 章节原文：[《Deep Agents 实战》第 7 章 Skills](https://datawhalechina.github.io/deepagents-in-action/chapters/ch07-skills/)。
> 本笔记是基于上述工程素材整理的课程笔记，不是官方文档译文。

## 一、问题与场景

任务是「写一份第 7 章 Skills 学习笔记」。这件事一次工具调用做不完：要先查术语口径，再组织正文，写入文件后再读回来核对。

两种偷懒做法都不行：

- **全塞进启动提示词**：术语卡、笔记模板、写作要求全部常驻。结果是写推文、写博客、改错别字这些无关请求，都在为这份笔记的资料买单。
- **什么都不给**：Agent 只能靠通用写作常识猜「三层加载」的术语、路径和实验命令，容易编。

Skill 就是这两者之间的第三条路：**能力常备，内容晚读**。启动时只交付一份「目录索引」，选中之后再展开正文，需要细节时再展开资源。

## 二、Skill 的结构

Skill 是**目录**，不是单个 Markdown 文件。最小可用结构只有 `SKILL.md`：

```text
skills/
└── skill-guide/
    ├── SKILL.md                  # frontmatter（元数据）+ 指令正文
    ├── references/concepts.md    # 深度资料：术语卡、边界条件
    └── assets/guide-outline.md   # 模板类资产：笔记骨架
```

`SKILL.md` 的 YAML frontmatter 至少要有 `name` 和 `description`；`name` 与目录名一致。本项目实际生效的 `description` 是：

```yaml
description: 当用户要求编写 Deep Agents 第 7 章 Skills 学习指南、Skills 学习笔记，
  或解释 SKILL.md 与渐进式加载的动手实验时使用。普通博客和社媒文案使用其他 Skill。
```

它同时做了两件事：命中「第 7 章学习笔记」，并明确排除「普通博客和社媒文案」。这不是修辞——**在读到正文之前，模型唯一的判据就是这一句话**。

## 三、三层加载

| 层级 | 进入上下文的内容 | 触发时机 | 本工程的证据 |
| --- | --- | --- | --- |
| Level 1 元数据 | `name` + `description` + 路径 | Agent 启动、扫描 `skills` 父目录时 | 启动提示词里已有 `skill-guide` 的名称、描述和 `/skills/skill-guide/SKILL.md` 路径 |
| Level 2 正文 | `SKILL.md` 的 Markdown 指令 | Agent 判定任务相关后调用 `read_file` | 读过 `SKILL.md` 之后，正文首句「你要用用户的语言，写一份简短但可以动手验证的学习指南」才可用 |
| Level 3 资源 | `references/`、`assets/`、`scripts/` 里的具体文件 | 正文指引 + 任务确实需要细节 | 依据正文「按需读取资料」一节的指引，才读了 `references/concepts.md` 与 `assets/guide-outline.md` |

三条要点：

1. **Level 1 只放索引，不放正文。** 扫描阶段程序当然会解析 frontmatter，但**进入模型上下文的只有元数据**。说「启动时没加载正文」讲的是上下文内容，不是磁盘没被碰过。
2. **Level 2 是 Agent 自己发起的动作。** 元数据只是候选清单，`read_file` 才是真正的加载。没有这次调用，正文永远不会进来。这也解释了为什么 `description` 写坏了整条链路都会失效。
3. **Level 3 是链式的，而且路径藏在正文里。** 正文写明「编写第 7 章概念说明时读 `references/concepts.md`；需要可复用笔记格式时读 `assets/guide-outline.md`」，Agent 才知道这两个文件存在。资源不被需要时，就一直躺在磁盘上，不占上下文。

换一句话概括机制：**渐进式加载 = 延迟绑定**。启动买索引，选中买正文，缺细节才买资源。

### 与相邻机制的分工

| 机制 | 保存什么 | 例子 |
| --- | --- | --- |
| Skill | 可复用的任务流程与配套资料 | `skill-guide` 规定「先讲目录结构，再讲三层加载，再给可执行实验」 |
| Tool | 原子操作 | `read_file`、`save_report` 只负责一次读写 |
| Memory | 跨对话的长期偏好 | 「用中文、要简洁」属于记忆，与任务流程无关 |

Skill 不是工具的超集，它管的是**何时组合工具、读到什么程度算完成**；它也不替代记忆，记忆管「一直成立的事」，Skill 管「这类任务怎么做」。

## 四、动手实验

### 1. 离线脚本：只验证加载机制

在 `task5` 目录运行：

```powershell
uv run --frozen python experiments/ch07_progressive_disclosure.py
uv run --frozen pytest tests/test_skills.py -q
```

脚本用 `ScriptedModel` 预设三次 `read_file`（依次读 `SKILL.md`、`references/concepts.md`、`assets/guide-outline.md`），跑的仍是真实的 Agent 图、Skills 中间件和 `FilesystemBackend(root_dir=PROJECT_ROOT, virtual_mode=True)`，`skills=["/skills/"]` 指向的是**含 Skill 子目录的父目录**。

它断言的是四轮提示词，而不是最后那句「已完成」：

- 第 1 轮有 Skill 描述，没有正文特征句「区分 Skill 指令、普通工具与持久记忆」；
- 第 2 轮有正文，但没有「第 7 章术语卡」；
- 第 3 轮有术语卡，但没有「# 学习笔记模板」；
- 第 4 轮才出现模板。

成功会打印四行中文摘要并以 `PASS` 收尾；`tests/test_skills.py` 另外验证多来源同名 Skill 的覆盖规则（共享目录与项目目录都声明 `skill-guide`，最终只应出现项目目录的描述）。

**边界**：脚本证明了「文件内容确实是读到之后才进上下文」，不证明真实模型会自己做出同样的选择。**本次写作没有执行这两个命令**（本环境只有文件读写工具，没有 shell），所以上面写的是「应看到什么」，不是「我看到了什么」。

### 2. 这次对话本身就是一次真实的三层加载

不是预设脚本，是可查的工具轨迹：

1. **Level 1**：启动时我看到 `skill-guide` 的名称、描述和 `SKILL.md` 路径，但不知道正文内容；
2. **Level 2**：因为请求是「第 7 章 Skills 学习笔记」，命中描述，我 `read_file` 了 `SKILL.md`，才拿到写作要求五条和「按需读取资料」的指引；
3. **Level 3**：正文点名了 `references/concepts.md` 和 `assets/guide-outline.md`，我才再一次读取这两个文件（同一批并行读取），于是拿到三层加载证据表和笔记模板。

顺序可验证：没有第 2 步，我不知道磁盘上有那两个资源文件；没有第 3 步，我写不出上表的证据栏和这份模板结构。

### 3. 想验证真实模型：看轨迹，不看结论

```powershell
uv run --frozen python experiments/ch07_live_skills.py
```

真实模型实验要先按 `README.md` 配好 `.env`。判读标准是工具调用本身：有没有对 `SKILL.md` 发起 `read_file`、随后读了哪些资源、最终保存的文章内容是否引用了真实资料。模型自称「已读取」不算证据。

## 五、结论与易错点

**结论**：三层加载的收益来自「按需付费」的延迟绑定——只用一份很小的元数据换取「Agent 知道自己有哪些能力」。代价是：启动元数据会随 Skill 数量线性增长，所以不要说「加多少 Skill 都零成本」；具体省了多少 token 取决于实际请求轨迹，本笔记不给没测量过的数字。

三个坑：

1. **`description` 太笼统。** 「帮助用户解决问题」既容易误匹配，也容易在真需要时选不中。它是启动阶段唯一的判据，要写清触发场景和不适用场景。
2. **把单个文件当成父目录。** `skills=["/skills/"]` 要指向**包含 Skill 子目录**的父目录，传 `.../SKILL.md` 是错的。
3. **把资源当启动已加载。** `references/`、`assets/` 不会自动进上下文，必须由正文指路 + Agent 主动读取才生效。

另外两条工程细节：多个来源出现同名 Skill 时，`skills` 列表里**后面的来源覆盖前面的**；`allowed-tools` 是规范里的实验性字段，不能替代 Deep Agents 自己的文件权限配置（`FilesystemBackend` / `StateBackend` / `StoreBackend` 与子 Agent 的 Skill 配置属于部署与权限边界，本章另有交代）。
