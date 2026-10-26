# Deep Agent 第 7 章学习与实验总结：Skills

## 验证内容

这一章我用 `task5` 的内容创作 Agent 实验 Skill 的发现、加载和权限控制。项目中新增的 `skill-guide` 包含 `SKILL.md`、术语卡和笔记模板，正好可以观察 Agent 什么时候看到 Skill 的介绍，什么时候才读取完整指令和配套资料。前四轮先验证基本加载与写保护：

1. **渐进式加载**：用预设工具调用依次读取 `SKILL.md`、术语卡和模板，对比每一轮发送给模型的内容，确认这些文件是否按需进入上下文。
2. **真实模型选择**：不预设工具调用，直接让模型编写第 7 章学习笔记，检查它是否主动选中 `skill-guide`，以及实际读取了哪些文件。
3. **同名 Skill 覆盖**：在共享目录和项目目录各放一份同名 Skill，检查两个来源同时配置时，Agent 最终采用哪一份。
4. **写入权限**：禁止改写 Skill 目录，同时允许写普通笔记；分别核对工具返回和文件内容，确认权限规则有没有生效、是否影响正常写入。

之后继续验证三种存储后端、动态选择 Skill 来源、子 Agent 继承、写入审批，以及从 Skill 调用脚本。各项实验的代码和运行命令汇总在 `EXPERIMENTS.md`。

## 第一轮：按需加载是否真的发生（`ch07_progressive_disclosure.py`）

### 验证什么

我想看到 `skill-guide` 的三层内容分别在什么时候进入模型上下文：

1. 启动时只有名称、描述和路径；
2. 调用 `read_file` 后才有 `SKILL.md` 正文；
3. 再读取 `references/` 和 `assets/` 时，资源内容才出现。

### 改了什么

在 `task5/skills/skill-guide/` 中，`SKILL.md` 写了第 7 章笔记的流程，并按需指向 `references/concepts.md` 和 `assets/guide-outline.md`。实验脚本用 `ScriptedModel` 预设三次 `read_file`，但实际运行的仍是 `create_deep_agent()`、Skills 中间件和 `FilesystemBackend(root_dir=PROJECT_ROOT, virtual_mode=True)`。它逐轮检查发送给模型的提示词。

从 `task5` 目录运行：

```powershell
uv run --frozen python experiments/ch07_progressive_disclosure.py
```

### 预测结果

- 第 1 轮能看到 `skill-guide` 的描述，看不到正文特征句；
- 第 2 轮读完 `SKILL.md` 才看到正文，看不到术语卡；
- 第 3 轮读完 `concepts.md` 才看到术语卡，看不到笔记模板；
- 第 4 轮读完 `guide-outline.md` 才看到模板。

### 实际结果

2026 年 10 月 26 日运行通过。脚本依次打印“四轮”中文摘要，最后输出：

```text
PASS：Skill 元数据、正文和资源按需进入模型上下文。
```

这轮证明了**文件内容进入上下文的时机**。由于三次工具调用是我预设的，它不能证明真实模型一定会主动选择这个 Skill。

## 第二轮：真实模型会不会自己选择 Skill（`ch07_live_skills.py`）

### 验证什么

离线脚本已证明加载机制，接下来要看真实模型收到任务后，会不会自己读取 Skill 正文和资源。这里的证据应是实际 `read_file` 轨迹，而不是模型在最终回答里说“我读过”。

### 改了什么

这个脚本不预设模型回复。任务是“写一份第 7 章 Skills 的学习笔记，说明三层加载”。运行时记录每次模型请求收到的内容、工具调用和最终文件操作。启动前的 `--dry-run` 只检查本地 Skill 能否被发现，不创建 Agent，也不调用模型。

```powershell
uv run --frozen python experiments/ch07_live_skills.py --dry-run
uv run --frozen python experiments/ch07_live_skills.py
```

### 预测结果

