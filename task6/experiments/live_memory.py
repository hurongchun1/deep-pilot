"""第 8 章真实模型实验：记忆写入、跨线程重载、用户隔离及失败路径。

从 task6/.env 读取模型配置；要求 LANGSMITH_API_KEY；运行后打印工具轨迹和 trace 链接。
所有实验数据放在本进程的 InMemoryStore，不会修改 task5 或用户的真实文件。
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langchain.chat_models import init_chat_model
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tracers.langchain import wait_for_all_tracers
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langsmith import Client, trace, tracing_context

# shell 环境变量优先；.env 只为本地运行补足缺失值，不覆盖已有设置。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class UserContext:
    """把用户身份交给运行时；namespace 函数从这里取得 user_id。"""

    user_id: str


class RequestRecorder(BaseCallbackHandler):
    """记录真实模型请求中的系统消息，判断新线程实际加载了哪份记忆。"""

    def __init__(self):
        self.system_prompts: list[str] = []

    def on_chat_model_start(self, serialized, messages, **kwargs):
        # 这是模型真正收到的请求，不是 Agent 的最终回答。
        for batch in messages:
            system = "\n".join(str(m.content) for m in batch if m.type == "system")
            self.system_prompts.append(system)


def model_from_env():
    """按 content-builder 模板的环境变量约定连接真实聊天模型。"""
    provider = (os.getenv("AGENTSEEK_MODEL_PROVIDER") or "openai").strip()
    if provider != "openai":
        raise SystemExit("当前 live 脚本仅支持模板的 openai / OpenAI 兼容接口")
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        raise SystemExit("缺少 OPENAI_API_KEY：填写 task6/.env 或设置环境变量")
    model_name = (os.getenv("AGENTSEEK_MODEL") or "").strip()
    if not model_name:
        raise SystemExit("缺少 AGENTSEEK_MODEL：填写 task6/.env 或设置环境变量")
    # temperature=0 只降低随机性，不能保证模型每次选择完全相同的工具路径。
    kwargs = {"model_provider": "openai", "api_key": key, "temperature": 0}
    if base := (os.getenv("OPENAI_API_BASE") or "").strip():
        kwargs["base_url"] = base
    return init_chat_model(model=model_name, **kwargs)


def run_turn(agent, recorder: RequestRecorder, user_id: str, prompt: str, label: str, *, thread_id=None):
    """发起一轮真实模型对话；默认创建新线程，传入 thread_id 可恢复旧线程。"""
    thread_id = thread_id or f"ch08-{label}-{uuid4().hex[:8]}"
    print(f"\n=== {label}: user={user_id}, thread={thread_id} ===", flush=True)
    # Checkpointer 用 thread_id 定位线程；StoreBackend 用 context.user_id 定位用户。
    result = agent.invoke(
        {"messages": [{"role": "user", "content": prompt}]},
        context=UserContext(user_id=user_id),
        config={
            "configurable": {"thread_id": thread_id},
            "callbacks": [recorder],
            "recursion_limit": 24,
            "run_name": f"task6-{label}",
        },
    )
    # 把模型提出的调用和工具真实返回值打印出来，方便和 LangSmith trace 对照。
    for message in result["messages"]:
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                print(f"  -> {call['name']} {call['args']}", flush=True)
        elif isinstance(message, ToolMessage):
            print(f"  <- {message.name} [{message.status}] {str(message.content)[:300]}", flush=True)
    final = result["messages"][-1]
    print(f"  answer: {str(final.content)[:400]}", flush=True)
    return result, thread_id


def store_content(store, user_id: str) -> str:
    """直接核对底层 Store；不能把模型说“记住了”当作写入证据。"""
    item = store.get((user_id, "memories"), "/preferences.md")
    assert item is not None, f"{user_id} 的偏好文件不存在"
    return item.value["content"]


def main():
    # Windows 控制台常使用本地代码页；统一用 UTF-8 显示中文工具参数。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=os.getenv("LANGSMITH_PROJECT") or "deep-pilot-task6")
    args = parser.parse_args()
    # 用户要求每次 live 实验都产生 LangSmith trace，因此缺失密钥时立即停止。
    if not (os.getenv("LANGSMITH_API_KEY") or "").strip():
        raise SystemExit("缺少 LANGSMITH_API_KEY：live 实验要求上传 LangSmith trace")

    # 每次运行新建内存 Store；不触碰 task5 的偏好文件或真实用户资料。
    from deepagents.backends.utils import create_file_data

    store = InMemoryStore()
    # Alice 和 Bob 使用同一路径、不同 namespace；初始内容包含易于核对的标记。
    store.put(
        ("alice", "memories"), "/preferences.md",
        create_file_data("# 用户偏好\n回复语言：待设置\n输出格式：列表\n"),
    )
    store.put(
        ("bob", "memories"), "/preferences.md",
        create_file_data("# 用户偏好\n回复语言：英文\nBOB_PRIVATE_MARKER\n"),
    )
    recorder = RequestRecorder()
    # 直接在实验中装配 Agent，完整展示本章涉及的四个关键配置。
    agent = create_deep_agent(
        model=model_from_env(),
        store=store,  # 长期记忆的底层存储；两个新线程共享同一 Store 对象
        checkpointer=InMemorySaver(),  # 保存暂停/续接及线程内 State 文件
        context_schema=UserContext,  # 声明 context.user_id 的类型
        backend=CompositeBackend(
            default=StateBackend(),  # /workspace/ 只随当前 thread_id 的 checkpoint 保存
            routes={
                "/memories/": StoreBackend(  # 该路径前缀跨线程共享
                    namespace=lambda rt: (rt.context.user_id, "memories")
                ),
            },
        ),
        memory=["/memories/preferences.md"],  # 把已有文件内容载入系统提示词
        system_prompt=(
            "只有用户明确要求记住偏好时，才更新 /memories/preferences.md。"
            "先读已有内容，再用 edit_file 局部修改，保留其他偏好。"
            "仅在工具写入成功后确认已记住。"
        ),
    )
    client = Client()
    # 外层根 run 将多轮对话归入同一实验；每次 invoke 仍有自己的子 trace。
    with tracing_context(enabled=True, project_name=args.project, client=client):
        with trace(
            "ch08-live-memory",
            run_type="chain",
            inputs={"cases": ["write", "cross-thread-read", "isolation", "update", "state", "failed-edit"]},
            tags=["task6", "ch08", "live-memory"],
        ) as root:
            # 1. 用户明确要求记住偏好；模型应先读后编辑，Store 必须出现新值。
            run_turn(
                agent, recorder, "alice",
                "请记住我的偏好：今后回答用中文。先读取 /memories/preferences.md，"
                "把其中的“回复语言：待设置”改成“回复语言：中文”，保留输出格式。"
                "只有实际写入成功才告诉我已记住。",
                "write",
            )
            saved = store_content(store, "alice")
            assert "回复语言：中文" in saved and "输出格式：列表" in saved, (
                f"真实模型未正确写入 Store：{saved!r}"
            )

            # 2. 全新 thread_id：检验新模型请求是否重新加载 Alice 的更新后记忆。
            before = len(recorder.system_prompts)
            run_turn(agent, recorder, "alice", "我之前要求你记住的回复语言和输出格式是什么？", "read-new-thread")
            new_prompts = recorder.system_prompts[before:]
            assert new_prompts and any("回复语言：中文" in p for p in new_prompts), (
                "新线程模型请求未加载 Alice 更新后的记忆"
            )

            # 3. 相同虚拟路径换成 Bob：模型请求不能看到 Alice 的列表偏好。
            before = len(recorder.system_prompts)
            run_turn(agent, recorder, "bob", "我偏好的回复语言是什么？", "user-isolation")
            bob_prompts = recorder.system_prompts[before:]
            assert bob_prompts and any("BOB_PRIVATE_MARKER" in p for p in bob_prompts)
            assert all("输出格式：列表" not in p and "回复语言：中文" not in p for p in bob_prompts)

            # 4. 再次更新 Alice 的语言条目，核对不相关的格式条目没有被覆盖。
            run_turn(
                agent, recorder, "alice",
                "更新我的偏好：今后回答改用英文。请先读取 /memories/preferences.md，"
                "用 edit_file 把“回复语言：中文”改成“回复语言：英文”，保留输出格式；"
                "写入成功后再确认。",
                "update",
            )
            updated = store_content(store, "alice")
            assert "回复语言：英文" in updated and "输出格式：列表" in updated
            assert "回复语言：中文" not in updated
            assert "BOB_PRIVATE_MARKER" in store_content(store, "bob")

            # 5. 写入 /workspace/：这条路径走 StateBackend，应按 thread_id 隔离。
            state_write, state_thread = run_turn(
                agent, recorder, "alice",
                "请用 write_file 工具把 TEMP_ONLY_MARKER_6284 写入 /workspace/draft.txt，"
                "确认工具成功后再回答。",
                "state-write",
            )
            assert any(
                isinstance(m, ToolMessage) and m.name == "write_file" and m.status != "error"
                for m in state_write["messages"]
            ), "真实模型没有成功调用 write_file"
            # 新线程读取失败，说明文件没有因为同一 user_id 而自动共享。
            state_new, _ = run_turn(
                agent, recorder, "alice",
                "请用 read_file 工具读取 /workspace/draft.txt，报告工具结果。",
                "state-new-thread",
            )
            assert any(
                isinstance(m, ToolMessage) and m.name == "read_file" and m.status == "error"
                for m in state_new["messages"]
            ), "新线程意外读到了 State 文件，或模型没有尝试读取"
            # 回到原 thread_id 后可以读到草稿，证明 Checkpointer 恢复了 State。
            state_old, _ = run_turn(
                agent, recorder, "alice",
                "请再次用 read_file 工具读取 /workspace/draft.txt，报告文件内容。",
                "state-old-thread",
                thread_id=state_thread,
            )
            assert any(
                isinstance(m, ToolMessage) and m.name == "read_file" and "TEMP_ONLY_MARKER_6284" in str(m.content)
                for m in state_old["messages"]
            ), "原线程未恢复 State 文件"

            # 6. 故意把不存在的 old_string 交给 edit_file，检查失败后 Store 原样。
            before_failure = store_content(store, "alice")
            failed, _ = run_turn(
                agent, recorder, "alice",
                "请实际调用一次 edit_file，目标 /memories/preferences.md，"
                "old_string 填“不存在的旧内容_6284”，new_string 填“回复语言：法文”。"
                "这次是失败路径实验；请根据工具返回如实报告，不能说已经保存。",
                "failed-edit",
            )
            assert any(
                isinstance(m, ToolMessage) and m.name == "edit_file" and m.status == "error"
                for m in failed["messages"]
            ), "真实模型未产生预期的 edit_file 失败工具结果"
            assert store_content(store, "alice") == before_failure, "失败写入改变了 Store"
            root.add_outputs({"status": "passed", "alice_memory": updated})
            print("\nPASS: live cross-thread memory, isolation, state, update and failed edit", flush=True)
            print(f"LangSmith run: {root.get_url()}", flush=True)
    # 等待异步 trace 上传结束，再关闭客户端；此时打印的 LangSmith 链接可访问。
    wait_for_all_tracers()
    client.flush(timeout=20)
    client.close(timeout=20)


if __name__ == "__main__":
    main()
