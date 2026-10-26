"""离线验证 Skill 写保护不会阻止普通工作区写入。

在 task5 目录运行：uv run --frozen python experiments/ch07_permission_deny.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from deepagents import FilesystemPermission, create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr


class ScriptedModel(BaseChatModel):
    replies: list[AIMessage]
    _cursor: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "offline-skill-permission"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        reply = self.replies[self._cursor]
        self._cursor += 1
        return ChatResult(generations=[ChatGeneration(message=reply)])


def run_experiment() -> None:
    with TemporaryDirectory(prefix="ch07-permission-") as directory:
        root = Path(directory)
        target = root / "skills" / "skill-guide" / "SKILL.md"
        target.parent.mkdir(parents=True)
        original = "---\nname: skill-guide\ndescription: 学习 Skills 时使用。\n---\n\n# 指南\n"
        target.write_text(original, encoding="utf-8")

        model = ScriptedModel(
            replies=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "write_file",
                            "args": {
                                "file_path": "/skills/skill-guide/SKILL.md",
                                "content": "PWNED",
                            },
                            "id": "blocked-write",
                        },
                        {
                            "name": "write_file",
                            "args": {"file_path": "/notes/out.md", "content": "ok\n"},
                            "id": "allowed-write",
                        },
                    ],
                ),
                AIMessage(content="已检查两个写入结果。"),
            ]
        )
        graph = create_deep_agent(
            model=model,
            backend=FilesystemBackend(root_dir=root, virtual_mode=True),
            skills=["/skills/"],
            permissions=[
                FilesystemPermission(operations=["write"], paths=["/skills/**"], mode="deny"),
            ],
        )
        result = graph.invoke({"messages": [{"role": "user", "content": "验证写入权限。"}]})
        tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        denied = [m for m in tool_messages if "permission denied for write" in str(m.content)]
        note = root / "notes" / "out.md"

        assert len(denied) == 1, tool_messages
        assert target.read_text(encoding="utf-8") == original
        assert note.read_text(encoding="utf-8") == "ok\n"
        print("Skill 写入被拒：是；SKILL.md 内容未变化：是。")
        print("普通笔记写入成功：是；/notes/out.md 内容为 ok。")
        print("PASS：只读 Skill 与可写工作区的权限边界生效。")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    run_experiment()
