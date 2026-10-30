"""用预设模型验证 State/Store/Composite 后端与按角色选择 Skill 来源。

在 task5 目录运行：uv run --frozen python experiments/ch07_backends.py
按环境配置上传 LangSmith；--trace 强制开启，--no-trace 关闭。
预设模型不调用真实模型 API，开启追踪时仍会向 LangSmith 上传实验记录。
"""

from __future__ import annotations

import argparse
import os
import sys
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from _scripted import ScriptedModel, skill_file
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend, StoreBackend
from deepagents.backends.utils import create_file_data
from langchain.tools import ToolRuntime
from langchain_core.messages import AIMessage
from langchain_core.tracers.langchain import wait_for_all_tracers
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from dotenv import load_dotenv
from langsmith import Client, trace, tracing_context


def done_model(count: int = 1) -> ScriptedModel:
    return ScriptedModel(replies=[AIMessage(content="完成") for _ in range(count)])

"""
StateBackend 通过 files 把 Skill 放进 state，checkpointer 会按执行步骤持续保存状态快照。
后续使用同一个 thread_id 可以恢复 Skill，不用重复传 files；换一个线程则不会自动共享。

保存多久取决于实现：InMemorySaver 只保存在当前实例的内存中，进程退出后就丢失；
持久化 checkpointer 可以在重启后恢复，但仍受删除、过期和清理策略影响。

StoreBackend 从 Store 读取 Skill，示例用 store.put() 提前写入。
不同线程使用同一个 Store、访问相同 namespace，就能共用 Skill。
namespace 是程序选择的数据范围，权限仍需应用校验；Agent 在权限允许时也能写入 Store。
InMemoryStore 同样只保存在内存中，需要重启后保留内容时，应接入持久化 Store。
"""


# 这里的skill采用statebackend的存储方式
def state_backend_case() -> None:
    model = done_model()

    graph = create_deep_agent(
        model=model, 
        backend=StateBackend(), 
        skills=["/skills/"],
        # 执行过程中会继续保存包含 files 的状态快照，后续按同一个 thread_id 恢复。
        # InMemorySaver 只保存在这个实例的内存中，进程退出或换成空的新实例后就无法恢复旧数据。
        # 配置后，invoke 还需要传 config={"configurable": {"thread_id": "state-a"}}。
        checkpointer=InMemorySaver(),
    )
    input_state = {
        "messages": [{"role": "user", "content": "列出可用 Skill"}],
        "files": {
            "/skills/state-guide/SKILL.md": create_file_data(
                skill_file("state-guide", "STATE_MARKER")
            )
        },
    }

    _ = graph.invoke(
        input_state,   # pyright: ignore[reportArgumentType]
        # context：给 Agent的节点、工具或中间件提供本次运行需要的业务信息，例如当前用户是谁
        context = "",
        # config：告诉框架这次运行怎么管理，例如属于哪个 thread_id
        config={"configurable": {"thread_id": "state-a"}},
    )
    assert "STATE_MARKER" in model.prompts[0]
    print("StateBackend：通过 files + create_file_data 注入 Skill，单次调用成功。")

# 这里的skill采用storebackend的存储方式
def store_backend_case() -> None:
    store: InMemoryStore = InMemoryStore()

    store.put(
        # 先把 Skill 写进这个 namespace，下面的 StoreBackend 也要访问同一个范围。
        # 第一个填写的是管存什么，第二个管谁在用
        namespace=("skills", "shared"),
        key="/skills/store-guide/SKILL.md",
        value=create_file_data(skill_file("store-guide", "STORE_MARKER：跨线程共享")),
    )
    model = done_model(2)
    graph = create_deep_agent(
        model=model,
        # 这里设置了agent使用的namespace，刚好与store中put的namespace保持一致，这样由这个agent生成的线程就能共享Skill
        backend=StoreBackend(namespace=lambda _rt: ("skills", "shared")),
        skills=["/skills/"],
        store=store,
    )
    # 这里是通过两个互不相干的线程，且都不上传files，看他们能不能发现同一个Skill
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

# 用一个虚拟路径 /skills/，因为"当前是哪个组织在问"而落到不同的 store分区，于是team-a只见 A，team-b只见 B
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
        # 用这种混合型的backend
        backend=CompositeBackend(
            default=StateBackend(),
            routes={
                # 这里指定虚拟路径: /skills 使用 storebackend的方式存储
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

        # 这张是 [角色 -> 扫描哪些目录]的映射表
        sources_by_role = {
            "engineering": ["/skills/engineering/"],
            "data": ["/skills/data/"],
        }
        prompts = {}
        for role, sources in sources_by_role.items():
            model = done_model()
            # 建立agent
            graph = create_deep_agent(
                model=model,
                backend=FilesystemBackend(root_dir=root, virtual_mode=True),
                skills=sources,
            )
            # 这里是执行agent
            graph.invoke({"messages": [{"role": "user", "content": "列出可用 Skill"}]})
            prompts[role] = model.prompts[0]
        assert "ENGINEERING_MARKER" in prompts["engineering"]
        assert "DATA_MARKER" not in prompts["engineering"]
        assert "DATA_MARKER" in prompts["data"]
        assert "ENGINEERING_MARKER" not in prompts["data"]
        print("按角色加载：工程师与数据角色各只发现自己的 Skill。")


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
    cases = (state_backend_case, store_backend_case, composite_tenant_case, role_sources_case)
    try:
        with tracing_context(enabled=enabled, project_name=project, client=client):
            root_trace = trace(
                "ch07_backends", client=client, project_name=project,
                inputs={"script": "experiments/ch07_backends.py", "model": "ScriptedModel"},
                tags=["ch07", "backends", "scripted"],
            ) if enabled else nullcontext()
            with root_trace as run:
                for case in cases:
                    case_trace = trace(case.__name__, inputs={"case": case.__name__}) if enabled else nullcontext()
                    with case_trace:
                        case()
                if run is not None:
                    run.add_outputs({"status": "passed", "cases_passed": len(cases)})
        print("PASS：Skill 存储、路由与动态来源实验通过。")
        if client is not None:
            # 等待后台上传完成，再退出；不要用 timeout=0 丢弃待上传记录。
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
