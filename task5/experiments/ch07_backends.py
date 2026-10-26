"""离线验证 State/Store/Composite 后端与按角色选择 Skill 来源。

在 task5 目录运行：uv run --frozen python experiments/ch07_backends.py
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from _scripted import ScriptedModel, skill_file
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend, StoreBackend
from deepagents.backends.utils import create_file_data
from langchain_core.messages import AIMessage
from langgraph.store.memory import InMemoryStore


def done_model(count: int = 1) -> ScriptedModel:
    return ScriptedModel(replies=[AIMessage(content="完成") for _ in range(count)])


def state_backend_case() -> None:
    model = done_model()
    graph = create_deep_agent(model=model, backend=StateBackend(), skills=["/skills/"])
    graph.invoke(
        {
            "messages": [{"role": "user", "content": "列出可用 Skill"}],
            "files": {
                "/skills/state-guide/SKILL.md": create_file_data(
                    skill_file("state-guide", "STATE_MARKER：仅在本次输入的 state 中注入")
                )
            },
        }
    )
    assert "STATE_MARKER" in model.prompts[0]
    print("StateBackend：通过 files + create_file_data 注入 Skill，单次调用成功。")


def store_backend_case() -> None:
    store = InMemoryStore()
    store.put(
        namespace=("skills", "shared"),
        key="/skills/store-guide/SKILL.md",
        value=create_file_data(skill_file("store-guide", "STORE_MARKER：跨线程共享")),
    )
    model = done_model(2)
    graph = create_deep_agent(
        model=model,
        backend=StoreBackend(namespace=lambda _rt: ("skills", "shared")),
        skills=["/skills/"],
        store=store,
    )
    for thread in ("store-a", "store-b"):
        graph.invoke(
            {"messages": [{"role": "user", "content": "列出可用 Skill"}]},
            config={"configurable": {"thread_id": thread}},
        )
    assert all("STORE_MARKER" in prompt for prompt in model.prompts)
    print("StoreBackend：预填一次 Store，两个线程都发现同一 Skill。")


@dataclass(frozen=True)
class TenantContext:
    org_id: str


def composite_tenant_case() -> None:
    store = InMemoryStore()
    for org, marker in (("team-a", "TEAM_A_MARKER"), ("team-b", "TEAM_B_MARKER")):
        store.put(
            namespace=("tenant-skills", org),
            # /skills/ 是 CompositeBackend 的路由前缀，Store key 使用相对路径。
            key="/tenant-guide/SKILL.md",
            value=create_file_data(skill_file("tenant-guide", marker)),
        )
    model = done_model(2)
    graph = create_deep_agent(
        model=model,
        context_schema=TenantContext,
        backend=CompositeBackend(
            default=StateBackend(),
            routes={
                "/skills/": StoreBackend(namespace=lambda rt: ("tenant-skills", rt.context.org_id))
            },
        ),
        skills=["/skills/"],
        store=store,
    )
    for org in ("team-a", "team-b"):
        graph.invoke(
            {"messages": [{"role": "user", "content": "列出可用 Skill"}]},
            context=TenantContext(org_id=org),
        )
    assert "TEAM_A_MARKER" in model.prompts[0] and "TEAM_B_MARKER" not in model.prompts[0]
    assert "TEAM_B_MARKER" in model.prompts[1] and "TEAM_A_MARKER" not in model.prompts[1]
    print("CompositeBackend：同一路由按组织 namespace 隔离 Skill。")


def role_sources_case() -> None:
    with TemporaryDirectory(prefix="ch07-roles-") as directory:
        root = Path(directory)
        for role, skill, marker in (
            ("engineering", "code-review", "ENGINEERING_MARKER"),
            ("data", "data-analysis", "DATA_MARKER"),
        ):
            path = root / "skills" / role / skill / "SKILL.md"
            path.parent.mkdir(parents=True)
            path.write_text(skill_file(skill, marker), encoding="utf-8")

        sources_by_role = {
            "engineering": ["/skills/engineering/"],
            "data": ["/skills/data/"],
        }
        prompts = {}
        for role, sources in sources_by_role.items():
            model = done_model()
            graph = create_deep_agent(
                model=model,
                backend=FilesystemBackend(root_dir=root, virtual_mode=True),
                skills=sources,
            )
            graph.invoke({"messages": [{"role": "user", "content": "列出可用 Skill"}]})
            prompts[role] = model.prompts[0]
        assert "ENGINEERING_MARKER" in prompts["engineering"]
        assert "DATA_MARKER" not in prompts["engineering"]
        assert "DATA_MARKER" in prompts["data"]
        assert "ENGINEERING_MARKER" not in prompts["data"]
        print("按角色加载：工程师与数据角色各只发现自己的 Skill。")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    state_backend_case()
    store_backend_case()
    composite_tenant_case()
    role_sources_case()
    print("PASS：Skill 存储、路由与动态来源实验通过。")
