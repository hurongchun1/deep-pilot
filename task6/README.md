# Task 6：长期记忆与 Human-in-the-Loop 学习

本目录整理了第八章和第九章的学习总结。当前六组实验、真实模型入口和运行命令见 [experiments/README.md](experiments/README.md)。预设模型实验不需要模型 API 密钥；所有实验默认沿用 Windows 环境中的 LangSmith 配置，也支持 `--trace` / `--no-trace` 开关。

- [第八章总结：长期记忆](ch08-long-term-memory-summary.md)
- [第九章总结：Human-in-the-Loop](ch09-human-in-the-loop-summary.md)

## 运行实验

在 `task6` 目录中运行：

```powershell
uv run --frozen python -X utf8 experiments/01_thread_state.py
uv run --frozen python -X utf8 experiments/02_memory_routing.py
uv run --frozen python -X utf8 experiments/03_hitl_review.py
uv run --frozen python -X utf8 experiments/04_interrupt_replay.py
```

| 实验问题 | 脚本 | 检查什么 |
| --- | --- | --- |
| 1. 同一 thread 能否恢复 state？ | `01_thread_state.py` | Checkpoint 中的消息和自定义 `topic`；新 thread 的独立状态 |
| 2. 不同 thread 能否共享用户偏好？ | `02_memory_routing.py` | Store 的 namespace、key、内容和新 thread 的模型请求 |
| 3. `memory=` 会自动保存吗？ | `02_memory_routing.py` | 加载前后模型请求、真实 `edit_file` 结果、缺失文件及 Store 内容 |
| 4. CompositeBackend 如何路由？ | `02_memory_routing.py` | thread A、B 的 state 文件与 Store 中去除路由前缀的 key |
| 5. 工具如何暂停和恢复？ | `03_hitl_review.py` | `action_requests`、Checkpoint、中断前后执行记录和不同 thread 状态 |
| 6. 四种审核决定有何区别？ | `03_hitl_review.py` | 实际执行参数、ToolMessage，以及 `respond` 时工具没有执行 |
| 7. `when` 与文件权限如何工作？ | `03_hitl_review.py` | 条件放行与拒绝、文件权限 `interrupt` 和 `deny` 的结果 |
| 8. 恢复时节点会重跑吗？ | `04_interrupt_replay.py` | 中断前后分别记录的执行次数 |

## 阅读和验证边界

- `_support.py` 提供预设模型；模型回复和工具调用由实验指定，但图执行、工具、权限、Checkpointer 和 Store 仍真实运行。因此结果不能证明真实模型一定会选择正确工具。
- `InMemorySaver` 和 `InMemoryStore` 只在当前进程内有效；实验验证跨线程访问，不验证重启后的持久化。namespace 分组也不能替代身份认证和授权。
- `when` 示例的字符串判断仅用于展示机制，不是可靠的真实路径安全检查。文件权限实验仅写入运行期间创建的临时目录。
- 如果要进一步观察真实模型的工具选择，需要另行配置模型服务和追踪，并检查实际工具调用和存储结果。
