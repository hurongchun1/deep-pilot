"""Deterministic chapter 3 lab using real DeepAgents tools and no API calls."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any, TypedDict

from deepagents import create_deep_agent
from deepagents.backends import (
    CompositeBackend,
    FilesystemBackend,
    LocalShellBackend,
    StateBackend,
    StoreBackend,
)
from deepagents.middleware.filesystem import FilesystemPermission
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from pydantic import PrivateAttr

# 实验输出目录
# Path(__file__) —— 获取当前 Python 文件的路径
# .resolve() ——转换成绝对路径并解析符号链接
# .parents[1] —— 获取上两级目录
# / "lab-output" / "ch03" —— 用 / 运算符拼接子路径
# 比如：当前目录为：d:/project/pythonProjects/deep-pilot/src/chapter3/lab.py
# 则最终输出内容：
# parents[1] = d:/project/pythonProjects/deep-pilot/src
# LAB_ROOT   = d:/project/pythonProjects/deep-pilot/src/lab-output/ch03
LAB_ROOT = Path(__file__).resolve().parents[1] / "lab-output" / "ch03"


class ScriptedModel(BaseChatModel):
    """Choose the next tool call in advance, while DeepAgents runs the real tool."""

    replies: list[AIMessage]
    _cursor: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "ch03-scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if self._cursor >= len(self.replies):
            raise RuntimeError("The scripted model ran out of replies")
        reply = self.replies[self._cursor]
        self._cursor += 1
        return ChatResult(generations=[ChatGeneration(message=reply)])


def call(name: str, args: dict, call_id: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def done() -> AIMessage:
    return AIMessage(content="实验完成")


def show_tools(result: dict, *, limit: int = 500, skip: int = 0) -> None:
    tool_messages = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    for message in tool_messages[skip:]:
            content = str(message.content)
            if len(content) > limit:
                content = content[:limit] + "... [display truncated]"
            print(f"\n[{message.name} | {message.status}]\n{content}")


def config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


class NamespaceContext(TypedDict):
    user_id: str
    assistant_id: str


def tools_lab() -> None:
    """Try all seven tools and compare the three grep output modes."""
    path = "/notes/plan.md"
    model = ScriptedModel(
        replies=[
            # Updated file /notes/plan.md
            call("write_file", {"file_path": path, "content": "alpha\nTODO first\nbeta\nTODO second\n"}, "write"),
            # ['/notes/plan.md']
            call("ls", {"path": "/notes"}, "ls"),
            # 2  TODO first
            # 3  beta
            # [Read 2 lines (lines 2-3 of 4 total). 1 line remaining from offset 3.] 这是分页读取说明读取两行内容，从第2行开始
            call("read_file", {"file_path": path, "offset": 1, "limit": 2}, "read"),
            # Successfully replaced 1 instance(s) of the string in '/notes/plan.md'
            call("edit_file", {"file_path": path, "old_string": "TODO first", "new_string": "DONE first"}, "edit"),
            # ['/notes/plan.md']
            call("glob", {"pattern": "*.md", "path": "/notes"}, "glob"),
            # grep 三种模式返回的差异：
            # files_with_matches: 只有文件名，省 token
            # content: 带行号的内容,用于精度
            # count: 次数,用于快速统计
            # /notes/plan.md
            call("grep", {"pattern": "TODO", "path": "/notes", "output_mode": "files_with_matches"}, "grep-files"),
            # /notes/plan.md:
            #   4: TODO second
            call("grep", {"pattern": "TODO", "path": "/notes", "output_mode": "content"}, "grep-content"),
            # /notes/plan.md: 1
            call("grep", {"pattern": "TODO", "path": "/notes", "output_mode": "count"}, "grep-count"),
            # Deleted /notes/plan.md
            call("delete", {"file_path": path}, "delete"),
            # Error: File '/notes/plan.md' not found
            call("read_file", {"file_path": path}, "read-deleted"),
            done(),
        ]
    )
    agent = create_deep_agent(model=model)
    result = agent.invoke({"messages": [{"role": "user", "content": "运行七个文件工具"}]})
    show_tools(result)
    print("\nStateBackend 最终 files 键：", list(result.get("files", {})))

# 演示 deep agent的状态（StateBackend）持久化与线程隔离
def state_lab() -> None:
    """Same thread can read files with a checkpointer; another thread cannot."""
    path = "/scratch/state.txt"
    # 这里相当于做一个定制化的模型调用
    # 首先写入文件A，所以文件A存在，那么读取文件A就会成功
    # 读取文件B失败，是因为文件B本来不存在所以失败
    model = ScriptedModel(
        replies=[
            # thread_id就是用户/会话隔离的实现基础
            # [write_file | success]
            # Updated file /scratch/state.txt
            # State 中的文件： ['/scratch/state.txt']
            call("write_file", {"file_path": path, "content": "仅属于 thread-A"}, "state-write"),
            done(),
            # [read_file | success]
            # 1  仅属于 thread-A
            # State 中的文件： ['/scratch/state.txt']
            call("read_file", {"file_path": path}, "state-read-A"),
            done(),
            # [read_file | error]
            # Error: File '/scratch/state.txt' not found
            # State 中的文件： []
            call("read_file", {"file_path": path}, "state-read-B"),
            done(),
        ]
    )
    agent = create_deep_agent(
        model=model, 
        # 这个就是默认的持久化方式，将文件存放到 State 状态中
        backend=StateBackend(), 
        # 这个是LangGraph 提供的检查点，作用是把每轮对话结束后的完整状态保存下来，让 agent 具备记忆
        # checkpointer=InMemorySaver()
        )
    prior_a_tools = 0
    # 相当于将所有操作都罗列出来，然后通过agent 运行得出结果，而agent的调用得到的结果在ScriptedModel 这个方法中固定了
    for label, thread_id in [("写入 A", "thread-A"), ("再次读取 A", "thread-A"), ("读取 B", "thread-B")]:
        result = agent.invoke({"messages": [{"role": "user", "content": label}]}, config(thread_id))
        print(f"\n=== {label} ===")
        show_tools(result, skip=prior_a_tools if thread_id == "thread-A" else 0)
        show_tools(result, skip=0) # skip=N,表示跳过前N条工具执行信息
        if thread_id == "thread-A":
            prior_a_tools = sum(isinstance(message, ToolMessage) for message in result["messages"])
        print("State 中的文件：", list(result.get("files", {})))

# CompositeBackend（组合后端）的路径路由
# 三种路由配置：
# 1./scratch/ 后端：StateBackend()，实际存储位置：agent状态里的files字典，特点：线程隔离，换线程就没了
# 2./workspace/ 后端：FilesystemBackend(root_dir,virtual_mode)，实际存储位置：本地磁盘，特点：跨线程，跨会话持久，真的写文件
# 3./memories/ 后端：StoreBackend(namespace)，实际存储位置：InMemoryStore，特点：跨线程共享的长期记忆库
def routing_lab() -> None:
    """Route virtual paths to State, a local directory, and an in-memory Store."""
    LAB_ROOT.mkdir(parents=True, exist_ok=True)
    store = InMemoryStore()
    # 这里是自定义的后端,根据不同的路由,使用不同的后端存储
    backend = CompositeBackend(
        # 这里是默认使用StateBackend存储的方式
        default=StateBackend(),
        # 自定义路由
        routes={
            # 对于Lab_root 路径使用文件本地存储的方式
            # 其中 /workspace/ 是虚拟文件系统的路径，而对应文件中真实的路径主要看你的backend存放的位置
            "/workspace/": FilesystemBackend(root_dir=LAB_ROOT.resolve(), virtual_mode=True),
            # 对于 命名空间ch03,使用的是用户demo-user 的方式存储的,同一用户会话共享记忆
            "/memories/": StoreBackend(namespace=lambda _rt: ("ch03", "demo-user")),
        },
    )
    paths = ["/scratch/temp.txt", "/workspace/disk.txt", "/memories/preference.txt"]
    model = ScriptedModel(
        replies=[
            # [write_file | success]
            # Updated file /scratch/temp.txt
            call("write_file", {"file_path": paths[0], "content": "state only"}, "route-state"),
            # [write_file | success]
            # Updated file /workspace/disk.txt
            call("write_file", {"file_path": paths[1], "content": "real disk"}, "route-disk"),
            # [write_file | success]
            # Updated file /memories/preference.txt
            # Agent State 的 files 键： ['/scratch/temp.txt']
            # 本地磁盘文件： D:\project\pythonProjects\deep-pilot\task2\lab-output\ch03\disk.txt 存在： True
            # Store 的键： ['/preference.txt']
            call("write_file", {"file_path": paths[2], "content": "shared store"}, "route-store"),
            done(),
            # [read_file | error]
            # Error: File '/scratch/temp.txt' not found

            # [read_file | success]
            # 1  real disk

            # [read_file | success]
            # 1  shared store
            *(call("read_file", {"file_path": path}, f"read-{i}") for i, path in enumerate(paths)),
            done(),
        ]
    )
    agent = create_deep_agent(
        model=model,
        backend=backend,
        checkpointer=InMemorySaver(),
        store=store,
    )
    first = agent.invoke({"messages": [{"role": "user", "content": "写三个文件"}]}, config("route-A"))
    print("\n=== thread A 写入 ===")
    show_tools(first)
    print("Agent State 的 files 键：", list(first.get("files", {})))
    disk_file = LAB_ROOT / "disk.txt"
    print("本地磁盘文件：", disk_file, "存在：", disk_file.exists())
    print("Store 的键：", [item.key for item in store.search(("ch03", "demo-user"))])
    second = agent.invoke({"messages": [{"role": "user", "content": "读三个文件"}]}, config("route-B"))
    print("\n=== 新 thread B 读取 ===")
    show_tools(second)

# namespace 的三种隔离策略：边界划在哪，共享范围就在哪
# - 按用户隔离：记忆跟人走（多用户 SaaS 的标准做法）
# - 按线程隔离：记忆跟会话走（会话级记忆，换线程即失）
# - 按助手隔离：记忆跟 agent 实例走（同一用户的不同助手互不可见）
NAMESPACE_CONTENT = "alice + bot-1 的共享记忆"

# 每个策略一个场景表：(标签, user_id, assistant_id, thread_id, 期望状态, 期望内容片段)
# 通用验证矩阵：写入 -> "另一个维度主体"同路径读取(应隔离) -> 原主体回读(应完好) -> 原主体换线程(看该策略的边界)
NAMESPACE_SCENARIOS: dict[str, list[tuple[str, str, str, str, str, str | None]]] = {
    "按用户隔离": [
        ("alice 写入", "alice", "bot-1", "thread-1", "success", None),
        ("bob 同线程读取（用户不同 -> 隔离）", "bob", "bot-1", "thread-1", "error", "not found"),
        ("alice 同线程读取（数据未被污染）", "alice", "bot-1", "thread-1", "success", NAMESPACE_CONTENT),
        ("alice 换线程读取（记忆跟人走）", "alice", "bot-1", "thread-2", "success", NAMESPACE_CONTENT),
    ],
    "按线程隔离": [
        ("alice 写入", "alice", "bot-1", "thread-1", "success", None),
        ("alice 换线程读取（跨线程 -> 隔离）", "alice", "bot-1", "thread-2", "error", "not found"),
        ("alice 回原线程读取", "alice", "bot-1", "thread-1", "success", NAMESPACE_CONTENT),
        ("bob 同线程读取（换用户无效！）", "bob", "bot-1", "thread-1", "success", NAMESPACE_CONTENT),
    ],
    "按助手隔离": [
        ("alice + bot-1 写入", "alice", "bot-1", "thread-1", "success", None),
        ("alice + bot-2 同线程读取（助手不同 -> 隔离）", "alice", "bot-2", "thread-1", "error", "not found"),
        ("alice + bot-1 同线程读取（数据未被污染）", "alice", "bot-1", "thread-1", "success", NAMESPACE_CONTENT),
        ("alice + bot-1 换线程读取（记忆跟助手走）", "alice", "bot-1", "thread-2", "success", NAMESPACE_CONTENT),
    ],
}

NAMESPACE_FACTORIES: dict[str, Any] = {
    "按用户隔离": lambda rt: ("ch03", "users", rt.context["user_id"]),
    "按线程隔离": lambda rt: ("ch03", "threads", rt.execution_info.thread_id),
    "按助手隔离": lambda rt: ("ch03", "assistants", rt.context["assistant_id"]),
}


def namespace_lab() -> None:
    """Verify user/thread/assistant namespace isolation strategies."""
    path = "/memories/preference.txt"
    for label, steps in NAMESPACE_SCENARIOS.items():
        print(f"\n{'#' * 6} namespace 策略：{label} {'#' * 6}")
        _run_namespace_scenario(label, steps, NAMESPACE_FACTORIES[label], path)


def _run_namespace_scenario(
    label: str,
    steps: list[tuple[str, str, str, str, str, str | None]],
    namespace_factory: Any,
    path: str,
) -> None:
    store = InMemoryStore()
    # 第一步是写入，其余都是读取；按步骤数动态生成脚本
    replies: list[AIMessage] = []
    for index in range(len(steps)):
        if index == 0:
            replies.append(call("write_file", {"file_path": path, "content": NAMESPACE_CONTENT}, f"{label}-0"))
        else:
            replies.append(call("read_file", {"file_path": path}, f"{label}-{index}"))
        replies.append(done())
    model = ScriptedModel(replies=replies)
    agent = create_deep_agent(
        model=model,
        backend=StoreBackend(namespace=namespace_factory),
        context_schema=NamespaceContext,
        store=store,
        # 无 checkpointer 时 execution_info.thread_id 为 None，按线程隔离会失效
        checkpointer=InMemorySaver(),
    )

    for index, (step_label, user_id, assistant_id, thread_id, expected_status, expected_text) in enumerate(steps):
        result = agent.invoke(
            {"messages": [{"role": "user", "content": step_label}]},
            config(thread_id),
            context={"user_id": user_id, "assistant_id": assistant_id},
        )
        tool_message = next(m for m in reversed(result["messages"]) if isinstance(m, ToolMessage))
        ok = tool_message.status == expected_status and (
            expected_text is None or expected_text in str(tool_message.content)
        )
        mark = "[PASS]" if ok else "[FAIL]"
        preview = str(tool_message.content)[:300].replace("\n", " ")
        print(f"  {mark} {step_label}\n      user={user_id}, assistant={assistant_id}, thread={thread_id}"
              f"\n      期望[{expected_status}] 实际[{tool_message.status}] | {preview}")
        assert tool_message.status == expected_status, f"{step_label}: {tool_message.status} != {expected_status}"
        if expected_text is not None:
            assert expected_text in str(tool_message.content), f"{step_label}: 未找到 {expected_text!r}"

    seen = sorted({tuple(item.namespace) for item in store.search(("ch03",))})
    print(f"  Store 中实际存在的 namespace：{seen}")

# 故意返回一个巨型字符串
def large_result() -> str:
    """Return an intentionally large result to trigger automatic tool-result offload."""
    return "REPORT HEADER\n" + "".join(f"row {i:04d}: " + "x" * 90 + "\n" for i in range(1000))

# 演示deep agent 的工具结果自动卸载机制
def offload_lab() -> None:
    model = ScriptedModel(
        replies=[
            # 文件如果超过最大输出
            call("large_result", {}, "large"),
            # 将文件输入到 /large_tool_results/large 中
            call("read_file", {"file_path": "/large_tool_results/large", "offset": 999, "limit": 2}, "read-large-tail"),
            done(),
        ]
    )
    """
    Tool result too large, the result of this tool call large was saved in the filesystem at this path: /large_tool_results/large

