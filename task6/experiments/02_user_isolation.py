"""实验 2：相同路径按用户隔离，再故意使用共享 namespace。"""
from _lab import *


def main():
    store = InMemoryStore()
    seed(store, "/preferences.md", "ALICE_ONLY：简洁回答", "alice")
    seed(store, "/preferences.md", "BOB_ONLY：详细解释", "bob")
    model = ScriptedModel(replies=[done(), done()])
    agent = memory_agent(model, store, memory=["/memories/preferences.md"])
    for user in ("alice", "bob"):
        run(agent, f"{user}-new", user=user)
    assert "ALICE_ONLY" in model.prompts[0] and "BOB_ONLY" not in model.prompts[0]
    assert "BOB_ONLY" in model.prompts[1] and "ALICE_ONLY" not in model.prompts[1]

    # 反例：写入 alice 的偏好却错误使用所有人共享的 namespace。
    seed(store, "/preferences.md", "ALICE_ONLY：简洁回答", "shared")
    shared_model = ScriptedModel(replies=[done()])
    shared = memory_agent(shared_model, store, memory=["/memories/preferences.md"], shared=True)
    run(shared, "bob-shared", user="bob")
    assert "ALICE_ONLY" in shared_model.prompts[0]
    print("PASS：用户 namespace 正确隔离；固定 namespace 反例暴露串记忆。")
    print("这里证明实际加载内容；回答风格请使用 07_live_assistant.py 观察。")


if __name__ == "__main__":
    experiment_main(main)
