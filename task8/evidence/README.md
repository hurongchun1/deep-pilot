# 运行证据

## 当前通用任务规划版

`offline-learning.json`、`offline-development.json`、`offline-event.json` 是三个无密钥案例的精简运行记录。`mode=scripted` 表示回复预设，验证 Agent 图、中间件、Skill、跨会话偏好加载和文件工具，不证明真实模型自主规划。

`experiments/live_demo.py` 在运行后写入 `planner-live-<run-id>.json`，记录本次输入、模型、工具调用与状态、结构检查工具结果、待办状态、跨会话偏好加载和最终文件哈希；运行中失败也保存已观察到的记录。未运行真实模型前，不能声称通用版已经通过真实模型验证。

本地 JSON 不包含完整模型请求与响应。需要完整审阅时使用可选的 LangSmith 追踪。结构检查通过不证明事实准确、计划可行或任务已经完成。

## 历史产品上线示例

`offline-release-plan.json` 与 `live-0bbfc76a4460.json` 属于旧版青柠清单上线计划助手。后者记录了 2026-11-01 的真实模型运行。它们按原样保留，仅供历史对照，不用于验证当前通用版，也不应使用当前通用结构检查器重新解读旧结果。
