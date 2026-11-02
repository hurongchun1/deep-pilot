"""在同一个 Agent 图中组合通用任务规划所需的工具、Skill 与记忆。"""

from __future__ import annotations

import os
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.middleware.memory import MemoryMiddleware
from dotenv import load_dotenv
from langchain.agents.middleware import TodoListMiddleware
from langchain_openai import ChatOpenAI

from tools import check_plan, list_sources, read_plan, read_source, save_plan, save_preference

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")


def build_model() -> ChatOpenAI:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise ValueError("启动真实模型前，请在 .env 中设置 OPENAI_API_KEY")
    parallel = os.getenv("AGENTSEEK_PARALLEL_TOOL_CALLS", "false").lower()
    if parallel not in {"true", "false"}:
        raise ValueError("AGENTSEEK_PARALLEL_TOOL_CALLS 只能设为 true 或 false")
    kwargs = {"model": os.getenv("AGENTSEEK_MODEL", "deepseek-ai/DeepSeek-V3.2"),
              "api_key": key,
              "model_kwargs": {"parallel_tool_calls": parallel == "true"}}
    if base := os.getenv("OPENAI_API_BASE", "").strip():
        kwargs["base_url"] = base
    return ChatOpenAI(**kwargs)


def build_graph(chat_model, *, root: Path = PROJECT_ROOT, checkpointer=None):
    backend = FilesystemBackend(root_dir=root, virtual_mode=True)
    return create_deep_agent(
        model=chat_model,
        middleware=[
            TodoListMiddleware(),
            MemoryMiddleware(
                backend=backend,
                sources=["/AGENTS.md", "/memory/preferences.md"],
                system_prompt="<agent_memory>\n{agent_memory}\n</agent_memory>",
            ),
        ],
        skills=["/skills/"],
        backend=backend,
        tools=[list_sources, read_source, save_plan, read_plan, check_plan, save_preference],
        checkpointer=checkpointer,
        system_prompt=(
            "你是通用任务规划助手，帮助用户把学习、开发、活动等目标拆成行动计划。"
            "多步骤任务先用 write_todos，读取 task-planning Skill 及其参考提纲。"
            "用户消息是主要输入；仅在需要补充资料时用 list_sources 发现文件，"
            "只读与当前任务相关的资料。不要把其他案例的条件套到当前任务上。"
            "不要遍历无关目录。先明确目标和约束，再写计划；save_plan、read_plan、check_plan "
            "依次等待工具结果。检查 ok=true 后才能说结构通过。"
            "行动步骤写清顺序、产物、时间安排及验收方式；未来动作不能写成已完成。"
            "缺少关键目标时询问用户；其余缺失信息列为待确认，建议与已知事实分开。"
            "不编造日期、预算、负责人或实际结果。未给开始日期时用相对时间。"
            "仅在用户明确要求记住语言、语气或格式时调用 save_preference。"
        ),
    )


graph = build_graph(build_model())
