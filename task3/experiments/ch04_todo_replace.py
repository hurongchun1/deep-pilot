"""Offline Chapter 4 lab: observe how write_todos replaces the todo list.

Run from the project root: uv run --frozen python experiments/ch04_todo_replace.py
"""

import os

# This scripted lab has no external model calls or traces to upload.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from langchain.agents import create_agent
from langchain.agents.middleware import TodoListMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr


class ScriptedModel(BaseChatModel):
    """按顺序返回预设回复；它不会自己决定何时调用工具。"""

    replies: list[AIMessage]
    _cursor: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "chapter-4-scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        # Agent 每次询问模型「下一步做什么」，就从 replies 取出下一项。
        reply = self.replies[self._cursor]
        self._cursor += 1
        if reply.tool_calls:
            call = reply.tool_calls[0]
            print(f"\n[模拟模型第 {self._cursor} 次回复] 请求调用 {call['name']}")
            print(f"  提交的完整清单：\n{call['args']['todos']}")
        else:
            print(f"\n[模拟模型第 {self._cursor} 次回复] 最终回答：\n{reply.content}")
        return ChatResult(generations=[ChatGeneration(message=reply)])


def todo_call(todos: list[dict[str, str]], call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": "write_todos", "args": {"todos": todos}, "id": call_id}],
    )


def main() -> None:
    # 第一次写入：Agent 的 todos 会变成这份完整清单。
    first = [
        {"content": "Read official docs", "status": "in_progress"},
        {"content": "Write report", "status": "pending"},
    ]
    # 第二次写入：故意删掉 "Write report"，加入 "Check citations"。
    # 如果 write_todos 是全量替换，最终状态中就不会再有 "Write report"。
    second = [
        {"content": "Read official docs", "status": "completed"},
        {"content": "Check citations", "status": "in_progress"},
    ]
    # 这三项就是模型被问三次时分别回答什么：
    # ① 请求 write_todos(first)；② 请求 write_todos(second)；③ 返回普通文本。
    model = ScriptedModel(
        replies=[
            # 模型第一次回复 -> 请求 write_todos(first) -> 工具写入第一份清单
            todo_call(first, "plan-1"),
            # 模型第二次回复 -> 请求 write_todos(second) -> 工具用第二份清单替换第一份
            todo_call(second, "plan-2"),
            # 模型第三次回复 -> 普通文字,无工具调用  -> Agent 结束
            AIMessage(content="Research finished."),
        ]
    )
    # tools=[] 表示没有另外添加工具；TodoListMiddleware 会提供真正的 write_todos。
    agent = create_agent(model=model, tools=[], middleware=[TodoListMiddleware()])

    snapshots = []
    todo_changes = []
    seen_tool_calls = set()
    # 每个 snapshot 是 Agent 运行到某一步后的完整状态。
    for snapshot in agent.stream(
        {"messages": [{"role": "user", "content": "Plan a research task."}]},
        # 把agent的执行从一次黑河变成可观察的时间线,用于过程可视化,中间状态断言,调试agent决策轨迹
        # 
        stream_mode="values",
    ):
        snapshots.append(snapshot)
        for message in snapshot["messages"]:
            if (
                isinstance(message, ToolMessage)
                and message.name == "write_todos"
                and message.tool_call_id not in seen_tool_calls
            ):
                seen_tool_calls.add(message.tool_call_id)
                print(f"[真实工具返回] {message.tool_call_id}: {message.content}")
        todos = snapshot.get("todos")
        if todos and (not todo_changes or todos != todo_changes[-1]):
            todo_changes.append(todos)
            print(f"[Agent 状态更新] todos = {todos}")

    # 两次工具调用后，状态只保留第二份清单；消息历史仍保留两次工具响应。
    assert todo_changes == [first, second]
    assert snapshots[-1]["todos"] == second

    tool_messages = [
        message
        for message in snapshots[-1]["messages"]
        if isinstance(message, ToolMessage) and message.name == "write_todos"
    ]
    # 这里断言模型回复的时候,调用的工具id是 plan-1 和 plan-2
    assert [message.tool_call_id for message in tool_messages] == ["plan-1", "plan-2"]

    # 把「全量替换」和「消息历史保留」变成能直接看到的证据。
    before = {todo["content"]: todo["status"] for todo in todo_changes[0]}
    after = {todo["content"]: todo["status"] for todo in todo_changes[1]}
    removed = [name for name in before if name not in after]
    added = [name for name in after if name not in before]
    changed = [
        f"{name}: {before[name]} -> {after[name]}"
        for name in before.keys() & after.keys()
        if before[name] != after[name]
    ]

    print("\n[直接看实验结果]")
    print("  第一次有、最终消失的任务：", removed)
    print("  第二次新增的任务：", added)
    print("  同一任务的状态变化：", changed)
    print("  最终 todos 等于第二次提交的完整清单：", snapshots[-1]["todos"] == second)
    print("  最终 messages 中仍有的两次工具响应 ID：", [
        message.tool_call_id for message in tool_messages
    ])


if __name__ == "__main__":
    main()
