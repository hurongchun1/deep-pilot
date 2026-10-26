# experiments/_support.py
from collections.abc import Callable
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


def tool_call(name: str, args: dict, call_id: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def tool_results(messages) -> list[ToolMessage]:
    return [m for m in messages if isinstance(m, ToolMessage)]


class ScriptedModel(BaseChatModel):
    """responder 看完整消息列表，决定下一条 AIMessage；模型之外的组件都是真的。"""

    responder: Callable[[list], AIMessage]
    turns: list[dict] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "ch07-scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.turns.append({
            "context": "\n".join(str(getattr(m, "content", "")) for m in messages),
            "tool_ids": {m.tool_call_id for m in messages if isinstance(m, ToolMessage)},
        })
        return ChatResult(generations=[ChatGeneration(message=self.responder(messages))])


def assert_disclosed(turns: list[dict], call_id: str, marker: str, label: str) -> None:
    """marker 在该 call_id 返回之前不得出现，返回之后必须出现。"""
    for turn in turns:
        if call_id not in turn["tool_ids"]:
            assert marker not in turn["context"], f"{label}：{call_id} 返回前就泄漏进上下文"
    assert any(marker in t["context"] for t in turns if call_id in t["tool_ids"]), f"{label}：返回后仍未出现"