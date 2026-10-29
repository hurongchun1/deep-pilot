"""实验 2：真实 edit_file 写入 Store，新线程重新加载偏好。"""

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from _support import ScriptedModel, UserContext, call, content, done, invoke, seed, tools


def main():
    # memory= 不会创建缺失文件，先向 alice 的 Store namespace 放入初始偏好。
    store = InMemoryStore()
    seed(store, "alice", "# 偏好\n语言：待设置\n")
    # 第一轮模型提出 edit_file；第二轮结束写入对话；第三轮是全新线程。
    model = ScriptedModel(replies=[
        call("edit_file", {
            "file_path": "/memories/preferences.md",
            "old_string": "语言：待设置",
            "new_string": "语言：中文",
        }, "edit-memory"),
        done(),
        done(),
    ])
    # 记忆路径经过 CompositeBackend 路由，底层 Store key 是 /preferences.md。
    agent = create_deep_agent(
        model=model,
        store=store,
        checkpointer=InMemorySaver(),
        context_schema=UserContext,
        backend=CompositeBackend(
            default=StateBackend(),
            routes={"/memories/": StoreBackend(namespace=lambda rt: (rt.context.user_id, "memories"))},
        ),
        memory=["/memories/preferences.md"],
        system_prompt="仅在明确要求记住偏好时，先读取并用 edit_file 更新 /memories/preferences.md；写入成功后再确认。",
    )
    written = invoke(agent, "write-thread", "alice")
    # 同时检查工具成功、Store 内容和新线程模型请求，避免“口头说已记住”误判。
    assert any(m.tool_call_id == "edit-memory" and m.status != "error" for m in tools(written))
    assert "语言：中文" in content(store, "alice")
    invoke(agent, "read-thread", "alice")
    assert "语言：中文" in model.prompts[-1]
    assert "语言：待设置" not in model.prompts[-1]
    assert "运行记忆实验：write-thread" not in model.prompts[-1]
    print("PASS 2: store write and fresh-thread reload")


if __name__ == "__main__":
    main()
