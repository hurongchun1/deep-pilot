"""把手写的 LangGraph 图作为 CompiledSubAgent 接入 Deep Agent。"""

import os
import sys
from pathlib import Path
from typing import Annotated, TypedDict

from deepagents import CompiledSubAgent, create_deep_agent
from dotenv import load_dotenv
from langchain.tools import tool
from langchain_core.messages import AIMessage, AnyMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition


ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


# childstate：子图运行时保存的数据结构
class ChildState(TypedDict):
    # messages：保存用户消息、模型回复和工具结果；自定义图作为子 Agent 接入时必须有这个字段
    # add_messages：节点返回新消息时 ，将他合并进已有消息列表
    messages: Annotated[list[AnyMessage], add_messages]


# 需要将普通方法封装成可调用工具
@tool
def calculate_average(numbers: list[float]) -> float:
    """计算一组数字的算术平均值。"""
    # 1. 如果列表为空，抛出 ValueError
    if not numbers:
        raise ValueError("列表不能为空")
    # 2. 返回总和 ÷ 数量
    result = sum(numbers) / len(numbers)
    print(f"[子图 tools] calculate_average({numbers}) = {result}")
    return result


def build_model() -> ChatOpenAI:
    """读取 task4/.env，创建主 Agent 和子图共用的模型。"""
    if not ENV_FILE.is_file():
        raise SystemExit(f"找不到配置文件：{ENV_FILE}")
    load_dotenv(ENV_FILE, override=True)

    if os.getenv("BUB_API_KEY", "").strip():
        api_key = os.environ["BUB_API_KEY"]
        model_name = os.getenv("BUB_MODEL", "").strip() or "deepseek-ai/DeepSeek-V3.2"
        base_url = os.getenv("BUB_API_BASE", "").strip() or None
    else:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        model_name = os.getenv("AGENTSEEK_MODEL", "").strip() or "deepseek-ai/DeepSeek-V3.2"
        base_url = os.getenv("OPENAI_API_BASE", "").strip() or None
    if not api_key:
        raise SystemExit(f"请先在 {ENV_FILE} 配置 BUB_API_KEY 或 OPENAI_API_KEY")

    return ChatOpenAI(
        model=model_name.removeprefix("openai:"),
        base_url=base_url,
        api_key=api_key,
    )


def build_subagent_graph(model: ChatOpenAI):
    """子图执行顺序：model →（需要工具时）tools → model。"""
    model_with_tools = model.bind_tools([calculate_average])

    # model节点的创建
    def call_model(state: ChildState) -> dict:
        """模型节点读取消息，返回一条新消息给 ChildState。"""
        print("[子图 model] 正在读取 messages 并调用模型")
        reply = model_with_tools.invoke(
            [
                SystemMessage(
                    content="你是计算员。求平均值时必须调用 calculate_average；"
                    "根据工具结果解释算式，不要自己猜测结果。"
                ),
                *state["messages"],
            ]
        )
        return {"messages": [reply]}
    
    '''
    开始
    │
    ▼
    model（模型读取消息并回复）
    │
    ├─ 回复中有工具调用 ──► tools（执行 calculate_average）
    │                            │
    │                            └────────► 回到 model
    │
    └─ 回复中没有工具调用 ──► 结束
    '''
    # 定义流程中传递的数据：消息记录
    graph = StateGraph(ChildState)
    # 设置"思考与回答"步骤
    graph.add_node("model", call_model)
    # 设置"实际计算"步骤
    graph.add_node("tools", ToolNode([calculate_average]))
    # 从START 节点开始，从模型步骤开始
    graph.add_edge(START, "model")
    # 模型要调用工具就去 tools,否则结束
    # tools_condition的返回分两种情况：
    # 最后一条消息有tool_calls -> 返回字符串 "tools"(去名为tools的节点)
    # 最后一条消息没有 -> 返回字符串 "__end__"(去终点)
    graph.add_conditional_edges("model", tools_condition)
    # 计算完，把结果交给模型
    graph.add_edge("tools", "model")
    # 把流程定义变成可运行的子图
    return graph.compile()


def main() -> None:
    # Windows 终端可能默认使用 GBK；模型回复含特殊字符时改用 UTF-8。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    model = build_model()
    child_graph = build_subagent_graph(model)

    # CompiledSubAgent 的 runnable 是已经 compile() 的图。
    calculator: CompiledSubAgent = {
        "name": "calculator",
        "description": "计算一组数字的平均值，并解释计算过程。",
        # 将子agent集成进去
        "runnable": child_graph,
    }
    parent_agent = create_deep_agent(
        model=model,
        subagents=[calculator],
        system_prompt="你是协调者。遇到平均值问题，必须通过 task 工具委派给 calculator；"
        "收到子 Agent 的结果后再回答用户。",
    )

    question = "请让 calculator 子 Agent 计算 12、18、30 的平均值，并解释计算式。"
    print(f"[用户问题] {question}")

    final_answer = ""
    # 下面这串内容用来回答问题的
    for chunk in parent_agent.stream(
        {"messages": [{"role": "user", "content": question}]},
        stream_mode="updates",
    ):
        for node_name, update in chunk.items():
            if not isinstance(update, dict):
                continue
            for message in update.get("messages", []):
                if isinstance(message, AIMessage):
                    for call in message.tool_calls:
                        print(f"[主图 {node_name}] 请求工具：{call['name']} {call['args']}")
                    if message.content and not message.tool_calls:
                        final_answer = str(message.content)
                elif isinstance(message, ToolMessage):
                    print(f"[主图 {node_name}] 工具返回：{message.name} → {message.content}")

    if not final_answer:
        raise SystemExit("主 Agent 没有生成最终回复，请查看上面的调用记录。")
    print(f"\n[主 Agent 最终回答]\n{final_answer}")


if __name__ == "__main__":
    main()
