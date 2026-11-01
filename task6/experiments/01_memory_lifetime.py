"""实验 1：
- 新线程的文件状态里没有旧草稿，而且读取工具返回"找不到"
- 新线程收到的模型提示包含已保存的偏好，但不包含就草稿内容
- 回到旧线程后，读取工具能返回 DRAFT_MARKER
- 新建 fresh_store 后，里面没有先前的偏好，莫辛纳甘提示里也没有中文注释
"""
from _lab import *


def main():
    store = InMemoryStore()
    # 这里是固定写死模型回复的内容
    model = ScriptedModel(replies=[
        # 保存临时草稿
        call("write_file", file_path="/workspace/draft.md", content="DRAFT_MARKER"), done(),
        # 记住我的偏好
        call("write_file", file_path="/memories/preferences.md", content="中文注释，英文变量名"), done(),
        # 尝试读取旧草稿
        call("read_file", file_path="/workspace/draft.md"), done(),
        # 回到旧线程读取草稿
        call("read_file", file_path="/workspace/draft.md"), done(),
        done(),
    ])
    agent = memory_agent(model, store, memory=["/memories/preferences.md"])

    tools_ok(run(agent, "old", "保存临时草稿"))
    print("PASS 1/7：旧线程已保存临时草稿。")
    tools_ok(run(agent, "old", "记住我的偏好"))
    assert "中文注释" in content(store, "/preferences.md"), "偏好未写入 Store"
    print("PASS 2/7：偏好已写入 Store。")
    new = run(agent, "new", "尝试读取旧草稿")
    assert "/workspace/draft.md" not in agent.get_state(config("new")).values.get("files", {}), \
        "新线程的文件状态包含旧线程草稿"
    assert any("not found" in str(m.content).lower() or "does not exist" in str(m.content).lower()
               for m in new.value["messages"] if isinstance(m, ToolMessage)), \
        "新线程读取旧草稿时，工具没有返回文件不存在的信息"
    print("PASS 3/7：新线程读不到旧线程草稿。")

    # 新线程的系统提示中已经加载偏好，但没有旧线程的文件内容。
    assert "中文注释" in model.prompts[4], "新线程的模型提示未加载偏好"
    assert "DRAFT_MARKER" not in model.prompts[4], "新线程的模型提示泄漏了旧草稿内容"
    print("PASS 4/7：新线程提示加载了偏好，未包含旧草稿。")
    old = tools_ok(run(agent, "old", "回到旧线程读取草稿"))
    assert "DRAFT_MARKER" in str(old[-1].content), "旧线程未能读取已保存的草稿"
    print("PASS 5/7：回到旧线程后可以读取草稿。")
    run(agent, "loaded", "加载偏好")
    assert "中文注释" in model.prompts[-1], "另一新线程的模型提示未加载偏好"
    print("PASS 6/7：另一新线程也加载了偏好。")

    # 新建实例模拟重启后的空内存；它不等价于磁盘或数据库持久化。
    fresh_store = InMemoryStore()
    fresh_model = ScriptedModel(replies=[done()])
    fresh = memory_agent(fresh_model, fresh_store, memory=["/memories/preferences.md"])
    run(fresh, "after-restart")
    assert fresh_store.get(("alice", "memories"), "/preferences.md") is None, \
        "新建的 Store 意外包含旧偏好"
    assert "中文注释" not in fresh_model.prompts[0], "新建 Store 后的模型提示仍包含旧偏好"
    print("PASS 7/7：新建 Store 为空，模型提示没有旧偏好。")


if __name__ == "__main__":
    experiment_main(main)
