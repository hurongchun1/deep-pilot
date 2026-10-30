"""实验 5：规则的批准、修改、拒绝，以及新线程的实际加载。"""
from _lab import *
from deepagents import FilesystemPermission


def main():
    original = "# 回答规则\n暂无长期规则。"
    proposed = "先给最小可运行示例，再解释原理。"
    narrowed = "只有用户要求代码时才提供示例。"
    for decision in ("approve", "edit", "reject"):
        store = InMemoryStore()
        seed(store, "/AGENTS.md", original)
        model = ScriptedModel(replies=[call("edit_file", file_path="/memories/AGENTS.md",
            old_string="暂无长期规则。", new_string=proposed), done(), done()])
        agent = memory_agent(model, store, memory=["/memories/AGENTS.md"], permissions=[
            FilesystemPermission(operations=["write"], paths=["/memories/**"], mode="interrupt"),
        ])
        result = run(agent, "feedback", "以后先给示例再解释，请记住。")
        requests(result)
        assert content(store, "/AGENTS.md") == original
        review = {"type": decision}
        if decision == "edit":
            review["edited_action"] = {"name": "edit_file", "args": {
                "file_path": "/memories/AGENTS.md", "old_string": "暂无长期规则。", "new_string": narrowed}}
        elif decision == "reject":
            review["message"] = "只是本次要求，不要保存或重试。"
        resume(agent, "feedback", [review])
        expected = {"approve": proposed, "edit": narrowed, "reject": "暂无长期规则。"}[decision]
        assert content(store, "/AGENTS.md") == "# 回答规则\n" + expected
        run(agent, "fresh-question", "解释 Python 生成器")
        assert expected in model.prompts[-1]
        if decision != "approve":
            assert proposed not in model.prompts[-1]
        print(f"PASS：{decision}，新线程加载规则：{expected}")
    print("离线只证明保存与注入正确；真实回答是否遵循规则，用 07 实验观察。")


if __name__ == "__main__":
    experiment_main(main)
