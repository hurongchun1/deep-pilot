"""实验 6：三轮研究交接，拒绝错误结论，检查最终报告工具输出。"""
from _lab import *
from deepagents import FilesystemPermission


def main():
    store = InMemoryStore()
    paths = ["sources.md", "notes.md", "progress.md", "report.md"]
    for path in paths:
        seed(store, f"/research/{path}", "待填写")
    model = ScriptedModel(replies=[
        call("write_file", file_path="/workspace/draft.md", content="临时草稿"), done(),
        call("write_file", file_path="/memories/research/sources.md", content="资料：Python 官方 tomllib 文档"), done(),
        call("write_file", file_path="/memories/research/notes.md", content="已核验：tomllib 自 Python 3.11 加入标准库。"), done(),
        call("write_file", file_path="/memories/research/progress.md", content="已完成：资料收集；下一步：比较配置格式。"), done(),
        call("edit_file", file_path="/memories/research/notes.md", old_string="3.11", new_string="3.8"), done(),
        call("edit_file", file_path="/memories/research/notes.md", old_string="标准库。", new_string="标准库；只支持读取 TOML。"), done(),
        call("write_file", file_path="/memories/research/progress.md", content="已完成：补充只读限制；下一步：撰写报告。"), done(),
        call("write_file", file_path="/memories/research/report.md", content="配置研究报告：tomllib 在 Python 3.11 加入标准库，只支持读取 TOML。"), done(),
    ])
    agent = memory_agent(model, store, memory=[f"/memories/research/{p}" for p in paths], permissions=[
        FilesystemPermission(operations=["write"], paths=["/memories/**"], mode="interrupt"),
    ])

    def reviewed(thread, decision="approve"):
        result = run(agent, thread)
        requests(result)
        before = {p: content(store, f"/research/{p}") for p in paths}
        if decision == "reject":
            assert "3.11" in before["notes.md"]
        result = resume(agent, thread, [{"type": decision, "message": "3.8 是错误结论，请保留 3.11，不要重试。" if decision == "reject" else "已核验"}])
        assert not result.interrupts
        if decision == "approve":
            tools_ok(result)
        else:
            assert before == {p: content(store, f"/research/{p}") for p in paths}

    tools_ok(run(agent, "session-1", "先写临时草稿"))
    for _ in range(3):
        reviewed("session-1")
    reviewed("session-2", "reject")
    reviewed("session-2")
    reviewed("session-2")
    reviewed("session-3")
    assert "只支持读取 TOML" in model.prompts[-2]
    assert "下一步：撰写报告" in model.prompts[-2]
    assert "/workspace/draft.md" not in agent.get_state(config("session-3")).values.get("files", {})
    report = content(store, "/research/report.md")
    assert "3.11" in report and "3.8" not in report
    print("PASS：三轮交接、错误写入拒绝、有效补充保留、临时草稿隔离。")
    print(report)
    print("报告文字由预设模型给定；真实资料研究和结论质量请使用 07 实验评估。")


if __name__ == "__main__":
    experiment_main(main)
