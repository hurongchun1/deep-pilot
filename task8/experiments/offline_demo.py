"""无密钥运行发布计划 Agent；模型回复预设，Agent 图与工具真实执行。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langsmith import tracing_context

os.environ.setdefault("OPENAI_API_KEY", "unused-offline-key")
os.environ["LANGSMITH_TRACING"] = "false"

import agent  # noqa: E402 — 先提供不发送请求的占位密钥
import tools  # noqa: E402
from sample_plan import PLAN  # noqa: E402
from scripted_model import ScriptedModel, call  # noqa: E402


def prepare_workspace(root: Path) -> None:
    for relative in ("AGENTS.md", "memory/preferences.md"):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((agent.PROJECT_ROOT / relative).read_text(encoding="utf-8"), encoding="utf-8")
    shutil.copytree(agent.PROJECT_ROOT / "sources", root / "sources")
    shutil.copytree(agent.PROJECT_ROOT / "skills", root / "skills")


def tool_calls(messages) -> list[dict]:
    return [call for message in messages if isinstance(message, AIMessage)
            for call in message.tool_calls]


def main() -> None:
    with tracing_context(enabled=False), TemporaryDirectory(prefix="release-pilot-") as folder:
        root = Path(folder)
        prepare_workspace(root)
        old_root = tools.PROJECT_ROOT
        tools.PROJECT_ROOT = root
        try:
            writer = ScriptedModel(replies=[
                call("save_preference", {"key": "format", "value": "中文分节 Markdown"}, "remember"),
                AIMessage(content="已保存格式偏好。"),
            ])
            graph = agent.build_graph(writer, root=root, checkpointer=InMemorySaver())
            graph.invoke(
                {"messages": [{"role": "user", "content": "请记住：以后写上线计划用中文分节 Markdown。"}]},
                {"configurable": {"thread_id": "remember"}},
            )
            assert "format: 中文分节 Markdown" in (root / "memory/preferences.md").read_text(encoding="utf-8")

            model = ScriptedModel(replies=[
                call("write_todos", {"todos": [{"content": "读取资料并制定上线计划", "status": "in_progress"}]}, "plan"),
                call("read_file", {"file_path": "/skills/release-plan/SKILL.md"}, "skill"),
                call("read_file", {"file_path": "/skills/release-plan/references/plan-outline.md"}, "outline"),
                call("read_source", {"name": "product-brief.md"}, "brief"),
                call("read_source", {"name": "release-constraints.md"}, "constraints"),
                call("save_plan", {"slug": "qingning-release-plan", "content": PLAN}, "save"),
                call("read_plan", {"slug": "qingning-release-plan"}, "readback"),
                call("check_plan", {"slug": "qingning-release-plan"}, "check"),
                call("write_todos", {"todos": [{"content": "读取资料并制定上线计划", "status": "completed"}]}, "done"),
                AIMessage(content="上线计划已保存，结构检查通过。"),
            ])
            graph = agent.build_graph(model, root=root, checkpointer=InMemorySaver())
            snapshots = list(graph.stream(
                {"messages": [{"role": "user", "content": "为青柠清单 v1.2 制定上线计划。"}]},
                {"configurable": {"thread_id": "release"}}, stream_mode="values",
            ))
            final = snapshots[-1]
            calls = tool_calls(final["messages"])
            results = {m.tool_call_id: m for m in final["messages"] if m.type == "tool"}
            names = [item["name"] for item in calls]
            checker = json.loads(results["check"].text)
            assert checker["ok"] and results["readback"].text == PLAN
            assert "format: 中文分节 Markdown" in model.prompts[0]
            assert {"write_todos", "read_file", "read_source", "save_plan", "read_plan", "check_plan"} <= set(names)
            assert all(message.status != "error" for message in results.values())
            states = []
            for snapshot in snapshots:
                state = [todo["status"] for todo in snapshot.get("todos") or []]
                if state and (not states or state != states[-1]):
                    states.append(state)
            assert states and states[-1] == ["completed"]
            source_artifact = root / "artifacts/qingning-release-plan.md"
            assert source_artifact.read_text(encoding="utf-8") == PLAN
        finally:
            tools.PROJECT_ROOT = old_root

        artifact = agent.PROJECT_ROOT / "artifacts/qingning-release-plan-offline.md"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_artifact, artifact)
        final_check = json.loads(tools.check_plan.invoke({"slug": "qingning-release-plan-offline"}))
        assert final_check["ok"]
        evidence = {
            "mode": "scripted",
            "working_model_calls": len(model.prompts),
            "memory_visible_in_new_thread": "format: 中文分节 Markdown" in model.prompts[0],
            "tool_calls": names,
            "todo_states": states,
            "check_plan": checker,
            "final_file_check": final_check,
            "artifact": "artifacts/qingning-release-plan-offline.md",
            "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "meaning": "预设模型回复；只证明 Agent 图、中间件、Skill 读取、记忆加载和工具链运行。",
        }
        evidence_path = agent.PROJECT_ROOT / "evidence/offline-release-plan.json"
        evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print("工具调用：", " → ".join(names))
        print("结构检查：", final_check)
        print("输出文件：", artifact)
        print("证据文件：", evidence_path)
        print("PASS：独立上线计划 Agent 的离线链路已完成。")


if __name__ == "__main__":
    main()
