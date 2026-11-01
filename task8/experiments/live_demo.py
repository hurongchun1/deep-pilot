"""用真实模型制定青柠清单 v1.2 上线计划并保存精简证据。

在 task8 目录运行：uv run --frozen python -X utf8 experiments/live_demo.py
此脚本会调用模型服务，可能产生费用。
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from agent import PROJECT_ROOT, build_graph, build_model
from tools import check_plan


class PromptRecorder(BaseCallbackHandler):
    def __init__(self):
        self.has_saved_preference: list[bool] = []

    def on_chat_model_start(self, serialized, messages, **kwargs):
        for batch in messages:
            prompt = "\n".join(str(message.content) for message in batch)
            self.has_saved_preference.append(
                "format:" in prompt and "中文" in prompt and "Markdown" in prompt
            )


def tool_calls(messages):
    calls = []
    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                args = {key: value for key, value in call["args"].items() if key != "content"}
                calls.append({"name": call["name"], "args": args, "id": call["id"]})
    return calls


def tool_results(messages):
    return {message.tool_call_id: message for message in messages if message.type == "tool"}


def main():
    model = build_model()
    model_name = model.model_name
    graph = build_graph(model, checkpointer=InMemorySaver())
    run_id = uuid4().hex[:12]
    remember_id, plan_id = f"{run_id}-remember", f"{run_id}-plan"
    print(f"真实模型：{model_name}；运行标识：{run_id}")

    remember = graph.invoke(
        {"messages": [{"role": "user", "content": "请记住：以后制定上线计划时，用中文分节 Markdown 格式。"}]},
        {"configurable": {"thread_id": remember_id}, "recursion_limit": 30},
    )
    memory = (PROJECT_ROOT / "memory/preferences.md").read_text(encoding="utf-8")
    remember_calls = tool_calls(remember["messages"])
    remember_results = tool_results(remember["messages"])
    saved_by_tool = any(
        call["name"] == "save_preference" and call["id"] in remember_results
        and remember_results[call["id"]].status != "error"
        and "format:" in str(remember_results[call["id"]].content)
        for call in remember_calls
    )
    remembered = saved_by_tool and "format:" in memory and "中文" in memory and "Markdown" in memory
    if not remembered:
        print("保存偏好会话调用了：", [call["name"] for call in remember_calls])
        print("偏好文件是否含中文与 Markdown：", "中文" in memory, "Markdown" in memory)
        raise RuntimeError("真实模型未保存明确要求记住的格式偏好")

    prompt_recorder = PromptRecorder()
    request = (
        "请为青柠清单 v1.2 制定一份可执行的上线计划。先按 release-plan Skill "
        "读取两份本地资料和参考提纲，使用 write_todos 规划。"
        "计划要写清 10% → 50% → 100% 放量、验收指标、暂停与回滚条件。"
        "资料未给出的姓名或实测值标为待确认或待验证，不要编造。"
        "将计划保存为 qingning-release-plan，读回并调用 check_plan 检查后再回答。"
    )
    snapshots = []
    try:
        for snapshot in graph.stream(
            {"messages": [{"role": "user", "content": request}]},
            {"configurable": {"thread_id": plan_id},
             "callbacks": [prompt_recorder], "recursion_limit": 80},
            stream_mode="values",
        ):
            snapshots.append(snapshot)
    except Exception:
        if snapshots:
            print("中断前调用了：", [call["name"] for call in tool_calls(snapshots[-1]["messages"])])
        raise

    final = snapshots[-1]
    calls = tool_calls(final["messages"])
    results = tool_results(final["messages"])
    names = [call["name"] for call in calls]
    checker = next((results.get(call["id"]) for call in reversed(calls)
                    if call["name"] == "check_plan"), None)
    try:
        checker_result = json.loads(checker.text) if checker and checker.status != "error" else None
    except json.JSONDecodeError:
        checker_result = None

    artifact = PROJECT_ROOT / "artifacts/qingning-release-plan.md"
    final_file_check = json.loads(check_plan.invoke({"slug": "qingning-release-plan"})) if artifact.is_file() else None
    sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest() if artifact.is_file() else None
    todo_states = []
    for snapshot in snapshots:
        state = [todo["status"] for todo in snapshot.get("todos") or []]
        if state and (not todo_states or state != todo_states[-1]):
            todo_states.append(state)

    evidence = {
        "mode": "live", "model": model_name, "run_id": run_id,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "remember_thread": remember_id, "plan_thread": plan_id,
        "memory_saved_by_model": remembered,
        "memory_visible_in_new_thread": bool(prompt_recorder.has_saved_preference and
                                             prompt_recorder.has_saved_preference[0]),
        "memory_tool_calls": remember_calls,
        "tool_calls": calls,
        "tool_result_status": {call_id: message.status for call_id, message in results.items()},
        "todo_states": todo_states,
        "check_plan": checker_result,
        "final_file_check": final_file_check,
        "artifact": "artifacts/qingning-release-plan.md" if sha256 else None,
        "artifact_sha256": sha256,
        "langsmith_tracing": os.getenv("LANGSMITH_TRACING", "false").lower() == "true",
    }
    evidence_dir = PROJECT_ROOT / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    evidence_path = evidence_dir / f"live-{run_id}.json"
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print("上线计划会话调用了：", names)
    print("结构检查结果：", checker_result)
    print("证据文件：", evidence_path)

    required = {"write_todos", "read_file", "read_source", "save_plan", "read_plan", "check_plan"}
    read_sources = {call["args"].get("name") for call in calls if call["name"] == "read_source"}
    successful_required = all(
        results.get(call["id"]) is not None and results[call["id"]].status != "error"
        for call in calls if call["name"] in required
    )
    if not (required <= set(names)
            and read_sources == {"product-brief.md", "release-constraints.md"}
            and successful_required
            and evidence["memory_visible_in_new_thread"]
            and checker_result and checker_result.get("ok")
            and final_file_check and final_file_check.get("ok")
            and sha256):
        raise RuntimeError("真实模型运行未覆盖全部必需步骤；已保存现有证据")


if __name__ == "__main__":
    main()
