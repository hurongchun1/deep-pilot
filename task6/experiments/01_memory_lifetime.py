"""实验 1：同线程、新线程、旧线程与新建内存 Store 的对照。"""
from _lab import *


def main():
    store = InMemoryStore()
    model = ScriptedModel(replies=[
        call("write_file", file_path="/workspace/draft.md", content="DRAFT_MARKER"), done(),
        call("write_file", file_path="/memories/preferences.md", content="中文注释，英文变量名"), done(),
        call("read_file", file_path="/workspace/draft.md"), done(),
        call("read_file", file_path="/workspace/draft.md"), done(),
        done(),
    ])
    agent = memory_agent(model, store, memory=["/memories/preferences.md"])
    tools_ok(run(agent, "old", "保存临时草稿"))
    tools_ok(run(agent, "old", "记住我的偏好"))
    assert "中文注释" in content(store, "/preferences.md")
    new = run(agent, "new", "尝试读取旧草稿")
    assert "/workspace/draft.md" not in agent.get_state(config("new")).values.get("files", {})
    assert any("not found" in str(m.content).lower() or "does not exist" in str(m.content).lower()
               for m in new.value["messages"] if isinstance(m, ToolMessage))
    # 新线程的系统提示中已经加载偏好，但没有旧线程的文件内容。
    assert "中文注释" in model.prompts[4]
    assert "DRAFT_MARKER" not in model.prompts[4]
    old = tools_ok(run(agent, "old", "回到旧线程读取草稿"))
    assert "DRAFT_MARKER" in str(old[-1].content)
    run(agent, "loaded", "加载偏好")
    assert "中文注释" in model.prompts[-1]
    # 新建实例模拟重启后的空内存；它不等价于磁盘或数据库持久化。
    fresh_store = InMemoryStore()
    fresh_model = ScriptedModel(replies=[done()])
    fresh = memory_agent(fresh_model, fresh_store, memory=["/memories/preferences.md"])
    run(fresh, "after-restart")
    assert fresh_store.get(("alice", "memories"), "/preferences.md") is None
    assert "中文注释" not in fresh_model.prompts[0]
    print("PASS：线程文件隔离、旧线程恢复、偏好跨线程加载、新 Store 为空。")


if __name__ == "__main__":
    experiment_main(main)
