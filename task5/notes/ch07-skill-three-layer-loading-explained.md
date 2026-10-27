# Deep Agent 的 SKILL.md 三层加载是怎么回事

> 本文用到的素材都是本次实际读过的文件：`/skills/skill-guide/SKILL.md`、
> `/skills/skill-guide/references/concepts.md`、`/skills/skill-guide/assets/guide-outline.md`、
> `/experiments/ch07_progressive_disclosure.py`、`/tests/test_skills.py`。
> 章节原文：[《Deep Agents 实战》第 7 章 Skills](https://datawhalechina.github.io/deepagents-in-action/chapters/ch07-skills/)。

## 一、先看一个一次调用做不完的任务

假设用户说：「写一份第 7 章 Skills 学习笔记。」

这件事拆开至少四步：查术语口径 → 按结构成文 → 写入文件 → 读回来核对。任意单次工具调用都覆盖不了。

于是有两种笨办法：

- **全塞进启动提示词**：术语卡、笔记模板、写作要求全部常驻。写推文、改错别字、闲聊时，都在为这份笔记的资料付费，而且 Skill 越加越多，启动提示词越滚越大。
- **什么都不给**：模型只能拿通用写作常识去猜「三层加载」的术语、路径和实验命令，很容易编出一套看似合理的东西。

Skill 是第三条路：**能力常备，内容晚读**。启动时只交付一张「目录卡」，命中任务再展开正文，确实缺细节才展开资料。这就是所谓「渐进式加载」（progressive disclosure），也叫三层加载。

## 二、Skill 是目录，不是文件

```text
skills/
└── skill-guide/
    ├── SKILL.md                  # frontmatter（元数据）+ 指令正文
    ├── references/concepts.md    # 深度资料：术语卡、边界条件
    └── assets/guide-outline.md   # 模板类资产：笔记骨架
```

`SKILL.md` 的 YAML frontmatter 至少要有 `name` 和 `description`，`name` 与目录名保持一致。本项目 `skill-guide` 的 `description` 是：

```yaml
description: 当用户要求编写 Deep Agents 第 7 章 Skills 学习指南、Skills 学习笔记，
  或解释 SKILL.md 与渐进式加载的动手实验时使用。普通博客和社媒文案使用其他 Skill。
```

这一句同时做了两件事：命中「第 7 章 / Skills / 渐进式加载」，并主动排除「普通博客和社媒文案」。这不是文风问题——**在读到正文之前，模型判断要不要用这个 Skill，唯一依据就是这一句描述**。

## 三、三层加载分别发生在什么时候

| 层级 | 进入上下文的东西 | 触发条件 | 谁在动作 |
| --- | --- | --- | --- |
| Level 1 元数据 | `name` + `description` + `SKILL.md` 路径 | Agent 启动、扫描 `skills` 父目录 | 框架自动 |
| Level 2 正文 | `SKILL.md` 里的 Markdown 指令 | 模型判断任务匹配后读取该路径 | 模型主动 `read_file` |
| Level 3 资源 | `references/`、`assets/`、`scripts/` 里的具体文件 | 正文点名了路径，且任务确实需要细节 | 模型再主动读 |

### Level 1：只发索引，不发正文

启动阶段，框架会扫描 `skills=["/skills/"]` 这个父目录下的每个 Skill，解析 frontmatter，但**真正进入模型上下文的只有元数据**：名称、描述、那个 `SKILL.md` 的路径。

要点：磁盘上当然被读过（不解析 frontmatter 就不知道描述），但「启动时没加载正文」说的是**上下文内容**，不是「文件没被碰过」。这两件事经常被混为一谈。

### Level 2：正文是模型自己去拿的

元数据只是一份候选清单。真正的加载动作是模型发出的 `read_file("/skills/skill-guide/SKILL.md")`。这一次调用之后，正文里的写作要求、「按需读取资料」指引才可用。

这也解释了为什么 `description` 写坏了整条链路都会失效：模型压根不会去发那次 `read_file`，后面两层就永远不存在。

### Level 3：路径藏在正文里，是链式的

正文写着：

> 编写第 7 章概念说明时，读取 `references/concepts.md`……
> 用户要求可复用的学习笔记格式时，再读取 `assets/guide-outline.md`。

模型是先看到这句话，才知道磁盘上存在这两个文件，然后才去读。资源不被需要时，就一直躺着，不占上下文。**这是链式依赖：没有 Level 2，就不会有 Level 3。**

一句话概括：**渐进式加载 = 延迟绑定**。启动买索引，选中买正文，缺细节才买资源。

## 四、这套说法有什么证据

### 1. 代码级断言：四轮提示词

`experiments/ch07_progressive_disclosure.py` 用一个 `ScriptedModel` 预设了三步 `read_file`，但跑的仍是真实的 Agent 图、Skills 机制和 `FilesystemBackend(root_dir=PROJECT_ROOT, virtual_mode=True)`。它断言的不是模型最后那句「已完成」，而是每一轮实际拼出来的提示词：

```python
assert "当用户要求编写 Deep Agents 第 7 章 Skills 学习指南" in prompts[0]   # 有描述
assert "区分 Skill 指令、普通工具与持久记忆" not in prompts[0]              # 无正文
assert "区分 Skill 指令、普通工具与持久记忆" in prompts[1]                  # 读 SKILL.md 后有正文
assert "第 7 章术语卡" not in prompts[1]                                    # 但还没有资源
assert "第 7 章术语卡" in prompts[2]                                        # 读 concepts.md 后
assert "# 学习笔记模板" not in prompts[2]
assert "# 学习笔记模板" in prompts[3]                                       # 读 guide-outline.md 后
```

第 0 轮有描述无正文、第 1 轮有正文无术语卡、第 2 轮有术语卡无模板、第 3 轮才有模板——这四条断言就是三层加载的机械证据。

运行方式（在 `task5` 目录）：

```powershell
uv run --frozen python experiments/ch07_progressive_disclosure.py
uv run --frozen pytest tests/test_skills.py -q
```

预期输出是四行中文摘要，以 `PASS` 收尾。要检查的是**四轮提示词里特征的进出**，不是最后那句总结。

**边界**：脚本预设了工具调用，它证明的是「文件内容确实要读到之后才进上下文」，**不证明真实模型会自己做出同样的选择**。另外本文没有执行这两条命令（当前环境只有文件读写工具，没有 shell），上面写的是「应看到什么」，不是「我看到了什么」。

### 2. 本次对话本身就是一次真实的三层加载

这不是脚本，是可查的工具轨迹：

1. **Level 1**：会话开始我只看到 `skill-guide` 的名称、「编写第 7 章学习指南 / 解释渐进式加载」的描述，以及 `/skills/skill-guide/SKILL.md` 这个路径——不知道正文写了什么。
2. **Level 2**：请求命中描述，我 `read_file` 了 `SKILL.md`，才拿到「先讲目录结构，再讲三层加载」「按需读取资料」这些指令。
3. **Level 3**：正文点名了 `references/concepts.md` 和 `assets/guide-outline.md`，我才接着读这两个文件（并行一次读），拿到三层加载证据表和学习笔记模板。

顺序可验证：没有第 2 步，我不知道磁盘上有那两个资源；没有第 3 步，本文的证据表和这个章节结构都写不出来。

### 3. 想验证真实模型，就看轨迹

```powershell
uv run --frozen python experiments/ch07_live_skills.py
```

真实模型实验要先按 `README.md` 配好 `.env`。判读标准是工具调用本身：有没有对 `SKILL.md` 发 `read_file`、随后读了哪些资源、成文里有没有引用真实资料。**模型自称「已读取」不算证据。**

## 五、别把它和工具、记忆混在一起

| 机制 | 存什么 | 例子 |
| --- | --- | --- |
| Skill | 可复用的任务流程 + 配套资料 | `skill-guide` 规定「先讲结构，再讲三层，再给可执行实验」——它决定**何时组合工具、读到什么程度算完成** |
| Tool | 原子操作 | `read_file`、`save_report`，一次只干一件事 |
| Memory | 跨对话的长期偏好 | 「用中文、要简洁」——和任务流程无关，一直成立 |

Skill 不是工具的超集，也不替代记忆。三者边界清楚，才不会把流程写成工具，把偏好写进 Skill。

## 六、三个容易踩的坑

1. **`description` 写得太笼统。** 「帮助用户解决问题」既容易误匹配，也容易在真需要时选不中。它是 Level 1 唯一的判据，要写清触发场景**和不适用场景**。
2. **把单个文件当成父目录。** `skills=["/skills/"]` 要指向**包含 Skill 子目录**的父目录；传 `.../SKILL.md` 是错的。另外，多个来源出现同名 Skill 时，`skills` 列表里**后面的来源覆盖前面的**（`tests/test_skills.py` 覆盖了这条规则）。
3. **把资源当成启动已加载。** `references/`、`assets/` 不会自动进上下文，必须「正文指路 + 模型主动读」才生效。

还有一条成本提醒：**启动元数据随 Skill 数量线性增长**。所以别讲「加多少 Skill 都是零成本」；具体省了多少 token 取决于真实请求轨迹，本文不给没测量过的数字。