You can read the result from the filesystem by using the read_file tool, but make sure to only read part of the result at a time.

You can do this by specifying an offset and limit in the read_file tool call. For example, to read the first 100 lines, you can use the read_file tool with offset=0 and limit=100.

Here is a preview showing the head and tail of the result (lines of the form `... [N lines truncated] ...` indicate omitted lines in the middle of the content):

1  REPORT HEADER
2  row 0000: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
3  row 0001: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
4  row 0002: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
5  row 0003: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
... [991 lines truncated] ...
 997  row 0995: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx       
 998  row 0996: xxxxxxxxxxxxx... [display truncated]

[read_file | success]
1000  row 0998: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx       
1001  row 0999: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx       

卸载文件：/large_tool_results/large；完整内容字符数：101014
    """
    agent = create_deep_agent(model=model, tools=[large_result])
    result = agent.invoke({"messages": [{"role": "user", "content": "获取大结果"}]})
    show_tools(result, limit=1200)
    files = result.get("files", {})
    for path, data in files.items():
        if path.startswith("/large_tool_results/"):
            print(f"\n卸载文件：{path}；完整内容字符数：{len(data['content'])}")

# 演示声明式 FilesystemPermission
def permission_lab() -> None:
    model = ScriptedModel(
        replies=[
            # call_id  他是工具调用的唯一标识符,对应 tool_calls里的id字段
            call("write_file", {"file_path": "/policies/rule.md", "content": "try"}, "denied"),
            call("write_file", {"file_path": "/scratch/allowed.md", "content": "ok"}, "allowed"),
            done(),
        ]
    )
    agent = create_deep_agent(
        model=model,
        # 路径禁止写入 /policies/下的文件
        permissions=[FilesystemPermission(operations=["write"], paths=["/policies/**"], mode="deny")],
    )
    result = agent.invoke({"messages": [{"role": "user", "content": "验证写入权限"}]})
    show_tools(result)
    print("\nState 中的文件：", list(result.get("files", {})))


# 这个lab的目的是让你在不冒任何执行风险的前提下，看清两种 backend的能力边界
# FilessystemBackend 只管文件
# LocalShellBackend 额外开放了Shell 执行能力,并提醒这份能力是无隔离的需要谨慎授权
def shell_lab() -> None:
    """Show the extra capability without running any host command."""
    fs = FilesystemBackend(root_dir=LAB_ROOT.resolve(), virtual_mode=True)
    shell = LocalShellBackend(root_dir=LAB_ROOT.resolve(), virtual_mode=True)
    print("FilesystemBackend 有 execute：", callable(getattr(fs, "execute", None)))
    print("LocalShellBackend 有 execute：", callable(getattr(shell, "execute", None)))
    print("LocalShellBackend 的文件 root_dir：", LAB_ROOT.resolve())
    print("execute 命令仍在 Windows 宿主机执行；virtual_mode 不隔离 Shell。")


LABS = {
    "tools": tools_lab,
    "state": state_lab,
    "routing": routing_lab,
    "namespace": namespace_lab,
    "offload": offload_lab,
    "permissions": permission_lab,
    "shell": shell_lab,
}


def main() -> None:
    # 你可以通过指定演示的内容
    # python ch03_lab.py tools 只跑工具演示
    # python ch03_lab.py state 只跑状态隔离演示
    # python ch03_lab.py all 全部依次跑
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lab", choices=[*LABS, "all"])
    args = parser.parse_args()
    for name in LABS if args.lab == "all" else [args.lab]:
        print(f"\n{'=' * 18} {name} {'=' * 18}")
        LABS[name]()

    # langchain-core 内部持有自己的 Client 和上传队列，此处 flush 不到；
    # 只能等待后台线程把 trace 发送完，否则短命进程的 trace 会随解释器关闭而丢失
    time.sleep(3)


if __name__ == "__main__":
    main()
