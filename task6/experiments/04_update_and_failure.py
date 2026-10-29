"""实验 4：局部更新保留其他条目；错误编辑不改变 Store。"""

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langgraph.store.memory import InMemoryStore

from _support import ScriptedModel, UserContext, call, content, done, invoke, seed, tools


def edit(old: str, new: str, call_id: str):
    """为对照实验构造一次 edit_file 调用，实际修改仍由 Deep Agents 工具执行。"""
    return call("edit_file", {
        "file_path": "/memories/preferences.md",
        "old_string": old,
        "new_string": new,
    }, call_id)


def main():
    # 两条偏好同处一个文件，用于检查局部更新是否误删无关条目。
    store = InMemoryStore()
    seed(store, "alice", "# 偏好\n语言：中文\n格式：列表\n")
    model = ScriptedModel(replies=[
        edit("语言：中文", "语言：英文", "replace-language"), done(),
        edit("不存在的旧内容", "语言：法文", "invalid-edit"), done(),
    ])
    # 更新成功和失败都经过同一条 /memories/ -> StoreBackend 路由。
    agent = create_deep_agent(
        model=model,
        store=store,
        context_schema=UserContext,
        backend=CompositeBackend(
            default=StateBackend(),
            routes={"/memories/": StoreBackend(namespace=lambda rt: (rt.context.user_id, "memories"))},
        ),
        memory=["/memories/preferences.md"],
        system_prompt="更新偏好时使用 edit_file，保留其他条目；工具失败时不能确认已保存。",
    )
    updated = invoke(agent, "update-thread", "alice")
    # 成功路径必须同时满足工具成功、新语言落盘、旧的格式偏好保留。
    assert any(m.tool_call_id == "replace-language" and m.status != "error" for m in tools(updated))
    assert "语言：英文" in content(store, "alice")
    assert "格式：列表" in content(store, "alice")
    failed = invoke(agent, "failure-thread", "alice")
    # 找不到 old_string 时工具应报错，Store 不得出现尝试写入的新值。
    assert any(m.tool_call_id == "invalid-edit" and m.status == "error" for m in tools(failed))
    assert "语言：英文" in content(store, "alice")
    assert "语言：法文" not in content(store, "alice")
    assert "格式：列表" in content(store, "alice")
    print("PASS 4: partial update and failed edit")


if __name__ == "__main__":
    main()
