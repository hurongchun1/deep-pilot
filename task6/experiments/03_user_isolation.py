"""实验 3：两个用户共用 Store，但 namespace 隔离。"""

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langgraph.store.memory import InMemoryStore

from _support import ScriptedModel, UserContext, content, done, invoke, seed


def main():
    # A、B 共用同一个 InMemoryStore，但 namespace 中的 user_id 不同。
    store = InMemoryStore()
    seed(store, "alice", "# 偏好\nALICE_MARKER：中文\n")
    seed(store, "bob", "# 偏好\nBOB_MARKER：英文\n")
    model = ScriptedModel(replies=[done(), done(), done()])
    # 相同的虚拟路径会按当前 context.user_id 路由到不同的 Store 分区。
    agent = create_deep_agent(
        model=model,
        store=store,
        context_schema=UserContext,
        backend=CompositeBackend(
            default=StateBackend(),
            routes={"/memories/": StoreBackend(namespace=lambda rt: (rt.context.user_id, "memories"))},
        ),
        memory=["/memories/preferences.md"],
    )
    invoke(agent, "alice-1", "alice")
    invoke(agent, "bob-1", "bob")
    invoke(agent, "alice-2", "alice")
    # 断言模型实际收到的提示词；只检查最终回答不足以证明隔离。
    assert "ALICE_MARKER" in model.prompts[0] and "BOB_MARKER" not in model.prompts[0]
    assert "BOB_MARKER" in model.prompts[1] and "ALICE_MARKER" not in model.prompts[1]
    assert "ALICE_MARKER" in model.prompts[2] and "BOB_MARKER" not in model.prompts[2]
    assert "BOB_MARKER" not in content(store, "alice")
    print("PASS 3: user namespace isolation")


if __name__ == "__main__":
    main()
