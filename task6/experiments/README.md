# 长期记忆与人工审批实验

六个离线实验对应本次讨论的六个问题。另有真实模型入口，检查模型的工具选择与回答行为。

## 运行

在 `task6` 目录执行，沿用现有依赖，不需要添加包：

```powershell
uv sync --frozen
uv run --frozen python -X utf8 experiments/run_all.py
```

也可以单独运行：

```powershell
uv run --frozen python -X utf8 experiments/01_memory_lifetime.py
```

| 脚本 | 实验内容 | 验收证据 |
| --- | --- | --- |
| `01_memory_lifetime.py` | 临时草稿和长期偏好的生命周期 | 新线程读不到草稿、能加载偏好；旧线程仍有草稿；新建 Store 后偏好消失 |
| `02_user_isolation.py` | 用户隔离与错误共享反例 | 相同路径、不同 namespace 加载不同内容；固定 namespace 出现串记忆 |
| `03_review_decisions.py` | approve / edit / reject / respond 和批量审批 | 中断前执行列表为空；批准或编辑后才记录参数；respond 不执行工具体 |
| `04_path_permissions.py` | allow / interrupt / deny | 新建、覆盖、编辑、删除；拒绝后内容不变；包含受保护文件的父目录删除不产生部分修改 |
| `05_reviewed_learning.py` | 经审批更新长期规则 | 三个独立分支检查 Store 和新线程实际加载的规则 |
| `06_research_handoff.py` | 三轮研究交接 | 错误结论被拒绝，补充知识保留，第三轮加载进度，报告不含错误结论 |
| `07_live_assistant.py` | 真实模型交互 | 人工查看工具参数、存储和新线程回答，判断偏好是否真正影响行为 |

离线实验通过断言验收，失败时返回非零状态；`run_all.py` 失败立即停止。`_lab.py` 是共用设施。所有文件写入均在虚拟 State / 内存 Store 中；邮件工具只向当前进程列表追加参数。没有真实邮件、真实文件删除或网络模型请求；开启追踪后会向 LangSmith 上传执行记录。

## LangSmith 链路追踪

所有编号实验默认沿用 Windows 进程环境中的 `LANGSMITH_TRACING`、`LANGSMITH_API_KEY`、`LANGSMITH_PROJECT`、`LANGSMITH_ENDPOINT` 等配置，也兼容旧的 `LANGCHAIN_*` 配置。`task6/.env` 只补充缺失值，不覆盖已有环境变量。默认不开启的环境可用 `--trace` 强制开启；`--no-trace` 则强制关闭本次追踪。

```powershell
# 所有离线实验开启追踪，不会调用真实模型
uv run --frozen python -X utf8 experiments/run_all.py --trace
# 单个实验
uv run --frozen python -X utf8 experiments/03_review_decisions.py --trace
# 完全离线运行
uv run --frozen python -X utf8 experiments/run_all.py --no-trace
# 真实模型也使用相同追踪选项
uv run --frozen python -X utf8 experiments/07_live_assistant.py --trace
```

开启追踪时会打印项目和 Trace 链接，每个实验以 `task6/脚本名` 作为根节点，包含模型请求、文件工具、权限中间件、中断与恢复调用。结束前等待后台上传。若没有配置项目名则使用 `deep-pilot-task6`。预设模型记录会标记为 `scripted`，不能把它误认为真实模型推理。

在 LangSmith 中展开根节点，对照同一 `thread_id` 的暂停和恢复；检查模型输入中的记忆、工具参数与 ToolMessage。Store 的最终内容仍由脚本断言验收，不意味着每次底层 Store 操作都会单独形成 trace。运行成功与追踪上传成功是两个独立结果；上传问题需检查终端 SDK 提示和 LangSmith 项目记录。新设置 Windows 环境变量后，可能需要重启终端或 Codex 才能被进程继承。

## 真实模型实验

复制 `task6/.env.example` 为 `task6/.env`，填写 `OPENAI_API_KEY`，确认 `OPENAI_API_BASE` 和 `AGENTSEEK_MODEL`，然后运行：

```powershell
uv run --frozen python -X utf8 experiments/07_live_assistant.py --user alice
```

该入口会调用配置的模型服务并产生费用；LangSmith 追踪沿用上面的设置。不要使用真实隐私资料做练习。

建议按以下顺序输入：

1. `记住：我喜欢中文注释、英文变量名。` 审批时先看目标路径和内容，再输入 `approve`。
2. `/store` 检查是否实际保存；`/new` 后输入 `帮我写一个排序函数`，观察偏好是否生效。
3. `/user bob`，询问 `我有什么编码偏好？`；检查没有读取 Alice 的记忆。
4. `/user alice`，输入 `以后先给最小可运行示例，再解释原理。请记住。`，用 `edit` 将参数中的规则收窄为“只有用户要求代码时才提供示例”。注意保留 `file_path`、`old_string`、`new_string` 等完整参数。
5. `/new` 后分别问概念题和代码题，观察规则适用范围。
6. 提供一小段可信资料，要求保存来源、笔记与下一步进度；每轮 `/new` 后要求继续研究。对一条错误更新输入 `reject` 并说明原因，再用 `/store` 核对原结论是否保留。

审批界面接受列出的英文决策，`edit` 接受完整参数 JSON 对象。只在审批后才会执行对应写入；一批多个请求须逐个决策。恢复保持相同线程和用户。`/quit` 退出。

## 观察与练习

每次记录：输入、工具或中断参数、实际存储前后差异、新线程模型请求或回答。离线脚本的 `model.prompts` 捕获实际模型请求，可加打印或断点观察。

- 实验 1：删除 `memory=` 配置，观察“文件仍在 Store 中”和“启动时自动加载”有何区别；缺失文件不会自动创建。
- 实验 2：将用户 namespace 固定为共享值，对比数据泄漏反例。namespace 是数据分区，真实服务还须验证身份和线程访问权。
- 实验 3：给拒绝反馈添加下一步要求；真实模型入口中观察它是否照做。离线模型只提供固定调用，不能证明模型会自行选择正确动作。
- 实验 4：路径权限针对内置文件工具，不自动约束任意自定义工具或 `execute`。实验 3 展示自定义工具如何用 `interrupt_on` 审批。
- 实验 5、6：离线证明存储、审批和加载链路；内容生成、主动记忆与回答质量需真实模型实验验证。

`InMemorySaver`、`InMemoryStore` 仅在当前进程有效；实验 1 通过新建空实例模拟重启后的内存丢失，不声称完成跨进程持久化。真实入口的 `/new` 是换线程，退出程序会丢失记忆；若要研究重启恢复，下一步应接入持久化 Store 和 Checkpointer。

参考：[第 8 章长期记忆](https://datawhalechina.github.io/deepagents-in-action/chapters/ch08-long-term-memory/)、[第 9 章 Human-in-the-Loop](https://datawhalechina.github.io/deepagents-in-action/chapters/ch09-human-in-the-loop/)。按本项目锁定的 Deep Agents 0.7.10 验证。

## 验证记录（2026-10-30）

复用项目依赖与预设模型，统一接入环境变量、追踪开关、实验根节点和退出前上传等待。`run_all.py --no-trace` 的六个实验全部通过；`03_review_decisions.py --trace` 已上传到当前配置的 `deep-pilot` 项目，并回读确认根节点结束、无错误、包含 10 次图调用。真实模型的服务调用未在此验证中执行。
