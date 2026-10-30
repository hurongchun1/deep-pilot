"""实验 4：内置文件工具的 allow / interrupt / deny，全部操作虚拟 State。"""
from _lab import *
from deepagents import FilesystemPermission


def main():
    cases = [
        ("write_file", {"file_path": "/workspace/new.md", "content": "new"}, "allow"),
        ("write_file", {"file_path": "/memories/new.md", "content": "new"}, "approve"),
        ("write_file", {"file_path": "/memories/existing.md", "content": "overwritten"}, "approve"),
        ("edit_file", {"file_path": "/memories/existing.md", "old_string": "ORIGINAL", "new_string": "edited"}, "approve"),
        ("delete", {"file_path": "/memories/existing.md"}, "reject"),
        ("delete", {"file_path": "/memories/existing.md"}, "approve"),
        ("write_file", {"file_path": "/policies/rule.md", "content": "changed"}, "deny"),
        ("delete", {"file_path": "/"}, "approve-then-deny"),
    ]
    for index, (name, args, mode) in enumerate(cases):
        model = ScriptedModel(replies=[call(name, **args), done()])
        agent = create_deep_agent(model=model, checkpointer=InMemorySaver(), permissions=[
            FilesystemPermission(operations=["write"], paths=["/workspace/**"], mode="allow"),
            FilesystemPermission(operations=["write"], paths=["/memories/**"], mode="interrupt"),
            FilesystemPermission(operations=["write"], paths=["/policies/**"], mode="deny"),
        ])
        thread = f"permissions-{index}"
        files = {path: create_file_data("ORIGINAL") for path in (
            "/memories/existing.md", "/policies/rule.md", "/workspace/keep.md")}
        result = agent.invoke({"messages": [{"role": "user", "content": "执行文件操作"}], "files": files},
                              config=config(thread), version="v2")
        if mode in ("approve", "reject", "approve-then-deny"):
            requests(result)
            assert agent.get_state(config(thread)).values["files"] == files
            # 删除父目录可先触发中断；批准也不能绕过受保护后代的 deny。
            decision = "approve" if mode == "approve-then-deny" else mode
            result = resume(agent, thread, [{"type": decision, "message": "本次实验决策"}])
        else:
            assert not result.interrupts
        after = agent.get_state(config(thread)).values["files"]
        if mode in ("deny", "reject", "approve-then-deny"):
            assert after == files, "拒绝后文件发生改变"
            if mode != "reject":
                assert any("permission denied" in str(m.content).lower()
                           for m in result.value["messages"] if isinstance(m, ToolMessage))
        else:
            tools_ok(result)
            path = args["file_path"]
            if name == "delete":
                assert path not in after
            else:
                expected = args.get("content", args.get("new_string"))
                assert expected in after[path]["content"]
        print(f"PASS：{name} {args['file_path']} → {mode}")


if __name__ == "__main__":
    experiment_main(main)
