"""用真实模型拆解任意目标；会调用模型服务，可能产生费用。"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from sample_plan import SCENARIOS


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
    return [{"name": item["name"], "id": item["id"],
             "args": {key: value for key, value in item["args"].items() if key != "content"}}
            for message in messages if isinstance(message, AIMessage)
            for item in message.tool_calls]


def tool_results(messages):
    return {message.tool_call_id: message for message in messages if message.type == "tool"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, default="learning")
    parser.add_argument("--task", help="直接描述你的目标、时间和约束；设置后覆盖预设案例")
    parser.add_argument("--slug", default="task-plan", help="输出文件名，不含 .md")
    args = parser.parse_args()
    if args.task is not None and not args.task.strip():
        parser.error("--task 不能为空")
    # 先校验文件名，避免消耗模型调用后才发现参数错误。
    from tools import _plan_path, check_plan
    artifact = _plan_path(args.slug)
    from agent import PROJECT_ROOT, build_graph, build_model

    model = build_model()
    graph = build_graph(model, checkpointer=InMemorySaver())
    run_id = uuid4().hex[:12]
    recorder = PromptRecorder()
    request = args.task or SCENARIOS[args.scenario]["request"]
    remember, snapshots = None, []
    error = None
    evidence_dir = PROJECT_ROOT / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    evidence_path = evidence_dir / f"planner-live-{run_id}.json"
    try:
        remember = graph.invoke(
            {"messages": [{"role": "user", "content": "请记住：以后写行动计划用中文分节 Markdown 格式。"}]},
            {"configurable": {"thread_id": f"{run_id}-remember"}, "recursion_limit": 30},
        )
        task = (request + "\n请使用 task-planning Skill 及参考提纲、write_todos。"
                "按用户给出的目标规划，本地资料仅在相关时读取。"
                f"使用 save_plan 将计划保存为 {args.slug}，再 read_plan、check_plan，等待各工具结果后回答。")
        for snapshot in graph.stream(
            {"messages": [{"role": "user", "content": task}]},
            {"configurable": {"thread_id": f"{run_id}-plan"},
             "callbacks": [recorder], "recursion_limit": 80}, stream_mode="values",
        ):
            snapshots.append(snapshot)
        messages = snapshots[-1]["messages"]
        calls, results = tool_calls(messages), tool_results(messages)
        memory_calls = tool_calls(remember["messages"])
        memory_results = tool_results(remember["messages"])
        saved = any(item["name"] == "save_preference" and item["id"] in memory_results
                    and memory_results[item["id"]].status != "error"
                    and "format:" in memory_results[item["id"]].text for item in memory_calls)
        required = {"write_todos", "read_file", "save_plan", "read_plan", "check_plan"}
        successful = {item["name"] for item in calls if item["id"] in results
                      and results[item["id"]].status != "error"}
        read_paths = {item["args"].get("file_path") for item in calls
                      if item["name"] == "read_file" and item["id"] in results
                      and results[item["id"]].status != "error"}
        checks = [results[item["id"]] for item in calls if item["name"] == "check_plan"
                  and item["args"].get("slug") == args.slug and item["id"] in results]
        checker = json.loads(checks[-1].text) if checks else {}
        file_check = json.loads(check_plan.invoke({"slug": args.slug})) if artifact.is_file() else {}
        # 要求本次调用确实依序保存、读回、检查目标文件，不能借用旧产物。
        order = [item["name"] for item in calls if item["args"].get("slug") == args.slug
                 and item["name"] in {"save_plan", "read_plan", "check_plan"}
                 and item["id"] in results and results[item["id"]].status != "error"]
        ordered = any(order[index:index + 3] == ["save_plan", "read_plan", "check_plan"]
                      for index in range(len(order) - 2))
        if not (saved and recorder.has_saved_preference and recorder.has_saved_preference[0]
                and required <= successful and ordered
                and {"/skills/task-planning/SKILL.md", "/skills/task-planning/references/plan-outline.md"} <= read_paths
                and checker.get("ok") and file_check.get("ok")
                and snapshots[-1].get("todos")
                and all(todo["status"] == "completed" for todo in snapshots[-1]["todos"])):
            raise RuntimeError("真实运行未覆盖全部必需步骤；详见精简证据")
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        messages = snapshots[-1]["messages"] if snapshots else []
        calls, results = tool_calls(messages), tool_results(messages)
        evidence = {
            "mode": "live", "model": model.model_name, "run_id": run_id,
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "request": request, "error": error,
            "memory_tool_calls": tool_calls(remember["messages"]) if remember else [],
            "memory_visible_in_new_thread": bool(recorder.has_saved_preference and recorder.has_saved_preference[0]),
            "tool_calls": calls,
            "tool_results": {key: {"status": value.status, "check": value.text if value.name == "check_plan" else None}
                             for key, value in results.items()},
            "todos": snapshots[-1].get("todos") if snapshots else None,
            "artifact": f"artifacts/{args.slug}.md" if artifact.is_file() else None,
            "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest() if artifact.is_file() else None,
        }
        evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print("精简证据：", evidence_path)
    print("行动计划：", artifact)
    print("结构检查通过；不代表计划已经执行或可行性已经验证。")


if __name__ == "__main__":
    main()
