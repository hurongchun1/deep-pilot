"""Chapter 4 lab: inspect a research agent's tool calls and todo state.

Run from the project root with: uv run --frozen python experiments/ch04_planning.py
"""

from __future__ import annotations

import os
from pathlib import Path

from deepagents import create_deep_agent
from dotenv import load_dotenv
from langchain.agents.middleware import TodoListMiddleware
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from tavily import TavilyClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"
if not ENV_FILE.is_file():
    raise SystemExit(f"找不到配置文件：{ENV_FILE}")
load_dotenv(ENV_FILE, override=True)

QUESTION = (
    "请调研 Agent 开发领域的三个 Harness 框架（Deep Agents、Claude Agent SDK、"
    "Codex SDK），对比它们的核心能力差异，写一份简要分析报告。"
)


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"请先在 {ENV_FILE} 中填写 {name}")
    return value


def main() -> None:
    tavily_key = required_env("TAVILY_API_KEY")

    # 优先读取当前 .env 中的 BUB_*；也兼容 .env.example 的 OPENAI_* 配置。
    if os.getenv("BUB_API_KEY", "").strip():
        model_key = required_env("BUB_API_KEY")
        model_name = os.getenv("BUB_MODEL", "").strip() or "deepseek-ai/DeepSeek-V3.2"
        base_url = os.getenv("BUB_API_BASE", "").strip() or None
    else:
        model_key = required_env("OPENAI_API_KEY")
        model_name = os.getenv("AGENTSEEK_MODEL", "").strip() or "deepseek-ai/DeepSeek-V3.2"
        base_url = os.getenv("OPENAI_API_BASE", "").strip() or None

    # BUB_MODEL 可写成 "openai:deepseek-flash"；ChatOpenAI 只接受接口中的模型名。
    if model_name.startswith("openai:"):
        model_name = model_name.removeprefix("openai:")
    if not model_name:
        raise SystemExit(f"请在 {ENV_FILE} 中填写有效的模型名")

    model = ChatOpenAI(
        model=model_name,
        api_key=model_key,
        base_url=base_url,
    )
    tavily_client = TavilyClient(api_key=tavily_key)

    def internet_search(query: str, max_results: int = 3) -> dict:
        """搜索互联网，获取研究任务所需的资料。"""
        return tavily_client.search(query, max_results=max_results)

    agent = create_deep_agent(
        model=model,
        tools=[internet_search],
        middleware=[TodoListMiddleware()],
        system_prompt=(
            "你是一位技术研究员。遇到多步骤研究任务时，先用 write_todos 规划，"
            "再搜索资料、核对来源、更新任务状态，最后给出有来源的简要报告。"
        ),
    )

    print(f"配置文件：{ENV_FILE}")
    print(f"研究问题：{QUESTION}\n")
    last_todos = None
    seen_tool_calls: set[str] = set()
    final_snapshot = None

    for snapshot in agent.stream(
        {"messages": [{"role": "user", "content": QUESTION}]},
        stream_mode="values",
    ):
        final_snapshot = snapshot
        for message in snapshot.get("messages", []):
            if not isinstance(message, AIMessage):
                continue
            for call in message.tool_calls:
                call_id = call.get("id") or str(call)
                if call_id not in seen_tool_calls:
                    seen_tool_calls.add(call_id)
                    print(f"工具调用：{call['name']}")

        todos = snapshot.get("todos", [])
        if todos != last_todos:
            last_todos = [dict(item) for item in todos]
            if todos:
                print("\n任务状态：")
                for item in todos:
                    print(f"  [{item['status']}] {item['content']}")
                print()

    if final_snapshot is None:
        raise SystemExit("Agent 没有返回状态快照")

    print("\n最终回答：")
    print(final_snapshot["messages"][-1].content)
    print("\n最终 todos：", final_snapshot.get("todos", []))


if __name__ == "__main__":
    main()
