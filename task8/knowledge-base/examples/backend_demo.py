"""Deep Agents Backend 实践。默认运行无需模型的五项实验；权限实验单独请求真实模型。"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import NotRequired

from deepagents import FilesystemPermission, create_deep_agent
from deepagents.backends import (
    CompositeBackend, FilesystemBackend, LocalShellBackend, StateBackend, StoreBackend,
)
from deepagents.middleware.filesystem import FilesystemState
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore


class FileOperationState(FilesystemState):
    action: str
    path: str
    content: str
    observation: NotRequired[str]
    operation_error: NotRequired[str | None]


def file_graph(backend, *, checkpointer=None):
    """直接运行文件节点，使用真实图状态，不使用模型或预设模型回复。"""
    def operate(state: FileOperationState):
        if state["action"] == "write":
            result = backend.write(state["path"], state["content"])
            observation = result.error or f"已写入 {result.path}"
        else:
            result = backend.read(state["path"])
            observation = result.error or str(result.file_data)
        return {"observation": observation, "operation_error": result.error}

    builder = StateGraph(FileOperationState)
    builder.add_node("operate", operate)
    builder.add_edge(START, "operate")
    builder.add_edge("operate", END)
    return builder.compile(checkpointer=checkpointer)


def operation(graph, thread: str, action: str, path: str, content: str = ""):
    result = graph.invoke(
        {"action": action, "path": path, "content": content},
        {"configurable": {"thread_id": thread}},
    )
    print(f"thread={thread} {action} {path}: {result['observation']}")
    return result


def filesystem_demo(root: Path):
    backend = FilesystemBackend(root_dir=root, virtual_mode=True)
    assert backend.write("/notes.md", "虚拟路径映射到本地文件。\n").error is None
    print("真实文件：", root / "notes.md")
    print("实际内容：", (root / "notes.md").read_text(encoding="utf-8"))
    print("backend 读回：", backend.read("/notes.md"))
    try:
        backend.read("/../outside.md")
    except ValueError as exc:
        print("越界路径被拒绝：", exc)
    else:
        raise AssertionError("预期越界路径被拒绝")

    # 用另一临时目录演示 virtual_mode=False，不触碰系统或项目文件。
    with TemporaryDirectory(prefix="backend-outside-") as folder:
        outside = Path(folder) / "external.md"
        outside.write_text("位于 root_dir 外的实验文件。", encoding="utf-8")
        unrestricted = FilesystemBackend(root_dir=root, virtual_mode=False)
        result = unrestricted.read(str(outside))
        assert result.error is None
        print("关闭虚拟模式后，可按真实绝对路径读取根目录外文件：", result)


def shell_demo(root: Path):
    backend = LocalShellBackend(
        root_dir=root, virtual_mode=True, timeout=10,
        max_output_bytes=2000, inherit_env=False,
    )
    # 仅运行 shell 内置的工作目录查询，不启动后台进程或更改文件。
    result = backend.execute("cd" if os.name == "nt" else "pwd")
    print("输出：", result.output.strip())
    print("退出码：", result.exit_code, "截断：", result.truncated)
    assert result.exit_code == 0


def state_demo(root: Path):
    graph = file_graph(StateBackend(), checkpointer=InMemorySaver())
    written = operation(graph, "a", "write", "/draft.md", "只属于会话 a。")
    assert "/draft.md" in written["files"]
    assert operation(graph, "a", "read", "/draft.md")["operation_error"] is None
    assert operation(graph, "b", "read", "/draft.md")["operation_error"] is not None
    print("文件没有落到本地目录：", not (root / "draft.md").exists())

    uncheckpointed = file_graph(StateBackend())
    operation(uncheckpointed, "a", "write", "/draft.md", "没有配置快照保存。")
    assert operation(uncheckpointed, "a", "read", "/draft.md")["operation_error"] is not None
    print("无 checkpointer 时仍可运行，但单独的后续调用不会仅凭同名 thread_id 恢复文件。")


def store_demo(root: Path):
    store = InMemoryStore()
    backend = StoreBackend(store=store, namespace=lambda _runtime: ("user-a", "files"))
    graph = file_graph(backend, checkpointer=InMemorySaver())
    operation(graph, "a", "write", "/profile.md", "语言：中文。")
    assert operation(graph, "b", "read", "/profile.md")["operation_error"] is None

    other_user = StoreBackend(store=store, namespace=lambda _runtime: ("user-b", "files"))
    assert other_user.read("/profile.md").error is not None
    print("相同 store、不同 namespace：文件隔离。")

    fresh_store = StoreBackend(
        store=InMemoryStore(), namespace=lambda _runtime: ("user-a", "files"),
    )
    assert fresh_store.read("/profile.md").error is not None
    print("换成新的内存 store 后文件不存在；跨 thread 共享不等于重启后持久化。")


def composite_demo(root: Path):
    shared = StoreBackend(store=InMemoryStore(), namespace=lambda _runtime: ("shared",))
    local = FilesystemBackend(root_dir=root / "project", virtual_mode=True)
    reports = FilesystemBackend(root_dir=root / "reports", virtual_mode=True)
    backend = CompositeBackend(
        default=StateBackend(),
        routes={"/shared/": shared, "/workspace/": local, "/workspace/reports/": reports},
    )
    graph = file_graph(backend, checkpointer=InMemorySaver())
    for path in ("/draft.md", "/shared/profile.md", "/workspace/readme.md", "/workspace/reports/daily.md"):
        assert operation(graph, "a", "write", path, f"内容来自 {path}")["operation_error"] is None
    assert operation(graph, "b", "read", "/draft.md")["operation_error"] is not None
    assert operation(graph, "b", "read", "/shared/profile.md")["operation_error"] is None
    assert shared.read("/profile.md").error is None
    assert (root / "project/readme.md").is_file()
    assert (root / "reports/daily.md").is_file()
    assert not (root / "project/reports/daily.md").exists()
    print("较长的 /workspace/reports/ 路由优先；前缀剥离后写入 reports/daily.md。")


def permission_rules():
    return [
        FilesystemPermission(operations=["read"], paths=["/docs/**", "/artifacts/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/artifacts/**"], mode="allow"),
        FilesystemPermission(operations=["read", "write"], paths=["/**"], mode="deny"),
    ]


def permissions_demo(root: Path, env_file: str | None):
    # 仅此实验调用真实模型；没有为模型设置预设回复或工具调用剧本。
    from dotenv import load_dotenv
    from langchain_openai import ChatOpenAI

    if env_file:
        load_dotenv(env_file, override=False)
    key = os.getenv("OPENAI_API_KEY", "").strip()
    model_name = os.getenv("MODEL_NAME") or os.getenv("AGENTSEEK_MODEL")
    if not key or not model_name:
        raise ValueError("请配置 OPENAI_API_KEY 和 MODEL_NAME（兼容 AGENTSEEK_MODEL）。")
    model = ChatOpenAI(
        model=model_name, api_key=key,
        base_url=os.getenv("OPENAI_API_BASE") or None,
    )
    (root / "docs").mkdir()
    source = root / "docs/guide.md"
    source.write_text("这是一份只读的示例资料。", encoding="utf-8")
    backend = FilesystemBackend(root_dir=root, virtual_mode=True)
    agent = create_deep_agent(
        model=model, backend=backend, permissions=permission_rules(),
        system_prompt="按请求使用内置文件工具。工具拒绝后记录原因，不使用其他方式绕过。",
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": (
            "依次实践：读取 /docs/guide.md；尝试 write_file 创建 /docs/new.md；"
            "即使写入被拒绝，也继续 write_file 创建 /artifacts/result.md，"
            "记录观察到的结果。最后说明哪些操作成功，哪些被拒绝。"
        )}]},
        {"recursion_limit": 40},
    )
    for message in result["messages"]:
        message.pretty_print()
    print("原资料内容：", source.read_text(encoding="utf-8"))
    print("被禁止的文件是否存在：", (root / "docs/new.md").exists())
    print("允许的产物是否存在：", (root / "artifacts/result.md").exists())
    print("需核对工具请求及结果；模型未尝试某项操作时，不算验证了该项权限。")


DEMOS = {
    "filesystem": filesystem_demo, "shell": shell_demo, "state": state_demo,
    "store": store_demo, "composite": composite_demo,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", choices=[*DEMOS, "permissions", "all"], default="all")
    parser.add_argument("--env-file", help="权限实验的模型配置文件；其他实验不读取该文件")
    args = parser.parse_args()
    names = list(DEMOS) if args.demo == "all" else [args.demo]
    for name in names:
        print(f"\n=== {name} ===")
        with TemporaryDirectory(prefix=f"backend-{name}-") as folder:
            root = Path(folder).resolve()
            if name == "permissions":
                permissions_demo(root, args.env_file)
            else:
                DEMOS[name](root)
        print("临时目录已清理。")


if __name__ == "__main__":
    main()
