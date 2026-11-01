import json
import shutil
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

import agent
import tools
from sample_plan import PLAN
from scripted_model import ScriptedModel, call


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = Path(agent.PROJECT_ROOT)
    for relative in ("AGENTS.md", "memory/preferences.md"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((root / relative).read_text(encoding="utf-8"), encoding="utf-8")
    shutil.copytree(root / "sources", tmp_path / "sources")
    shutil.copytree(root / "skills", tmp_path / "skills")
    monkeypatch.setattr(tools, "PROJECT_ROOT", tmp_path)
    return tmp_path


def test_release_plan_in_one_graph_across_two_threads(workspace):
    writer = ScriptedModel(replies=[
        call("save_preference", {"key": "format", "value": "中文分节 Markdown"}, "remember"),
        AIMessage(content="已保存格式偏好。"),
    ])
    graph = agent.build_graph(writer, root=workspace, checkpointer=InMemorySaver())
    first = graph.invoke(
        {"messages": [{"role": "user", "content": "请记住：以后写上线计划用中文分节 Markdown。"}]},
        {"configurable": {"thread_id": "remember"}},
    )
    assert "format: 中文分节 Markdown" in (workspace / "memory/preferences.md").read_text(encoding="utf-8")
    assert any(message.type == "tool" and message.tool_call_id == "remember"
               for message in first["messages"])

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
    graph = agent.build_graph(model, root=workspace, checkpointer=InMemorySaver())
    snapshots = list(graph.stream(
        {"messages": [{"role": "user", "content": "为青柠清单 v1.2 制定上线计划。"}]},
        {"configurable": {"thread_id": "release"}}, stream_mode="values",
    ))
    final = snapshots[-1]
    messages = {m.tool_call_id: m.content for m in final["messages"] if m.type == "tool"}
    assert "format: 中文分节 Markdown" in model.prompts[0]
    assert "请记住：以后" not in model.prompts[0]
    assert "release-plan" in model.prompts[0]
    assert {"write_todos", "read_file", "read_source", "save_plan", "read_plan",
            "check_plan", "save_preference"} <= set(model.seen_tools)
    assert "上线计划结构" in messages["outline"]
    assert "青柠清单 v1.2 产品简报" in messages["brief"]
    assert messages["readback"] == PLAN
    assert json.loads(messages["check"])["ok"] is True
    assert (workspace / "artifacts/qingning-release-plan.md").read_text(encoding="utf-8") == PLAN
    statuses = [s["todos"][0]["status"] for s in snapshots if s.get("todos")]
    assert "in_progress" in statuses and statuses[-1] == "completed"


def test_checker_rejects_missing_sections_and_sources(workspace):
    tools.save_plan.invoke({"slug": "incomplete", "content": "# 只有标题"})
    result = json.loads(tools.check_plan.invoke({"slug": "incomplete"}))
    assert result["ok"] is False
    assert "回滚预案" in result["missing"]
    assert "sources/product-brief.md" in result["missing"]


def test_checker_rejects_missing_rollout_stage(workspace):
    tools.save_plan.invoke({"slug": "missing-stage", "content": PLAN.replace("50%", "半数")})
    result = json.loads(tools.check_plan.invoke({"slug": "missing-stage"}))
    assert result["ok"] is False
    assert "50%" in result["missing"]


def test_invalid_preference_key_returns_feedback_without_writing(workspace):
    original = (workspace / "memory/preferences.md").read_text(encoding="utf-8")
    feedback = tools.save_preference.invoke({"key": "语言", "value": "中文"})
    assert "language、tone 或 format" in feedback
    assert (workspace / "memory/preferences.md").read_text(encoding="utf-8") == original


@pytest.mark.parametrize("slug", ["../escape", "/tmp/escape", "a/b", ""])
def test_plan_slug_does_not_escape_project(workspace, slug):
    with pytest.raises(ValueError):
        tools.save_plan.invoke({"slug": slug, "content": "bad"})