首轮请求中只有 Skill 列表；如果模型判断 `skill-guide` 与任务相关，它会读 `SKILL.md`。至于是否进一步读取术语卡和模板，取决于模型当时的选择，不能预先写成“必然发生”。

### 实际结果

`--dry-run` 发现了 `blog-post`、`skill-guide`、`social-media` 三个 Skill；其中 `skill-guide` 有一份参考资料和一份模板。真实模型运行退出码为 0。工具轨迹显示：

```text
read_file('/skills/skill-guide/SKILL.md')
read_file('/skills/skill-guide/references/concepts.md')
read_file('/skills/skill-guide/assets/guide-outline.md')
write_file('/notes/ch07-skills-learning-note.md')
read_file('/notes/ch07-skills-learning-note.md')
```

脚本记录的第 1 次模型请求是 `Level 1（仅元数据）`，第 2 次是 `Level 2（正文）`，后续请求是 `Level 3（正文 + 资源）`。最终判定为“模型自行读取 `SKILL.md`：是；继续读取 `references/assets`：是”。它还写入并读回了笔记文件。

这里要注意：模型生成的笔记正文里仍保留了一句“本次写作没有执行这两个命令”的旧表述。那是**生成内容中的错误**，不能拿来否定这次独立运行的工具轨迹；它也提醒我，实验结论要回到工具记录和文件状态核对。

## 第三轮：同名 Skill 从哪个来源生效（`test_skills.py`）

### 验证什么

如果共享目录与项目目录都提供 `skill-guide`，Agent 最终看到哪一份？这关系到团队默认流程能否被项目流程覆盖。

### 改了什么

测试在临时目录中分别创建 `/skill_sets/shared/skill-guide/SKILL.md` 和 `/skill_sets/project/skill-guide/SKILL.md`，描述中各写入 `SHARED_MARKER` 与 `PROJECT_MARKER`。再按共享目录、项目目录的顺序把这两个**父目录**传给 `build_graph()`。

```powershell
uv run --frozen pytest tests/test_skills.py -q
```

### 预测结果

同名 Skill 应由后一个来源覆盖；首轮提示词里应出现 `PROJECT_MARKER`，不出现 `SHARED_MARKER`。

### 实际结果

2026 年 10 月 26 日运行结果为 `2 passed`。覆盖测试的两条断言均通过。另一条测试再次执行第一轮的渐进式加载脚本。

这说明 `skills` 列表的**顺序有意义**。如果希望项目 Skill 覆盖团队 Skill，就要先放团队父目录，再放项目父目录。`skills=["/skills/"]` 指向的是包含多个 Skill 子目录的父目录，不是直接指向某个 `SKILL.md`。

## 第四轮：Skill 只读时，普通工作区还能写吗（`ch07_permission_deny.py`）

### 验证什么

我想把 `/skills/**` 设成只读，同时允许 Agent 往 `/notes/out.md` 写普通笔记。只检查“Skill 没变”还不够，因为模型可能根本没尝试修改它；必须同时检查工具返回的拒绝消息。

### 改了什么

实验在临时目录中创建 `skill-guide/SKILL.md`，配置 `FilesystemPermission(operations=["write"], paths=["/skills/**"], mode="deny")`。预设模型在同一轮分别调用两次 `write_file`：第一次覆盖 Skill，第二次写普通笔记。实验结束后核对工具消息和两个文件的真实内容。

```powershell
uv run --frozen python experiments/ch07_permission_deny.py
```

### 预测结果

Skill 写入被拒，`SKILL.md` 保持原样；`/notes/out.md` 写入成功，内容为 `ok`。

### 实际结果

离线脚本输出：

```text
Skill 写入被拒：是；SKILL.md 内容未变化：是。
普通笔记写入成功：是；/notes/out.md 内容为 ok。
PASS：只读 Skill 与可写工作区的权限边界生效。
```

