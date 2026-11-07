# 运行证据

## 当前通用任务规划版

`offline-learning.json`、`offline-development.json`、`offline-event.json` 是三个无密钥案例的精简运行记录。`mode=scripted` 表示回复预设，验证 Agent 图、中间件、Skill、跨会话偏好加载和文件工具，不证明真实模型自主规划。

`experiments/live_demo.py` 在运行后写入 `planner-live-<run-id>.json`，记录本次输入、模型、工具调用与状态、结构检查工具结果、待办状态、跨会话偏好加载和最终文件哈希；运行中失败也保存已观察到的记录。`planner-live-4aad1ec7cc74.json` 是 `deepseek-flash` 对学习场景的一次真实模型运行：保存、读回、结构检查依序成功，计划位于 `artifacts/learning-plan-live.md`。偏好写入时模型先尝试了无效的 `plan_format` 键，随后改用有效的 `format` 键。此证据只覆盖本次输入与模型配置。

本地 JSON 不包含完整模型请求与响应。需要完整审阅时使用可选的 LangSmith 追踪。结构检查通过不证明事实准确、计划可行或任务已经完成。
