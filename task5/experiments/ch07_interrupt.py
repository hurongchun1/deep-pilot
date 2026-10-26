"""离线验证 Skill 写入审批的暂停、拒绝与批准路径。

审批决定由本脚本模拟，不代表真实用户已批准任何外部写入。
在 task5 目录运行：uv run --frozen python experiments/ch07_interrupt.py
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
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command


def run_decision(decision: str) -> None:
    with TemporaryDirectory(prefix=f"ch07-interrupt-{decision}-") as directory:
        root = Path(directory)
        target = root / "skills" / "editable-guide" / "SKILL.md"
        target.parent.mkdir(parents=True)
        original = skill_file("editable-guide", "用于写入审批实验")
        target.write_text(original, encoding="utf-8")
        replacement = skill_file("editable-guide", "APPROVED_MARKER")

        model = ScriptedModel(
            replies=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "write_file",
                            "args": {
                                "file_path": "/skills/editable-guide/SKILL.md",
                                "content": replacement,
                            },
                            "id": "approval-write",
                        }
                    ],
                ),
                AIMessage(content="已收到审批结果。"),
            ]
        )
        graph = create_deep_agent(
            model=model,
            backend=FilesystemBackend(root_dir=root, virtual_mode=True),
            skills=["/skills/"],
            permissions=[
                FilesystemPermission(
                    operations=["write"], paths=["/skills/**"], mode="interrupt"
                )
            ],
            checkpointer=InMemorySaver(),
        )
        config = {"configurable": {"thread_id": f"approval-{decision}"}}
        paused = graph.invoke(
            {"messages": [{"role": "user", "content": "更新 Skill 描述。"}]},
            config=config,
        )
        assert paused.get("__interrupt__"), "写入前没有进入审批暂停"
        assert target.read_text(encoding="utf-8") == original, "审批前文件已变化"

        resumed = graph.invoke(
            Command(resume={"decisions": [{"type": decision}]}),
            config=config,
        )
        assert not resumed.get("__interrupt__"), "提交审批决定后没有恢复"
        actual = target.read_text(encoding="utf-8")
        if decision == "approve":
            assert actual == replacement, "批准后没有写入"
            print("批准路径：写入前暂停；提交 approve 后文件更新。")
        else:
            assert actual == original, "拒绝后文件仍被写入"
            print("拒绝路径：写入前暂停；提交 reject 后文件保持原样。")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    run_decision("reject")
    run_decision("approve")
    print("PASS：Skill 写入审批的暂停与恢复实验通过。")
