"""无密钥运行三个任务规划案例；模型回复预设，图和工具真实执行。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langsmith import tracing_context

os.environ["OPENAI_API_KEY"] = "unused-offline-key"
os.environ["LANGSMITH_TRACING"] = "false"

import agent  # noqa: E402
import tools  # noqa: E402
from sample_plan import SCENARIOS, sample_plan  # noqa: E402
from scripted_model import ScriptedModel, call, planning_model  # noqa: E402


def prepare_workspace(root: Path) -> None:
    for relative in ("AGENTS.md", "memory/preferences.md"):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((agent.PROJECT_ROOT / relative).read_text(encoding="utf-8"), encoding="utf-8")
    shutil.copytree(agent.PROJECT_ROOT / "sources", root / "sources")
    shutil.copytree(agent.PROJECT_ROOT / "skills", root / "skills")


def run_scenario(scenario: str) -> dict:
    with tracing_context(enabled=False), TemporaryDirectory(prefix="task-planner-") as folder:
        root = Path(folder)
        prepare_workspace(root)
        old_root = tools.PROJECT_ROOT
        tools.PROJECT_ROOT = root
        try:
            writer = ScriptedModel(replies=[
                call("save_preference", {"key": "format", "value": "中文分节 Markdown"}, "remember"),
                AIMessage(content="已保存格式偏好。"),
            ])
            agent.build_graph(writer, root=root).invoke(
                {"messages": [{"role": "user", "content": "请记住：以后写行动计划用中文分节 Markdown。"}]},
            )
            model = planning_model(scenario)
            graph = agent.build_graph(model, root=root, checkpointer=InMemorySaver())
            snapshots = list(graph.stream(
                {"messages": [{"role": "user", "content": SCENARIOS[scenario]["request"]}]},
                {"configurable": {"thread_id": scenario}}, stream_mode="values",
            ))
            final = snapshots[-1]
            calls = [item for message in final["messages"] if isinstance(message, AIMessage)
                     for item in message.tool_calls]
            results = {m.tool_call_id: m for m in final["messages"] if m.type == "tool"}
            checker = json.loads(results["check"].text)
            assert checker["ok"] and results["readback"].text == sample_plan(scenario)
            assert all(message.status != "error" for message in results.values())
            assert "format: 中文分节 Markdown" in model.prompts[0]
            assert final["todos"][0]["status"] == "completed"
            artifact = agent.PROJECT_ROOT / f"artifacts/{scenario}-plan-offline.md"
            artifact.parent.mkdir(exist_ok=True)
            shutil.copyfile(root / f"artifacts/{scenario}.md", artifact)
            states = []
            for snapshot in snapshots:
                state = [todo["status"] for todo in snapshot.get("todos") or []]
                if state and (not states or state != states[-1]):
                    states.append(state)
        finally:
            tools.PROJECT_ROOT = old_root
        final_check = json.loads(tools.check_plan.invoke({"slug": f"{scenario}-plan-offline"}))
        assert final_check["ok"]
        evidence = {
            "mode": "scripted", "scenario": scenario, "request": SCENARIOS[scenario]["request"],
            "memory_visible_in_new_thread": "format: 中文分节 Markdown" in model.prompts[0],
            "tool_calls": [item["name"] for item in calls], "todo_states": states,
            "check_plan": checker, "final_file_check": final_check,
            "artifact": f"artifacts/{artifact.name}",
            "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "meaning": "预设模型回复；只验证图、中间件、Skill、跨会话偏好和文件工具，不证明真实模型规划能力。",
        }
        path = agent.PROJECT_ROOT / f"evidence/offline-{scenario}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"PASS {scenario}：{artifact}；结构检查 {final_check['ok']}")
        return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=[*SCENARIOS, "all"], default="all")
    args = parser.parse_args()
    for scenario in SCENARIOS if args.scenario == "all" else [args.scenario]:
        run_scenario(scenario)


if __name__ == "__main__":
    main()