我也运行了真实模型版本 `ch07_live_permissions.py`。那次模型**没有调用** `write_file` 去覆盖 Skill，只完成了普通笔记写入；脚本以 `SKIP`、退出码 2 结束。因此真实模型那轮没有触发拒写规则，不能写成“真实模型验证了拒写”。这里把两次实验分开记录：离线实验验证权限机制，真实模型运行只观察到它跳过改写 Skill 的选择。

## 第五轮：Skill 换一个 Backend 后还能发现吗（`ch07_backends.py`）

### 验证什么

本地文件之外，Skill 能否从 agent state 或 Store 中加载？多租户场景中，`CompositeBackend` 能否让两个组织各自只看到自己的 Skill？根据用户角色构造不同 `skills` 路径后，Agent 又会看到什么？

### 改了什么

脚本分别用 `create_file_data()` 向 `StateBackend` 注入文件、向 `InMemoryStore` 预填 Skill，再用 `CompositeBackend` 把 `/skills/` 路由到按组织 ID 选择的 Store namespace。最后建立工程师与数据角色的两份 Skill 父目录，分别创建 Agent。

```powershell
uv run --frozen python experiments/ch07_backends.py
```

### 预测结果与实际结果

预测是：State 能在本次调用发现文件；Store 预填一次后，两个线程都能发现文件；两个组织的 Skill 不串用；两个角色只看到各自的 Skill。脚本四组断言全部通过。这里用的是 `InMemoryStore`，证明同一进程里的跨线程共享，不证明进程重启后仍能读取。`CompositeBackend` 的 Store key 使用剥离 `/skills/` 挂载前缀后的相对路径。

## 第六轮：子 Agent 会继承哪些 Skill（`ch07_subagents.py`）

### 验证什么

同一个任务分别交给通用子 Agent、自定义但未配置 `skills` 的子 Agent、显式配置自己 Skill 的子 Agent，比较它们实际收到的提示词。

### 改了什么

脚本预设主 Agent 调用 `task`，记录主 Agent 和子 Agent 的每次模型请求。临时目录分别放主 Agent 与自定义子 Agent 的 Skill，用不同描述标记来源。

```powershell
uv run --frozen python experiments/ch07_subagents.py
```

### 预测结果与实际结果

预测通用子 Agent 继承主 Agent Skill；自定义子 Agent 默认不继承；显式配置后只发现自己的 Skill。三种情况的提示词断言全部通过。这个实验验证的是 **Skill 列表可见性**，没有顺便把工具、中间件和外部共享文件的行为算进去。

## 第七轮：读权限、审批、Memory 和 Tool（`ch07_visibility_memory_tools.py`、`ch07_interrupt.py`）

### 验证什么

我想确认三个容易混淆的问题：禁止读取 Skill 是否会让它完全不可见；`mode="interrupt"` 是否真的在写入前暂停；Memory、Skill、Tool 在模型请求里分别处于什么位置。

### 改了什么

第一个脚本给 `/skills/**` 加读权限拒绝规则，并尝试 `read_file`；同时用两次不同请求比较 `AGENTS.md`、Skill 正文与绑定工具。第二个脚本使用 `InMemorySaver`，预设一次 Skill 写入，然后分别模拟拒绝和批准审批决定。

```powershell
uv run --frozen python experiments/ch07_visibility_memory_tools.py
uv run --frozen python experiments/ch07_interrupt.py
```

### 预测结果与实际结果

`interrupt` 的两条路径符合预测：审批前文件不变，`reject` 后仍不变，`approve` 后才更新。Memory 正文在两次请求中都出现；Skill 未被读取时只有元数据；Tool 每轮可调用。

**读权限部分出现了不同于最初设想的结果**：`read_file` 被拒绝，但 Skill 的名称和描述仍出现在启动提示词中。这个权限规则拦截了工具读文件，并没有让 Skills 中间件停止发现元数据。如果要让某个 Agent 完全看不到 Skill，需要控制它配置的 Skill 来源或后端可见范围，不能只依赖读权限规则。

## 第八轮：Skill 中的脚本怎样执行（`ch07_script_execution.py`、`ch07_interpreter.py`）

