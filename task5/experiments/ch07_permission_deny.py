"""用预设模型验证 Skill 写保护不会阻止普通工作区写入。

在 task5 目录运行：uv run --frozen python experiments/ch07_permission_deny.py
按环境配置上传 LangSmith；--trace 强制开启，--no-trace 关闭。
预设模型不调用真实模型 API，开启追踪时仍会向 LangSmith 上传实验记录。
"""

from __future__ import annotations

import argparse
import os
import sys
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory


from deepagents import FilesystemPermission, create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tracers.langchain import wait_for_all_tracers
from dotenv import load_dotenv
from langsmith import Client, trace, tracing_context
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


def run_experiment() -> dict[str, bool]:
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
        result = graph.invoke(
            {"messages": [{"role": "user", "content": "验证写入权限。"}]},
            config={"run_name": "permission_deny_agent"},
        )
        tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        denied = [m for m in tool_messages if "permission denied for write" in str(m.content)]
        note = root / "notes" / "out.md"

        assert len(denied) == 1, tool_messages
        assert target.read_text(encoding="utf-8") == original
        assert note.read_text(encoding="utf-8") == "ok\n"
        print("Skill 写入被拒：是；SKILL.md 内容未变化：是。")
        print("普通笔记写入成功：是；/notes/out.md 内容为 ok。")
        print("PASS：只读 Skill 与可写工作区的权限边界生效。")
        return {"skill_write_denied": True, "skill_unchanged": True, "note_written": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trace", action=argparse.BooleanOptionalAction, default=None,
        help="开启 LangSmith 追踪；--no-trace 关闭，默认沿用环境配置。",
    )
    parser.add_argument("--project", help="LangSmith 项目名，默认沿用环境配置。")
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    configured = os.getenv("LANGSMITH_TRACING", os.getenv("LANGCHAIN_TRACING_V2", "false"))
    enabled = args.trace if args.trace is not None else configured.lower() in {"true", "1"}
    project = args.project or os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT") or "default"
    if enabled and not (os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")):
        parser.error("追踪已开启，请在环境变量或 task5/.env 中配置 LANGSMITH_API_KEY。")

    print(f"LangSmith：{'开启，项目=' + project if enabled else '关闭（可加 --trace 开启）'}")
    client = Client() if enabled else None
    try:
        with tracing_context(enabled=enabled, project_name=project, client=client):
            experiment_trace = trace(
                "ch07_permission_deny", client=client, project_name=project,
                inputs={"script": "experiments/ch07_permission_deny.py", "model": "ScriptedModel"},
                tags=["ch07", "permissions", "scripted"],
            ) if enabled else nullcontext()
            with experiment_trace as run:
                checks = run_experiment()
                if run is not None:
                    run.add_outputs({"status": "passed", **checks})
        if client is not None:
            wait_for_all_tracers()
            client.flush(timeout=15)
            print(f"LangSmith run_id：{run.id}")
            print(f"LangSmith 链接：{run.get_url()}")
    finally:
        if client is not None:
            client.close(timeout=15)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
