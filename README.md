# deep-pilot

本项目用于跟随 Datawhale 的 [《Deep Agents 实战》教程](https://datawhalechina.github.io/deepagents-in-action/)进行动手实践，记录示例代码、实验结果和学习笔记。

## 学习起点

从[第 1 章：从 Agent Framework 到 Agent Harness](https://datawhalechina.github.io/deepagents-in-action/chapters/ch01-agent-harness/)开始。该章介绍 Agent 开发的三个层次：

| 层次 | 代表工具 | 关注点 |
| --- | --- | --- |
| Runtime | LangGraph | 执行、状态与持久化 |
| Framework | LangChain | 模型、工具与 Agent 循环 |
| Harness | Deep Agents | 文件操作、上下文管理与任务委派等能力 |

本章配套的 [Notebook](https://github.com/datawhalechina/deepagents-in-action/blob/main/notebooks/ch01/01-agent-harness.ipynb) 可作为首次实验的参考。

## 当前状态

Task 1 已完成：围绕"工具间数据如何流动"完成四轮实验（offline 假模型 / live 真实模型对照、错误透传、规划中间件拆除），实验记录见 [task1/task1.md](task1/task1.md)。

Task 4 已在 [task4/README.md](task4/README.md) 建立独立的 DeepAgents content-builder 后端实验目录。Task 4 使用自己的 Python 3.12 环境和锁文件；下面的根目录环境说明适用于 Task 1。

## 目录结构

```
task1/
├── 1-simple-agent.py              # 最小 Deep Agent：天气工具入门示例
├── 1-research-agent.py            # 研究助手 Agent：Tavily 联网搜索 + 规划中间件
├── 1-calculate-agent.py           # 计算与汇率双工具 Agent（live，安全表达式求值）
├── 2-simple-agent.py              # 消息类型解析（Human/AI/Tool）+ check_weather 验证函数
├── 2-research-agent.py            # 第 4 轮实验：规划中间件拆除（TodoListMiddleware）
├── 2-calculate-agent-offline.py   # 第 1/3 轮实验：offline 假模型预设调用 + 错误透传
├── 2-calculate-agent-alive.py     # 第 2 轮实验：live 真实模型串联工具结果对照
├── CHECKIN.md                     # 打卡模板（五要素自查清单）
├── task1.md                       # Task 1 打卡文档（四轮实验完整记录）
└── images/                        # 实验截图

task4/                           # Content Builder 后端实验，安装和运行见 task4/README.md
```

## 环境配置

Python 3.11+，依赖通过 venv 管理：

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install deepagents langchain langchain-openai langchain-core tavily-python
```

需要的环境变量：

| 变量 | 用途 | 必需性 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | DeepSeek 模型（live 实验） | live 必需 |
| `TAVILY_API_KEY` | Tavily 联网搜索（research agent） | research 脚本必需 |
| `LANGSMITH_TRACING` / `LANGSMITH_API_KEY` / `LANGSMITH_PROJECT` | LangSmith 链路追踪 | 可选，调试用 |

## 运行方式

在仓库根目录下执行（`task1.xxx` 为模块路径写法）：

```powershell
# offline 实验（假模型，无 API 消耗，确定性复现）
.\venv\Scripts\python.exe -m task1.2-calculate-agent-offline

# live 实验（真实模型 deepseek-flash）
.\venv\Scripts\python.exe -m task1.2-calculate-agent-alive

# 规划中间件拆除实验（真实模型 + 联网搜索）
.\venv\Scripts\python.exe -m task1.2-research-agent
```

## 学习记录

| 章节 | 主题 | 状态 | 记录 |
| --- | --- | --- | --- |
| 第 1 章 | Agent Framework 与 Agent Harness | ✅ 完成 | [task1/task1.md](task1/task1.md) |

Task 1 四轮实验一览：

| 轮次 | 实验 | 模式 | 核心结论 |
| --- | --- | --- | --- |
| 第 1 轮 | 汇率变量实验 | offline | 脚本硬编码第二次调用参数，割裂工具间数据流，旧数字随汇率变化暴露 |
| 第 2 轮 | live 真实模型对照 | live（deepseek-flash） | 真实模型从对话历史取值串联工具，同汇率变化下自适应算出 756.0 |
| 第 3 轮 | 工具错误透传 | offline | 参数错误转 error 消息回给模型；工具内部异常直接中断 invoke |
| 第 4 轮 | 规划中间件拆除 | live（deepseek-flash） | write_todos 来自 TodoListMiddleware 注册；todos 状态键被 deepagents 钉死的 state_schema 挡住 |

## 参考资料

- [Deep Agents 实战教程](https://datawhalechina.github.io/deepagents-in-action/)
- [第 1 章：从 Agent Framework 到 Agent Harness](https://datawhalechina.github.io/deepagents-in-action/chapters/ch01-agent-harness/)
- [deepagents 项目仓库](https://github.com/langchain-ai/deepagents)
- [LangChain Fake Chat Models](https://docs.langchain.com/oss/python/langchain/models)
- [LangSmith](https://smith.langchain.com)