### 验证什么

一条路径是 Agent 运行 `scripts/` 下的 Python 文件，取得标准输出；另一条路径是把 Skill 中的 JS helper 交给 QuickJS 执行。我要分别确认文件读取、工具调用和结果内容。

### 改了什么

Python 脚本实验在临时 Skill 目录中放入订单统计脚本，用预设模型调用 `execute`。解释器实验先调用 `read_file` 读取 JS 文件，再调用 QuickJS 的 `eval` 工具。后者使用可选依赖 `deepagents[quickjs]`。

```powershell
uv run --frozen python experiments/ch07_script_execution.py
uv run --frozen --extra quickjs python experiments/ch07_interpreter.py
```

### 预测结果与实际结果

两条路径都运行通过：Python 脚本向 Agent 返回订单统计的 JSON；QuickJS 执行 JS helper 后返回确定的分组。这里有两个边界必须保留。`LocalShellBackend` 在宿主机执行，**不能称为隔离沙箱**；本机 Docker 运行时未启动，因此容器沙箱没有验证。当前锁定的 `deepagents==0.7.8` 要求 `langchain-quickjs>=0.3.5`，其 `CodeInterpreterMiddleware` 不接受章节示例的 `skills_backend` 参数，所以本次验证的是“读取脚本后执行”，**不是 `metadata.entrypoint` 自动导入**。

## 实验中遇到的问题

### 1. “模型说它做了”与“工具真的执行了”不是一回事

第二轮的最终笔记里有一处过时的自述；第四轮真实模型又主动跳过了改写 Skill。于是我把判定依据固定为：工具调用、工具返回值、请求上下文和磁盘文件状态。最终回答只能作为补充线索。

### 2. `StateBackend` 与 `StoreBackend` 容易混淆

我原来把 `StateBackend` 写成“从 Store 加载 Skill”，这是错的。`StateBackend` 读写的是 Agent state 中的虚拟文件；预填文件时应使用 `create_file_data()`。`StoreBackend` 才使用 LangGraph Store，并通过 `namespace` 决定不同用户、线程或组织看到哪份文件。本地 `InMemoryStore` 退出进程就不保留数据，不能据此宣称已经实现跨进程持久化。

另一个误区是“`StateBackend` 一定要配置 checkpointer”。单次调用并不以它为构造前提；需要跨调用恢复同一线程，或让 `interrupt` 审批暂停后继续，才需要相应的持久化配置。我对单次 `StateBackend` 调用做过验证，它在未配置 checkpointer 的情况下成功返回；这不代表多轮状态会自动持久化。

### 3. 文件路径与执行环境是两件事

`FilesystemBackend(root_dir=..., virtual_mode=True)` 让虚拟路径对应到项目目录，并限制路径解析范围。它本身不提供隔离的代码执行环境。`scripts/` 里放了脚本，也不代表 Agent 一定有可用的 shell 或沙箱去运行。需要执行脚本时，应明确配置可执行的后端，再核对真实工具调用。

## 源码机制：一次 Skill 是怎样进入上下文的

这一章的主线可以写成一条链：

```text
skills=["/skills/"] 指定父目录
    ↓
Skills 中间件扫描各 Skill 的 SKILL.md frontmatter
    ↓
把名称、描述和路径放入启动提示词
    ↓
模型判断任务相关，调用 read_file 读取 SKILL.md
    ↓
模型按正文指引读取 references/、assets/ 或脚本
```

这里的“启动时只加载元数据”说的是**进入模型上下文的内容**。扫描程序仍要打开 `SKILL.md` 解析 frontmatter，并非磁盘上完全没有读取动作。多加一个 Skill 也会多一点元数据开销，只是通常远小于每次把完整正文和资源都塞进提示词。实际节省多少 token，本次没有测量。

一个 Skill 最小只需目录和 `SKILL.md`，常见结构如下：

