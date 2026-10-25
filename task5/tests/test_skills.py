"""Chapter 7 checks against the real Deep Agents graph and filesystem backend."""

import subprocess
import sys
from pathlib import Path

from langchain_core.messages import AIMessage
from scripted_model import ScriptedModel

from task5 import agent


def test_skill_body_and_resources_are_loaded_on_demand():
    root = Path(__file__).resolve().parents[1]
    process = subprocess.run(
        [sys.executable, str(root / "experiments/ch07_progressive_disclosure.py")],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert process.returncode == 0, process.stderr
    assert "PASS" in process.stdout


def test_later_skill_source_overrides_earlier_one(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "EXAMPLE_DIR", tmp_path)
    (tmp_path / "memory").mkdir()
    (tmp_path / "AGENTS.md").write_text("# Test writer\n", encoding="utf-8")
    (tmp_path / "memory/preferences.md").write_text("# Preferences\n", encoding="utf-8")
    for source, description in (("shared", "SHARED_MARKER"), ("project", "PROJECT_MARKER")):
        path = tmp_path / "skill_sets" / source / "skill-guide" / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(
            f"---\nname: skill-guide\ndescription: {description}\n---\n\n# Guide\n",
            encoding="utf-8",
        )
    model = ScriptedModel(replies=[AIMessage(content="Done")])
    graph = agent.build_graph(
        model,
        skill_sources=["/skill_sets/shared/", "/skill_sets/project/"],
    )
    graph.invoke({"messages": [{"role": "user", "content": "Write a guide."}]})
    assert "PROJECT_MARKER" in model.prompts[0]
    assert "SHARED_MARKER" not in model.prompts[0]
