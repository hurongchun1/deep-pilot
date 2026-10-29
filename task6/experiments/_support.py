"""第 8 章离线对照实验的公共工具。

这里只预设模型下一步提出的工具调用，不模拟 Deep Agents 的工具、Backend、
Checkpointer 或 Store。真实模型实验见 live_memory.py。
"""

import os
from dataclasses import dataclass

# 离线脚本不上传 trace；真实模型脚本不导入本模块，因此不会影响它的追踪。
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from deepagents.backends.utils import create_file_data
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field, PrivateAttr


@dataclass(frozen=True)
class UserContext:
    """运行时用户身份；StoreBackend 根据 user_id 选择 namespace。"""

    user_id: str


class ScriptedModel(BaseChatModel):
    """按 replies 顺序返回模型消息，并保存每轮实际收到的提示词。"""

    replies: list[AIMessage]
    prompts: list[str] = Field(default_factory=list)
    _cursor: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "ch08-scripted"

    def bind_tools(self, tools, **kwargs):
        # Deep Agents 会把工具绑定到模型；这里仍由预设的 AIMessage 决定调用哪一个。
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        # 保存模型请求，之后可断言记忆是否真正进入新线程的系统提示词。
        self.prompts.append("\n".join(str(m.content) for m in messages))
        if self._cursor >= len(self.replies):
            raise AssertionError("预设模型回复不足")
        reply = self.replies[self._cursor]
        self._cursor += 1
        return ChatResult(generations=[ChatGeneration(message=reply)])


def call(name: str, args: dict, call_id: str) -> AIMessage:
    """构造一条工具调用消息；工具本身仍由 Agent 正常执行。"""
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def done() -> AIMessage:
    """让预设模型结束当前对话。"""
    return AIMessage(content="实验结束")


def invoke(agent, thread_id: str, user_id: str):
    """用指定 thread_id 和 user_id 调用 Agent，两者分别控制线程与用户隔离。"""
    return agent.invoke(
        {"messages": [{"role": "user", "content": f"运行记忆实验：{thread_id}"}]},
        context=UserContext(user_id=user_id),
        config={"configurable": {"thread_id": thread_id}},
    )


def seed(store, user_id: str, content: str):
    """预置已有记忆文件；memory= 只加载文件，不会自动创建它。"""
    # CompositeBackend 会去掉 /memories/ 路由前缀；Store 的 key 因此是 /preferences.md。
    store.put((user_id, "memories"), "/preferences.md", create_file_data(content))


def content(store, user_id: str) -> str:
    """直接从 Store 读取真实内容，避免只根据模型回答判断写入成功。"""
    item = store.get((user_id, "memories"), "/preferences.md")
    assert item is not None
    return item.value["content"]


def tools(result) -> list[ToolMessage]:
    """提取真实工具结果，包括成功与失败状态。"""
    return [m for m in result["messages"] if isinstance(m, ToolMessage)]
