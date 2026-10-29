"""实验 1：同线程恢复 State 文件，新线程只共享 Store 记忆。"""

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from _support import ScriptedModel, UserContext, call, done, invoke, seed, tools


def main():
    # 共享同一个 Store：alice 的持久记忆可供多个线程读取。
    store = InMemoryStore()
    seed(store, "alice", "# 偏好\n语言：中文\n")
    # 六条回复对应三次 invoke：线程 A 写文件、线程 B 读、线程 A 恢复后读。
    model = ScriptedModel(replies=[
        call("write_file", {"file_path": "/workspace/draft.txt", "content": "THREAD_ONLY_MARKER"}, "write-draft"),
        done(),
        call("read_file", {"file_path": "/workspace/draft.txt"}, "new-thread-read"),
        done(),
        call("read_file", {"file_path": "/workspace/draft.txt"}, "old-thread-read"),
        done(),
    ])
    # 直接创建 Agent。普通路径走 StateBackend；/memories/ 路由到 StoreBackend。
    agent = create_deep_agent(
        model=model,
        store=store,
        checkpointer=InMemorySaver(),  # 回到 thread-a 时恢复该线程的文件状态
        context_schema=UserContext,
        backend=CompositeBackend(
            default=StateBackend(),
            routes={"/memories/": StoreBackend(namespace=lambda rt: (rt.context.user_id, "memories"))},
        ),
        memory=["/memories/preferences.md"],  # 每个新线程加载该用户已有的偏好
    )
    # thread-b 是全新线程；第三次调用复用 thread-a，故能恢复之前的草稿。
    first = invoke(agent, "thread-a", "alice")
    fresh = invoke(agent, "thread-b", "alice")
    resumed = invoke(agent, "thread-a", "alice")

    # 分别检查真实工具结果，并确认新线程的模型请求确实包含 Store 记忆。
    assert any(m.tool_call_id == "write-draft" and m.status != "error" for m in tools(first))
    assert any(m.tool_call_id == "new-thread-read" and m.status == "error" for m in tools(fresh))
    assert any(m.tool_call_id == "old-thread-read" and "THREAD_ONLY_MARKER" in str(m.content) for m in tools(resumed))
    assert "语言：中文" in model.prompts[2]  # 新线程仍加载同一用户的 Store 记忆
    print("PASS 1: thread state and cross-thread store")


if __name__ == "__main__":
    main()