```text
skills/
└── skill-guide/
    ├── SKILL.md             # 名称、描述和核心流程
    ├── scripts/             # 可选：脚本
    ├── references/          # 可选：详细参考资料
    └── assets/              # 可选：模板、数据等资产
```

`SKILL.md` 的 YAML frontmatter 中，`name` 和 `description` 必填，`name` 应与目录名一致。`license`、`compatibility`、`metadata` 和 `allowed-tools` 是可选字段。`description` 最好写明“做什么、什么请求要调用”；像“帮助用户解决问题”这样宽泛的句子，既可能误触发，也可能让真正相关的任务错过 Skill。`allowed-tools` 是规范中的实验性字段，不能代替 Deep Agents 的文件权限配置。

## 总结

我现在对 Skill 的理解是：它是一个**按任务启用的能力包**，不一定非得是一套很长的行业流程。它可以包含工作步骤、领域判断、参考资料、模板与脚本。Agent Skills 规范规定了可移植的基本结构，但不同产品的工具、执行环境和权限实现仍要分别检查。

这一章有三条容易混在一起的线：**Skill 告诉 Agent 怎样完成一类任务；Backend 决定文件从哪里来；Permission 决定 Agent 能做哪些文件操作。**`CompositeBackend` 可以把不同路径路由到不同存储；`FilesystemPermission` 管文件操作是否允许；`mode="interrupt"` 则会在受控操作前暂停，等待人的审批，且需要 checkpointer。审批针对受控写入，不是每次读取 Skill 都审批。团队与个人 Skill 可以放在不同父目录，也可以按角色、租户、请求或环境动态组装 `skills` 列表。

子 Agent 也要单独配置。通用子 Agent 会继承主 Agent 的 Skills；自定义子 Agent 默认不会继承主 Agent 的 Skills，需要显式指定。这里不能顺便推断所有工具和中间件都以同样方式继承。如果两个 Agent 指向同一磁盘目录或 Store 命名空间，它们仍可能共享外部文件。

脚本执行有两类思路：一类让 Agent 运行 `scripts/` 中的脚本，把标准输出交回 Agent；另一类在 QuickJS 中运行确定性的 JS helper。第八轮已分别验证“本地 shell 执行”和“读取脚本后交给解释器执行”，但本地 shell 不是隔离容器。章节中的 `metadata.entrypoint` 自动导入也没有在当前依赖版本上跑通，不能把这两项写成已验证。

最后用一个选择规则收尾：**始终需要的背景或偏好放 Memory；特定任务才需要的专业流程放 Skill；读文件、检索、写文件等原子动作交给 Tool。**我最初把 Skill 和 Tool 的后两条规则写反了。Memory 也不是单次聊天记录的同义词：聊天历史属于线程状态，长期记忆是否跨线程取决于背后的文件或 Store 配置。

目前已完成第 1 至第 8 轮的可复现实验，项目测试结果为 `15 passed`。后续仍需在真正隔离的沙箱中运行 Skill 脚本，找出与当前版本兼容的 Skill 模块自动导入方式，并用持久化 Store 验证跨进程恢复。不同 `description` 的匹配效果也需要在多种任务下单独观察，不能从一次命中推断召回率。

## 参考资料

- [《Deep Agents 实战》第 7 章：Skills](https://datawhalechina.github.io/deepagents-in-action/chapters/ch07-skills/)
- [Agent Skills 规范](https://agentskills.io/specification)
- [Deep Agents 官方 Skills 文档](https://docs.langchain.com/oss/python/deepagents/skills)
- [Deep Agents 官方 Backends 文档](https://docs.langchain.com/oss/python/deepagents/backends)
- [Deep Agents 官方 Subagents 文档](https://docs.langchain.com/oss/python/deepagents/subagents)
- [Deep Agents 官方 Memory 文档](https://docs.langchain.com/oss/python/deepagents/memory)

文中的 `task5` 实验和示例 Skill 属于本项目的课程实验材料；第 5 章 PDF 用作本篇的写法参考。
