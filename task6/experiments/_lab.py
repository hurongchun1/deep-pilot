"""共用设施：预设模型只决定请求；工具、权限、Store、Checkpoint 均真实执行。"""
from __future__ import annotations

import os
import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from deepagents.backends.utils import create_file_data
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command
from pydantic import Field, PrivateAttr
from dotenv import load_dotenv
from langsmith import Client, trace, tracing_context
from langsmith.utils import tracing_is_enabled
from langchain_core.tracers.langchain import wait_for_all_tracers


def experiment_main(main):
    """沿用进程环境；CLI 开关仅覆盖本次追踪，并为每个实验建立根 trace。"""
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    parser = argparse.ArgumentParser(add_help=False)
    switches = parser.add_mutually_exclusive_group()
    switches.add_argument("--trace", dest="tracing", action="store_true")
    switches.add_argument("--no-trace", dest="tracing", action="store_false")
    parser.set_defaults(tracing=None)
    options, remaining = parser.parse_known_args()
    sys.argv[1:] = remaining
    if "--help" in remaining or "-h" in remaining:
        if Path(sys.argv[0]).name != "07_live_assistant.py":
            print("运行当前实验；--trace 强制开启 LangSmith，--no-trace 强制关闭，默认沿用环境变量。")
            return
        main()
        return
    enabled = tracing_is_enabled() if options.tracing is None else options.tracing
    if not enabled:
        print("LangSmith：关闭（可用 --trace 开启）。")
        with tracing_context(enabled=False):
            main()
        return
    project = os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT") or "deep-pilot-task6"
    name = "task6/" + Path(sys.argv[0]).stem
    client = Client()
    print(f"LangSmith：开启，项目={project}，实验={name}")
    try:
        with tracing_context(enabled=True, project_name=project, client=client):
            with trace(name, inputs={"experiment": name}, tags=["task6"],
                       metadata={"model_mode": "live" if "07_live" in name else "scripted"},
                       client=client, project_name=project) as root:
                try:
                    print(f"Trace：{root.get_url()}")
                except Exception:
                    print(f"Trace ID：{root.id}（链接生成失败，请到项目内查找）")
                main()
                root.end(outputs={"completed": True})
    finally:
        # 等待子节点及根 trace 的后台上传，避免进程退出导致 incomplete。
        wait_for_all_tracers()
        client.flush()


@dataclass(frozen=True)
class User:
    user_id: str = "alice"


class ScriptedModel(BaseChatModel):
    replies: list[AIMessage]
    prompts: list[str] = Field(default_factory=list)
    _cursor: int = PrivateAttr(default=0)

    @property
    def _llm_type(self):
        return "task6-scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.prompts.append("\n".join(str(m.content) for m in messages))
        if self._cursor >= len(self.replies):
            raise AssertionError("预设回复耗尽：请检查是否发生了意外重试或额外模型调用")
        reply = self.replies[self._cursor]
        self._cursor += 1
        return ChatResult(generations=[ChatGeneration(message=reply)])


def call(name: str, **args) -> AIMessage:
    return AIMessage(content="", tool_calls=[{
        "name": name, "args": args, "id": uuid4().hex, "type": "tool_call",
    }])


def done() -> AIMessage:
    return AIMessage(content="本轮完成（预设回复，不作为验收依据）。")


def config(thread: str):
    return {"configurable": {"thread_id": thread}}


def run(agent, thread: str, text="执行本轮实验", user="alice"):
    return agent.invoke({"messages": [{"role": "user", "content": text}]},
                        config=config(thread), context=User(user), version="v2")


def resume(agent, thread: str, decisions: list[dict], user="alice"):
    return agent.invoke(Command(resume={"decisions": decisions}),
                        config=config(thread), context=User(user), version="v2")


def requests(result):
    assert len(result.interrupts) == 1, "本实验预期一个中断批次"
    actions = result.interrupts[0].value["action_requests"]
    print("待审批动作：", actions)
    return actions


def content(store, key, user="alice"):
    item = store.get((user, "memories"), key)
    assert item is not None, f"记忆不存在：{user}/{key}"
    value = item.value["content"]
    return value if isinstance(value, str) else "\n".join(value)


def seed(store, key, text, user="alice"):
    store.put((user, "memories"), key, create_file_data(text))

# result 里包含整个线程的历史消息，这个函数只检查刚才这一次操作有没有成功
def tools_ok(result):
    history = result.value["messages"]
    # 同线程保留历史；之前被人工拒绝的 ToolMessage 不能算作本轮失败。
    start = next((i for i in range(len(history) - 1, -1, -1)
                  if isinstance(history[i], HumanMessage)), 0)
    messages = [m for m in history[start:] if isinstance(m, ToolMessage)]
    assert messages, "没有工具执行记录"
    for message in messages:
        assert message.status != "error", message.content
    return messages


def memory_agent(model, store, *, memory=None, shared=False, **kwargs):
    return create_deep_agent(
        model=model, 
        context_schema=User, 
        store=store,
        checkpointer=InMemorySaver(), 
        memory=memory or [],
        backend=CompositeBackend(
            default=StateBackend(), 
            routes={
            "/memories/": StoreBackend(namespace=lambda rt: (
                "shared" if shared else rt.context.user_id, "memories")),
        }), **kwargs,
    )


if __name__ == "__main__":
    print("这是共用模块，请运行编号实验。")
