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

    def reviewed(thread, label, decision="approve"):
        result = run(agent, thread)
        requests(result)
        before = {p: content(store, f"/research/{p}") for p in paths}
        if decision == "reject":
            assert "3.11" in before["notes.md"], "拒绝错误结论前，正确的 3.11 记录已丢失"
        result = resume(agent, thread, [{"type": decision, "message": "3.8 是错误结论，请保留 3.11，不要重试。" if decision == "reject" else "已核验"}])
        assert not result.interrupts, f"{label}：恢复后仍有待审批动作"
        if decision == "approve":
            tools_ok(result)
        else:
            assert before == {p: content(store, f"/research/{p}") for p in paths}, \
                f"{label}：拒绝后研究文件发生改变"
        print(f"PASS：{label}（{thread}，{decision}）。")

    tools_ok(run(agent, "session-1", "先写临时草稿"))
    assert "/workspace/draft.md" in agent.get_state(config("session-1")).values.get("files", {}), \
        "第一轮线程状态没有临时草稿"
    print("PASS：第一轮临时草稿已写入线程文件状态。")
    reviewed("session-1", "保存资料来源")
    reviewed("session-1", "保存已核验笔记")
    reviewed("session-1", "保存研究进度")
    reviewed("session-2", "拒绝错误的 3.8 结论", "reject")
    reviewed("session-2", "补充 TOML 只读限制")
    reviewed("session-2", "更新下一步进度")
    reviewed("session-3", "写入最终报告")
    assert "只支持读取 TOML" in model.prompts[-2], "第三轮模型提示未加载 TOML 只读限制"
    assert "下一步：撰写报告" in model.prompts[-2], "第三轮模型提示未加载研究进度"
    print("PASS：第三轮模型提示加载了笔记和进度。")
    assert "/workspace/draft.md" not in agent.get_state(config("session-3")).values.get("files", {}), \
        "第三轮线程状态包含第一轮的临时草稿"
    print("PASS：第三轮没有第一轮的临时草稿。")
    report = content(store, "/research/report.md")
    assert "3.11" in report and "3.8" not in report, "最终报告包含错误版本或缺少正确版本"
    print("PASS：最终报告保留 3.11，没有错误的 3.8 结论。")
    print(report)
    print("报告文字由预设模型给定；真实资料研究和结论质量请使用 07 实验评估。")


if __name__ == "__main__":
    experiment_main(main)
