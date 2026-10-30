"""实验 3：四种决策和一次批量审批。发送仅追加当前进程列表。"""
from _lab import *
from langchain.tools import tool


def main():
    for decision in ("approve", "edit", "reject", "respond"):
        sent, asked = [], []

        @tool
        def send_email(to: str, subject: str, body: str) -> str:
            """模拟发送邮件，仅记录参数。"""
            sent.append({"to": to, "subject": subject, "body": body})
            return "模拟发送成功"

        @tool
        def ask_user(question: str) -> str:
            """向用户询问信息。"""
            asked.append(question)
            return "不应执行此工具体"

        action = (call("ask_user", question="报告用什么语言？") if decision == "respond" else
                  call("send_email", to="old@example.test", subject="报告", body="草稿"))
        model = ScriptedModel(replies=[action, done()])
        agent = create_deep_agent(model=model, tools=[send_email, ask_user],
                                  checkpointer=InMemorySaver(), interrupt_on={
            "send_email": {"allowed_decisions": ["approve", "edit", "reject"]},
            "ask_user": {"allowed_decisions": ["respond"]},
        })
        result = run(agent, decision)
        assert len(requests(result)) == 1
        assert not sent and not asked
        review = {"type": decision}
        if decision == "edit":
            review["edited_action"] = {"name": "send_email", "args": {
                "to": "new@example.test", "subject": "报告", "body": "草稿"}}
        elif decision == "reject":
            review["message"] = "不要发送，不要重试，保留草稿。"
        elif decision == "respond":
            review["message"] = "请使用中文。"
        result = resume(agent, decision, [review])
        assert not result.interrupts
        assert len(sent) == (1 if decision in ("approve", "edit") else 0)
        if sent:
            assert sent[0]["to"] == ("new@example.test" if decision == "edit" else "old@example.test")
        assert not asked
        if decision == "respond":
            assert any(m.content == "请使用中文。" for m in result.value["messages"] if isinstance(m, ToolMessage))
        print(f"PASS：{decision}，实际发送记录={sent}")

    # 同一批的决策必须与 action_requests 数量、顺序一致。
    sent.clear()
    first = call("send_email", to="first@example.test", subject="一", body="一")
    second = call("send_email", to="second@example.test", subject="二", body="二")
    batch_model = ScriptedModel(replies=[AIMessage(content="", tool_calls=first.tool_calls + second.tool_calls), done()])
    batch = create_deep_agent(model=batch_model, tools=[send_email], checkpointer=InMemorySaver(),
                              interrupt_on={"send_email": {"allowed_decisions": ["approve", "reject"]}})
    result = run(batch, "batch")
    actions = requests(result)
    assert len(actions) == 2 and not sent
    resume(batch, "batch", [{"type": "approve"}, {"type": "reject", "message": "第二封不要发送"}])
    assert [entry["to"] for entry in sent] == ["first@example.test"]
    print("PASS：批量审批按动作顺序处理。")


if __name__ == "__main__":
    experiment_main(main)
