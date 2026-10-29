"""第 9 章真实模型实验：approve、reject、edit、respond 四种人工决策。

此脚本不会发送邮件或调用真实外部业务接口。record_notice 仅向当前进程列表
追加一条本地记录，便于证明审批前没有副作用、审批后才真正执行。
人工决策由本实验脚本按预设方案提交；真实模型负责自行提出工具调用。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from uuid import uuid4

from deepagents import create_deep_agent
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tracers.langchain import wait_for_all_tracers
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from langsmith import Client, trace, tracing_context


# 仿照 content-builder 模板从实验目录旁的 .env 读取模型配置；shell 变量优先。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def main() -> None:
    """顺序执行四种决策，并对照 Checkpointer、工具轨迹与执行日志。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=os.getenv("LANGSMITH_PROJECT") or "deep-pilot-task7")
    args = parser.parse_args()

    # 两种密钥都要有：模型用于真实工具选择，LangSmith 用于上传完整运行链路。
    model_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    smith_key = (os.getenv("LANGSMITH_API_KEY") or "").strip()
    model_name = (os.getenv("AGENTSEEK_MODEL") or "").strip()
    if not model_key or not model_name or not smith_key:
        raise SystemExit("请在 task7/.env 或环境变量中设置 OPENAI_API_KEY、AGENTSEEK_MODEL、LANGSMITH_API_KEY")
    if (os.getenv("AGENTSEEK_MODEL_PROVIDER") or "openai") != "openai":
        raise SystemExit("此实验使用模板的 openai / OpenAI 兼容接口配置")
    model_kwargs = {"model_provider": "openai", "api_key": model_key, "temperature": 0}
    if base_url := (os.getenv("OPENAI_API_BASE") or "").strip():
        model_kwargs["base_url"] = base_url
    model = init_chat_model(model=model_name, **model_kwargs)

    # 本地列表充当“外部副作用记录”。审批前必须为空；approve/edit 后才会新增。
    executed: list[dict[str, str]] = []
    asked: list[str] = []

    @tool
    def record_notice(channel: str, message: str) -> str:
        """在本地执行日志记录一条通知；这是需要人工审批的副作用工具。"""
        executed.append({"channel": channel, "message": message})
        return f"已记录通知：{channel} / {message}"

    @tool
    def ask_user(question: str) -> str:
        """向人类询问缺失信息；真正回答由 respond 决策提供。"""
        asked.append(question)  # respond 正确生效时，这一行不会被执行。
        return "等待用户回答"

    @tool
    def read_policy(topic: str) -> str:
        """读取本地演示策略；只读工具不需要人工审批。"""
        return f"{topic}：通知只能写入本地实验日志。"

    # 直接在实验中构造 Agent。interrupt_on 是工具调用前的审批边界。
    # Checkpointer 保存暂停点；恢复时必须再次使用原来的 thread_id。
    agent = create_deep_agent(
        model=model,
        tools=[record_notice, ask_user, read_policy],
        interrupt_on={
            "record_notice": {"allowed_decisions": ["approve", "edit", "reject"]},
            "ask_user": {"allowed_decisions": ["respond"]},
            "read_policy": False,
        },
        checkpointer=InMemorySaver(),
        system_prompt=(
            "按用户要求调用指定工具。工具被人工拒绝后不要重试，也不要绕过工具直接写记录。"
            "需要询问人类时调用 ask_user，等待其返回；获得结果后再回答。"
        ),
    )
    client = Client()

    # 根 trace 把四个独立线程归为同一次学习实验，便于在 LangSmith 中逐步检查。
    with tracing_context(enabled=True, project_name=args.project, client=client):
        with trace(
            "ch09-live-hitl",
            run_type="chain",
            inputs={"cases": ["approve", "reject", "edit", "respond"]},
            tags=["task7", "ch09", "human-in-the-loop"],
        ) as root:
            cases = [
                ("approve", "调用 record_notice，channel='ops'，message='APPROVE_MARKER'。只调用一次。"),
                ("reject", "调用 record_notice，channel='ops'，message='REJECT_MARKER'。只调用一次。"),
                ("edit", "调用 record_notice，channel='ops'，message='EDIT_MARKER'。只调用一次。"),
                ("respond", "调用 ask_user，question='本次报告按什么时间维度统计？'；收到回答后复述。"),
            ]
            for decision_type, prompt in cases:
                # 每个案例使用独立线程，避免上一个案例的对话历史影响模型判断。
                config = {
                    "configurable": {"thread_id": f"ch09-{decision_type}-{uuid4().hex[:8]}"},
                    "recursion_limit": 20,
                    "run_name": f"ch09-{decision_type}",
                }
                before = list(executed)
                before_asked = list(asked)
                paused = agent.invoke(
                    {"messages": [{"role": "user", "content": prompt}]},
                    config=config,
                    version="v2",
                )
                assert paused.interrupts, f"{decision_type}：模型未发起需要审批的工具调用"

                # action_requests 是人工审查界面的输入；不同入口可能使用 args 或 arguments。
                payload = paused.interrupts[0].value
                actions = payload["action_requests"]
                reviews = payload["review_configs"]
                assert len(actions) == len(reviews) == 1, f"{decision_type}：预期只有一个待审批动作"
                action = actions[0]
                original_args = action.get("arguments", action.get("args", {}))
                expected_tool = "ask_user" if decision_type == "respond" else "record_notice"
                assert action["name"] == expected_tool, f"{decision_type}：实际待审工具为 {action['name']}"
                assert decision_type in reviews[0]["allowed_decisions"]
                assert executed == before and asked == before_asked, "审批前已有工具副作用"

                # 暂停状态保存在 Checkpointer 中；检查 next 和 interrupts 能定位卡点。
                snapshot = agent.get_state(config)
                assert snapshot.next and snapshot.interrupts, "Checkpoint 没有保存待恢复中断"
                print(f"\n[{decision_type}] 待审工具={action['name']} 参数={original_args}")
                print(f"[{decision_type}] checkpoint.next={snapshot.next}")

                # 人类决策的数据形状：edit 必须带 name 与 args；respond 返回人类消息。
                if decision_type == "approve":
                    decision = {"type": "approve"}
                elif decision_type == "reject":
                    decision = {
                        "type": "reject",
                        "message": "用户拒绝这次通知。不要重试，也不要声称已经执行。",
                    }
                elif decision_type == "edit":
                    decision = {
                        "type": "edit",
                        "edited_action": {
                            "name": action["name"],
                            "args": {**original_args, "channel": "reviewed"},
                        },
                    }
                else:
                    decision = {"type": "respond", "message": "使用季度维度，并排除测试数据。"}

                # Command(resume=...) 必须和暂停时使用相同的 config/thread_id。
                resumed = agent.invoke(
                    Command(resume={"decisions": [decision]}),
                    config=config,
                    version="v2",
                )
                assert not resumed.interrupts, f"{decision_type}：提交决策后仍在暂停"
                tool_messages = [m for m in resumed.value["messages"] if isinstance(m, ToolMessage)]
                assert tool_messages, f"{decision_type}：恢复后没有工具结果"

                # 根据实际本地执行日志判断动作是否发生，而非相信模型最后的自然语言。
                added = executed[len(before):]
                if decision_type == "approve":
                    assert added == [{"channel": "ops", "message": "APPROVE_MARKER"}]
                elif decision_type == "reject":
                    assert not added, "reject 后通知仍被执行"
                elif decision_type == "edit":
                    assert added == [{"channel": "reviewed", "message": "EDIT_MARKER"}]
                else:
                    assert not added and asked == before_asked, "respond 不应真正运行 ask_user"
                    assert any("季度维度" in str(m.content) for m in tool_messages)
                final = resumed.value["messages"][-1]
                if isinstance(final, AIMessage):
                    print(f"[{decision_type}] 最终回答={str(final.content)[:220]}")
                print(f"[{decision_type}] 工具结果={str(tool_messages[-1].content)[:220]}")

            root.add_outputs({"status": "passed", "executed": executed})
            print("\nPASS：四种决策均按预期暂停、恢复并控制真实工具执行")
            print(f"LangSmith run: {root.get_url()}")

    # LangSmith tracer 异步上传；等待完成后再关闭客户端。
    wait_for_all_tracers()
    client.flush(timeout=20)
    client.close(timeout=20)


if __name__ == "__main__":
    main()
