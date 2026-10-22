"""Optional chapter 3 trial with the model configured in task2/.env."""

from langchain_core.messages import AIMessage, ToolMessage

from task2.demo_binding import build_agent


def main() -> None:
    agent = build_agent()
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "请使用文件工具完成这个小任务：在 /lab/notes.md 写入三行，分别是 "
                        "'目标：理解 Backend'、'TODO：比较 State 和 Store'、'结论：按需读取'。"
                        "然后用 ls 查看 /lab，用 read_file 从 offset=1 读取 1 行，"
                        "最后用 grep 的 content 模式搜索 TODO。请简短说明你实际调用了哪些工具。"
                    ),
                }
            ]
        }
    )
    for message in result["messages"]:
        if isinstance(message, AIMessage) and message.tool_calls:
            names = [tool_call["name"] for tool_call in message.tool_calls]
            print("\n同一轮模型发出的工具调用：", names)
        if isinstance(message, ToolMessage):
            print(f"\n[{message.name} | {message.status}]\n{message.content}")
    tool_messages = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    print("\n实际工具调用次数：", len(tool_messages))
    print("\n模型最终回答：", result["messages"][-1].content)
    print("Agent State.files：", list(result.get("files", {})))


if __name__ == "__main__":
    main()
