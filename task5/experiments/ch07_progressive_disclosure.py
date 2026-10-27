"""离线观察 Skill 元数据、正文和资源进入模型上下文的时机。

在 task5 目录运行：uv run --frozen python experiments/ch07_progressive_disclosure.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# 离线实验不发送 LangSmith trace；也避免进程退出时后台追踪线程尚在运行。
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr


class ScriptedModel(BaseChatModel):
    replies: list[AIMessage]
    prompts: list[str] = []
    _cursor: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "offline-skill-trace"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.prompts.append("\n".join(str(message.content) for message in messages))
        reply = self.replies[self._cursor]
        self._cursor += 1
        return ChatResult(generations=[ChatGeneration(message=reply)])


def read_file(path: str, call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": "read_file", "args": {"file_path": path}, "id": call_id}],
    )


def run_trace() -> list[str]:
    model = ScriptedModel(
        replies=[
            read_file("/skills/skill-guide/SKILL.md", "body"),
            read_file("/skills/skill-guide/references/concepts.md", "reference"),
            read_file("/skills/skill-guide/assets/guide-outline.md", "outline"),
            AIMessage(content="已读取 Skill 正文及按需资源。"),
        ]
    )
    graph = create_deep_agent(
        model=model,
        backend=FilesystemBackend(root_dir=PROJECT_ROOT, virtual_mode=True),
        skills=["/skills/"],
    )
    result = graph.invoke(
        {"messages": [{"role": "user", "content": "请按模板写一份 Skills 学习笔记。"}]}
    )
    errors = [m.content for m in result["messages"] if m.type == "tool" and m.status == "error"]
    if errors:
        raise RuntimeError(f"Skill reading failed: {errors}")
    prompts = model.prompts
    assert len(prompts) == 4
    assert "当用户要求编写 Deep Agents Skills 学习指南" in prompts[0]
    assert "区分 Skill 指令、普通工具与持久记忆" not in prompts[0]
    assert "区分 Skill 指令、普通工具与持久记忆" in prompts[1]
    assert "Skills 术语卡" not in prompts[1]
    assert "Skills 术语卡" in prompts[2]
    assert "# 学习笔记模板" not in prompts[2]
    assert "# 学习笔记模板" in prompts[3]
    return prompts


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    run_trace()
    print("第 1 轮：Skill 部分只有 skill-guide 的名称、描述和路径。")
    print("第 2 轮：读取 SKILL.md 后，提示词出现 Skill 正文。")
    print("第 3 轮：读取 concepts.md 后，提示词出现中文术语卡。")
    print("第 4 轮：读取 guide-outline.md 后，提示词出现中文学习笔记模板。")
    print("PASS：Skill 元数据、正文和资源按需进入模型上下文。")
