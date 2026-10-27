# 第 7 章 Skills 实验覆盖清单

本清单对应[《Deep Agents 实战》第 7 章](https://datawhalechina.github.io/deepagents-in-action/chapters/ch07-skills/)。运行目录均为 `task5`。离线脚本使用预设模型来固定工具调用，检查真实 Agent 图、中间件和后端的行为；真实模型脚本观察模型自己的选择。两类证据不能互相替代。

| 知识点 | 实验与检查点 | 当前结果 |
| --- | --- | --- |
| Skill 目录、frontmatter、`description` | `skills/skill-guide/SKILL.md`；真实模型是否选中该 Skill | 示例已具备；真实模型在本次笔记任务中选中。尚未做不同描述的命中率比较。 |
| 渐进式加载三级 | `ch07_progressive_disclosure.py` 比较四轮提示词；`ch07_live_skills.py` 记录真实模型轨迹 | 两项均已运行通过；真实模型读取正文、术语卡和模板。 |
| `FilesystemBackend`、虚拟路径 | 渐进式加载脚本使用 `virtual_mode=True` 和 `/skills/` 父目录 | 已运行通过。 |
| `StateBackend` | `ch07_backends.py` 用 `files` 与 `create_file_data()` 注入 | 单次调用通过；未验证跨调用状态恢复。 |
| `StoreBackend` | `ch07_backends.py` 预填一次 `InMemoryStore`，从两个线程发现 Skill | 同一进程内通过；未验证跨进程持久化。 |
| `CompositeBackend` 与租户命名空间 | `ch07_backends.py` 让 `/skills/` 路由到不同组织的 Store namespace | 两个组织分别只见自己的 Skill，已通过。 |
| 多源覆盖、按角色动态选择 | `test_skills.py` 检查后者覆盖前者；`ch07_backends.py` 检查角色对应的父目录 | 已通过。 |
| 子 Agent Skill 继承 | `ch07_subagents.py` 比较通用、自定义未声明、自定义显式声明 | 三种情况已通过。 |
| 可见性、读写权限 | `ch07_visibility_memory_tools.py`、`ch07_permission_deny.py` | 读写工具拦截已通过；读权限拒绝**不会隐藏**启动提示词里的 Skill 元数据。 |
| 写入审批 | `ch07_interrupt.py` 检查暂停前文件、模拟 reject 与 approve 后文件 | 两条路径已通过；使用 `InMemorySaver`，未接真实审批 UI。 |
| Skill 脚本执行 | `ch07_script_execution.py` 用 `LocalShellBackend` 调用 `scripts/` 中的 Python 脚本 | 工具调用与标准输出已通过；**本地 shell 不提供沙箱隔离**。 |
| QuickJS 解释器 | `ch07_interpreter.py` 先读 Skill 脚本，再交给 `CodeInterpreterMiddleware` 执行 | 已通过；当前依赖版本不支持章节示例的 `skills_backend` 参数，未验证 `metadata.entrypoint` 自动导入。 |
| Skill / Memory / Tool 分工 | `ch07_visibility_memory_tools.py` 比较提示词内容与绑定工具 | 已通过：Memory 正文常驻、Skill 仅元数据常驻、Tool 每轮可用。 |

## 一次运行全部可复现的离线实验

```powershell
uv run --frozen python experiments/ch07_progressive_disclosure.py
uv run --frozen python experiments/ch07_backends.py
uv run --frozen python experiments/ch07_subagents.py
uv run --frozen python experiments/ch07_permission_deny.py
uv run --frozen python experiments/ch07_interrupt.py
uv run --frozen python experiments/ch07_visibility_memory_tools.py
uv run --frozen python experiments/ch07_script_execution.py
uv run --frozen --extra quickjs python experiments/ch07_interpreter.py
uv run --frozen pytest tests/test_skills.py -q
```

`ch07_backends.py` 使用预设模型，也支持 LangSmith 追踪。它默认读取环境变量和
`task5/.env` 中的追踪配置；加 `--trace` 可强制开启，`--no-trace` 可关闭。
例如 `uv run --frozen python experiments/ch07_backends.py --trace --project deep-pilot`。
开启时需配置 `LANGSMITH_API_KEY`，根记录名为 `ch07_backends`，下面按四组实验展开；
脚本退出前等待上传，并打印追踪链接。该记录展示预设模型下的运行过程，不代表真实模型调用。

第四轮的 `ch07_permission_deny.py` 使用相同追踪选项，例如
`uv run --frozen python experiments/ch07_permission_deny.py --trace`。
根记录名为 `ch07_permission_deny`，可展开查看两个 `write_file` 调用及拒写返回；
根记录输出同时保存 Skill 拒写、内容未变和普通笔记写入三项检查结果。

真实模型实验需要按 `.env.example` 配置模型密钥：

```powershell
uv run --frozen python experiments/ch07_live_skills.py
uv run --frozen python experiments/ch07_live_permissions.py
```

`ch07_live_permissions.py` 的一次运行中，模型没有尝试改写 Skill，脚本返回 `SKIP`。它只证明模型跳过了该操作；拒写机制由 `ch07_permission_deny.py` 的实际工具返回和文件状态验证。

## 目前不能标为“全部验证通过”的部分

1. 真正隔离的容器沙箱：本机 Docker 命令可用，但运行时未启动；`LocalShellBackend` 实验不能替代容器隔离测试。
2. `metadata.entrypoint` 自动导入：锁定的 `deepagents==0.7.8` 要求 `langchain-quickjs>=0.3.5`，当前 `CodeInterpreterMiddleware` 构造函数没有章节示例使用的 `skills_backend` 参数。解释器实验采用显式读取脚本再执行。
3. 持久化 Store 的跨进程恢复、不同 `description` 的匹配效果、以及真实审批 UI 尚未做端到端验证。

因此，本目录已覆盖章节的大部分可离线验证机制，但不能说“所有实验都已经完成”。
