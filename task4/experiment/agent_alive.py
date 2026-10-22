from re import sub
from typing import Any, Literal

from langchain.agents.middleware import TodoListMiddleware
from langchain_openai import ChatOpenAI
from pathlib import Path
from dotenv import load_dotenv
import os

from deepagents import create_deep_agent
from research_find import search_subagent

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"  # experiment/ 的上一级 = task4/
load_dotenv(ENV_FILE)

# 创建模型
# 坑1：模型名的参数是 model，不是 name（name 是 Runnable 显示名，会被静默吞掉，
#      model 退回默认值 gpt-3.5-turbo → 网关 400）。
# 坑2：.env 里 AGENTSEEK_MODEL=openai:deepseek-flash 的 "openai:" 前缀是
#      init_chat_model() 的提供商语法，直传 ChatOpenAI 要剥掉，否则网关收到
#      "openai:deepseek-flash" 还是会 400。
model = ChatOpenAI(
    model = os.environ["AGENTSEEK_MODEL"].removeprefix("openai:"),
    base_url = os.environ["OPENAI_API_BASE"],
    api_key= os.environ["OPENAI_API_KEY"],  # pyright: ignore[reportArgumentType]
    # DeepSeek 的 thinking.type 默认 enabled（思考模式）；思考模式不支持
    # tool_choice="required"，而结构化输出（response_format）会让 langchain
    # 强制 tool_choice="any"→"required" → 400 "Thinking mode does not support
    # this tool_choice"。关掉思考模式即可（官方文档建议）。
    extra_body = {"thinking": {"type": "disabled"}},
)

# 通过声明式将子agent 集成到 主agent中
agent  = create_deep_agent(
    model = model,
    system_prompt= """你是一位项目协调者。面对复杂任务时：
1. 先用 write_todos 制定计划
2. 将数据收集委派给 data-collector
3. 将分析工作委派给 data-analyzer
4. 将报告撰写委派给 report-writer
5. 整合各子 Agent 的输出，形成最终结果
    """,
    middleware= [TodoListMiddleware()],
    subagents = [search_subagent]
)

for chunk in  agent.stream(
    {"messages":[{"role":"user","content":"LangGraph 目前最新的稳定版本是多少？相比上一个主要版本有哪些值得关注的变化？请给出信息来源。"}]},
    stream_mode = "updates"  # updates 模式每个 chunk 是 {节点名: 更新dict}，匹配下面的遍历写法；
                             # messages 模式的 chunk 是 (消息, metadata) 元组，chunk.items() 会 AttributeError
):
    for node_name, update in chunk.items():
        print(f"\n===== 节点: {node_name} =====")
        # node-style 钩子返回 None = 本次无状态更新（如 PatchToolCalls 无需补齐时），
        # updates 模式下 chunk 会是 {节点名: None}，必须先判空
        if not update:
            print("  （无状态更新）")
            continue
        for msg in update.get("messages", []):
            if getattr(msg, "tool_calls", None):
                for c in msg.tool_calls:
                    print(f"  → 调用工具 [{c['name']}] 参数: {str(c['args'])[:150]}")
            else:
                print(f"  → {msg.__class__.__name__}: {str(msg.content)[:150]}")
        # write_todos 的 Command 会同时更新 todos 键，单独打出来看规划演变
        if "todos" in update:
            for t in update["todos"]:
                print(f"  → todo [{t['status']}] {t['content'][:50]}")



