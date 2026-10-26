"""第 7 章离线实验共用的预设模型与 Skill 文件生成器。"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field, PrivateAttr


class ScriptedModel(BaseChatModel):
    replies: list[AIMessage]
    prompts: list[str] = Field(default_factory=list)
    bound_tool_names: list[str] = Field(default_factory=list)
    _cursor: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "ch07-scripted"

    def bind_tools(self, tools, **kwargs):
        self.bound_tool_names = [getattr(tool, "name", str(tool)) for tool in tools]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.prompts.append("\n".join(str(message.content) for message in messages))
        reply = self.replies[self._cursor]
        self._cursor += 1
        return ChatResult(generations=[ChatGeneration(message=reply)])


def skill_file(name: str, description: str) -> str:
    return f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n"
