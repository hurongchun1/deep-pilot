"""离线区分 Skill 可见性、Memory 常驻内容与 Tool 可调用性。

在 task5 目录运行：uv run --frozen python experiments/ch07_visibility_memory_tools.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from _scripted import ScriptedModel, skill_file
from deepagents import FilesystemPermission, create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool


@tool
def atomic_ping() -> str:
    """返回一个简单的连通性检查结果。"""
    return "pong"


def main() -> None:
    with TemporaryDirectory(prefix="ch07-visible-") as directory:
        root = Path(directory)
        (root / "AGENTS.md").write_text("# 项目记忆\nMEMORY_MARKER：始终用中文回答。\n", encoding="utf-8")
        skill = root / "skills" / "special-guide" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            skill_file("special-guide", "SKILL_METADATA_MARKER：专项写作时使用")
            + "SKILL_BODY_MARKER：先核对资料。\n",
            encoding="utf-8",
        )
        model = ScriptedModel(replies=[AIMessage(content="完成"), AIMessage(content="完成")])
        graph = create_deep_agent(
            model=model,
            backend=FilesystemBackend(root_dir=root, virtual_mode=True),
            memory=["/AGENTS.md"],
            skills=["/skills/"],
            tools=[atomic_ping],
        )
        for task in ("闲聊", "列出可以使用的能力"):
            graph.invoke({"messages": [{"role": "user", "content": task}]})
        assert all("MEMORY_MARKER" in prompt for prompt in model.prompts)
        assert all("SKILL_METADATA_MARKER" in prompt for prompt in model.prompts)
        assert all("SKILL_BODY_MARKER" not in prompt for prompt in model.prompts)
        assert "atomic_ping" in model.bound_tool_names
        print("Memory 正文每次都在提示词；Skill 只有元数据；Tool 始终可调用。")

        hidden_model = ScriptedModel(
            replies=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "read_file",
                            "args": {"file_path": "/skills/special-guide/SKILL.md"},
                            "id": "blocked-read",
                        }
                    ],
                ),
                AIMessage(content="读取结束"),
            ]
        )
        hidden_graph = create_deep_agent(
            model=hidden_model,
            backend=FilesystemBackend(root_dir=root, virtual_mode=True),
            skills=["/skills/"],
            permissions=[
                FilesystemPermission(operations=["read"], paths=["/skills/**"], mode="deny")
            ],
        )
        hidden_result = hidden_graph.invoke({"messages": [{"role": "user", "content": "读取 Skill"}]})
        denied = [
            m for m in hidden_result["messages"]
            if isinstance(m, ToolMessage) and "permission denied for read" in str(m.content)
        ]
        assert denied, "read_file 没有被读权限规则拦截"
        assert "SKILL_METADATA_MARKER" in hidden_model.prompts[0]
        print("读权限拒绝了 read_file，但 Skill 元数据仍被发现；可见性需要额外控制来源。")
    print("PASS：可见性与 Skill/Memory/Tool 分工实验通过。")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
