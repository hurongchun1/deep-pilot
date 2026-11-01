"""在同一个 Agent 图中组合发布计划所需的工具、Skill 与记忆。"""

from __future__ import annotations

import os
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.middleware.memory import MemoryMiddleware
from dotenv import load_dotenv
from langchain.agents.middleware import TodoListMiddleware
from langchain_openai import ChatOpenAI

from tools import check_plan, read_plan, read_source, save_plan, save_preference

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
        tools=[read_source, save_plan, read_plan, check_plan, save_preference],
        checkpointer=checkpointer,
        system_prompt=(
            "你是青柠清单的上线计划助手。多步骤任务先用 write_todos。"
            "制定发布计划时读取 release-plan Skill、两份 sources 资料和 Skill 参考提纲。"
            "不要遍历无关目录。先读资料，再写计划；save_plan、read_plan、check_plan "
            "依次等待工具结果。检查 ok=true 后才能说结构通过。"
            "未来的发布步骤只能写成计划或待验证，不能写成已完成。"
            "资料不足时列出待确认项，不编造姓名和实测指标。"
            "仅在用户明确要求记住语言、语气或格式时调用 save_preference。"
        ),
    )


graph = build_graph(build_model())
