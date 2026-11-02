import json
import runpy
import shutil
import sys
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

import agent
import tools
from sample_plan import SCENARIOS, sample_plan
from scripted_model import ScriptedModel, call, planning_model


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


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_planning_across_new_sessions_without_sources(workspace, scenario):
    writer = ScriptedModel(replies=[
        call("save_preference", {"key": "format", "value": "中文分节 Markdown"}, "remember"),
        AIMessage(content="已保存格式偏好。"),
    ])
    agent.build_graph(writer, root=workspace).invoke(
        {"messages": [{"role": "user", "content": "请记住：以后写行动计划用中文分节 Markdown。"}]},
    )
    model = planning_model(scenario)
    graph = agent.build_graph(model, root=workspace, checkpointer=InMemorySaver())
    snapshots = list(graph.stream(
        {"messages": [{"role": "user", "content": SCENARIOS[scenario]["request"]}]},
        {"configurable": {"thread_id": scenario}}, stream_mode="values",
    ))
    final = snapshots[-1]
    messages = {m.tool_call_id: m for m in final["messages"] if m.type == "tool"}
    assert "format: 中文分节 Markdown" in model.prompts[0]
    assert "请记住：以后" not in model.prompts[0]
    assert "task-planning" in model.prompts[0]
    assert "行动计划结构" in messages["outline"].text
    assert all(m.status != "error" for m in messages.values())
    assert json.loads(messages["check"].text)["ok"] is True
    assert (workspace / f"artifacts/{scenario}.md").read_text(encoding="utf-8") == sample_plan(scenario)
    assert final["todos"][0]["status"] == "completed"
    assert not any(m.name == "read_source" for m in messages.values())


def test_optional_source_discovery_and_reading(workspace):
    (workspace / "sources/new-task.md").write_text("本周只有 3 小时。", encoding="utf-8")
    model = ScriptedModel(replies=[
        call("list_sources", {}, "list"),
        call("read_source", {"name": "new-task.md"}, "source"),
        AIMessage(content="补充资料中说明本周只有 3 小时。"),
    ])
    final = agent.build_graph(model, root=workspace).invoke(
        {"messages": [{"role": "user", "content": "请读取 new-task.md 的限制。"}]},
    )
    results = {m.tool_call_id: m for m in final["messages"] if m.type == "tool"}
    assert "new-task.md" in json.loads(results["list"].text)
    assert results["source"].text == "本周只有 3 小时。"


def test_checker_rejects_missing_and_empty_sections(workspace):
    tools.save_plan.invoke({"slug": "incomplete", "content": "# 标题\n\n## 任务目标\n\n## 已知条件\n两周。"})
    result = json.loads(tools.check_plan.invoke({"slug": "incomplete"}))
    assert result["ok"] is False
    assert "风险与调整" in result["missing"]
    assert "任务目标" in result["empty"]


def test_checker_accepts_body_under_subheadings(workspace):
    plan = sample_plan("learning").replace("## 行动步骤\n", "## 行动步骤\n### 第一阶段\n")
    tools.save_plan.invoke({"slug": "nested", "content": plan})
    assert json.loads(tools.check_plan.invoke({"slug": "nested"}))["ok"] is True


@pytest.mark.parametrize("complete", [True, False])
def test_live_entry_with_scripted_model_preserves_evidence(workspace, monkeypatch, complete):
    # 验证真实模型入口的编排和失败取证，不发送网络请求。
    class LiveScriptedModel(ScriptedModel):
        model_name: str = "scripted-entry-test"

    replies = [
        call("save_preference", {"key": "format", "value": "中文分节 Markdown"}, "remember"),
        AIMessage(content="已保存偏好。"),
    ]
    replies += planning_model("event").replies if complete else [AIMessage(content="未生成计划。")]
    model = LiveScriptedModel(replies=replies)
    original_build = agent.build_graph
    monkeypatch.setattr(agent, "PROJECT_ROOT", workspace)
    monkeypatch.setattr(agent, "build_model", lambda: model)
    monkeypatch.setattr(agent, "build_graph", lambda model, **kwargs: original_build(model, root=workspace, **kwargs))
    monkeypatch.setattr(sys, "argv", ["live_demo.py", "--task", SCENARIOS["event"]["request"], "--slug", "event"])
    main = runpy.run_path(str(Path(__file__).parents[1] / "experiments/live_demo.py"))["main"]
    if complete:
        main()
    else:
        with pytest.raises(RuntimeError, match="未覆盖全部必需步骤"):
            main()
    paths = list((workspace / "evidence").glob("planner-live-*.json"))
    assert len(paths) == 1
    evidence = json.loads(paths[0].read_text(encoding="utf-8"))
    assert evidence["request"] == SCENARIOS["event"]["request"]
    assert evidence["memory_visible_in_new_thread"] is True
    assert bool(evidence["error"]) is not complete
    assert bool(evidence["artifact_sha256"]) is complete


def test_invalid_preference_does_not_write(workspace):
    original = (workspace / "memory/preferences.md").read_text(encoding="utf-8")
    feedback = tools.save_preference.invoke({"key": "目标", "value": "学 Python"})
    assert "language、tone 或 format" in feedback
    assert (workspace / "memory/preferences.md").read_text(encoding="utf-8") == original


@pytest.mark.parametrize("slug", ["../escape", "/tmp/escape", "a/b", ""])
def test_plan_slug_stays_inside_workspace(workspace, slug):
    with pytest.raises(ValueError):
        tools.save_plan.invoke({"slug": slug, "content": "bad"})


@pytest.mark.parametrize("name", ["../AGENTS.md", "..\\AGENTS.md", "/tmp/escape.md", "note.txt"])
def test_source_path_stays_inside_sources(workspace, name):
    with pytest.raises(ValueError):
        tools.read_source.invoke({"name": name})
