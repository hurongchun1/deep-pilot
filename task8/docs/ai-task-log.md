# Task 8 开发记录

## 2026-11-02：将产品上线示例改为通用任务规划助手

- 类型：需求调整。
- 目标：支持直接输入学习、开发、活动等目标、时间和约束；无需修改代码即可规划其他任务。
- 验收：同一 Agent 图完成三个场景的计划保存、读回和结构检查；跨会话加载明确保存的格式偏好；资料可选；自定义输入可通过真实模型入口传入。
- 复用：create_deep_agent、TodoListMiddleware、MemoryMiddleware、FilesystemBackend、文件工具、预设模型及运行证据模式。未增加依赖。
- 修改：agent.py 和 AGENTS.md 改为通用规划规则；tools.py 新增资料发现、取消固定资料白名单并替换结构规则；task-planning Skill 替换 release-plan；sample_plan.py 提供三个预设案例；运行脚本支持场景和自定义目标；README 更新使用方式和历史证据边界。
- 验证：`uv sync --frozen` 成功；`uv run --frozen pytest tests -q` 为 17 passed；离线脚本三个案例全部 PASS，生成对应计划和证据；真实模型脚本 --help 正常。测试覆盖真实入口的编排成功及失败取证，但使用预设模型，没有外部模型请求。
- 边界：尚未运行通用版的真实模型验证。结构检查仅检查必要章节与非空正文，不证明事实准确或排期可行。旧版青柠清单产物、资料及证据保留作历史对照，旧 Skill 路径不再存在；旧证据不用于证明新版能力。
