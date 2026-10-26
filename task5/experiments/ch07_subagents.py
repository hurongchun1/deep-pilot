"""离线检查通用与自定义子 Agent 收到的 Skills 列表。

在 task5 目录运行：uv run --frozen python experiments/ch07_subagents.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from _scripted import ScriptedModel, skill_file
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_core.messages import AIMessage


def delegate(subagent_type: str) -> ScriptedModel:
    return ScriptedModel(
        replies=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {
                            "description": "列出你能发现的 Skill，简短回答。",
                            "subagent_type": subagent_type,
                        },
                        "id": "delegate-1",
                    }
                ],
            ),
            AIMessage(content="子 Agent 完成"),
            AIMessage(content="主 Agent 完成"),
        ]
    )


def run_case(root: Path, subagent_type: str, subagents=None) -> list[str]:
    model = delegate(subagent_type)
    graph = create_deep_agent(
        model=model,
        backend=FilesystemBackend(root_dir=root, virtual_mode=True),
        skills=["/skills/main/"],
        subagents=subagents,
    )
    graph.invoke(
        {"messages": [{"role": "user", "content": "请子 Agent 列出 Skill。"}]},
        config={"recursion_limit": 15},
    )
    assert len(model.prompts) == 3, f"预期主→子→主三次模型请求，实际为 {len(model.prompts)}"
    return model.prompts


def main() -> None:
    with TemporaryDirectory(prefix="ch07-subagents-") as directory:
        root = Path(directory)
        for group, name, marker in (
            ("main", "main-guide", "MAIN_SKILL_MARKER"),
            ("custom", "custom-guide", "CUSTOM_SKILL_MARKER"),
        ):
            path = root / "skills" / group / name / "SKILL.md"
            path.parent.mkdir(parents=True)
            path.write_text(skill_file(name, marker), encoding="utf-8")

        gp = run_case(root, "general-purpose")
        assert "MAIN_SKILL_MARKER" in gp[0] and "MAIN_SKILL_MARKER" in gp[1]
        print("通用子 Agent：继承主 Agent 的 Skill 列表。")

        custom = {"name": "reviewer", "description": "检查 Skill 可见性", "system_prompt": "完成指定检查。"}
        no_skills = run_case(root, "reviewer", subagents=[custom])
        assert "MAIN_SKILL_MARKER" in no_skills[0]
        assert "MAIN_SKILL_MARKER" not in no_skills[1]
        print("自定义子 Agent：未声明 skills 时不继承主 Agent Skill。")

        custom_with_skills = {**custom, "skills": ["/skills/custom/"]}
        own_skills = run_case(root, "reviewer", subagents=[custom_with_skills])
        assert "MAIN_SKILL_MARKER" not in own_skills[1]
        assert "CUSTOM_SKILL_MARKER" in own_skills[1]
        print("自定义子 Agent：显式声明后只发现自己的 Skill。")
    print("PASS：子 Agent 的 Skill 继承与显式配置实验通过。")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
