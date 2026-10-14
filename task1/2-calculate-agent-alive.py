"""第 2 轮实验：live 真实模型对照（对应 task1.md 第 2 轮）

与 2-calculate-agent-offline.py 的唯一实验差异：模型从
ScriptedToolChatModel（预设工具调用）换成 ChatOpenAI（deepseek-flash）。
工具、系统提示词、提问方式、check_calculator 验证全部不变——
观察真实模型是否会从对话历史中读取第一次工具的返回值，
串进第二次计算的参数里。

注意：错误注入实验（参数错误 / 工具内部异常透传）需要人为控制
调用参数，属于 offline 手段，见 2-calculate-agent-offline.py
的 run_scripted，本文件不包含。
"""

import json
import math
import os
import re

from langchain.messages import AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langchain_core.tracers.langchain import get_client
from deepagents import create_deep_agent


def calculate(expression: str) -> float:
    """Evaluate a math expression and return the result.

    Args:
        expression: A math expression, e.g. "1 + 2 * 3".
    """
    # 正文用 eval 演示；这里只放行数字和四则运算符号，不把任意代码交给 eval
    if not re.fullmatch(r"[\d\s.+\-*/()]+", expression) or "**" in expression:
        raise ValueError(f"只支持数字、括号和 + - * /：{expression!r}")
    return eval(expression)


def convert_currency(amount: float, from_currency: str, to_currency: str = "CNY") -> dict:
    """Convert an amount from one currency to another.

    Args:
        amount: The amount to convert.
        from_currency: The source currency code, e.g. "USD".
        to_currency: The target currency code, defaults to "CNY".
    """
    # 这里用固定汇率做演示；真实场景可接入汇率 API
    # rates = {"USD": 7.2, "CNY": 1.0, "EUR": 7.8}
    rates = {"USD": 7.0, "CNY": 1.0, "EUR": 7.8}
    cny = amount * rates[from_currency]
    return {"amount": round(cny / rates[to_currency], 2), "currency": to_currency}


# 通过 deepseek 的 OpenAI 兼容接口接入真实模型（live 实验必填模型名称）
model = ChatOpenAI(
    model="deepseek-flash",
    api_key=os.environ["DEEPSEEK_API_KEY"],  # pyright: ignore[reportArgumentType]
    base_url="https://api.deepseek.com/v1",
)
print("模型：", model.model_name, "（live 真实模型）\n")

agent = create_deep_agent(
    model=model,
    tools=[calculate, convert_currency],
    system_prompt="你是一个计算助手，能帮用户做数学运算和货币换算。",
)

result = agent.invoke(
    {"messages": [{"role": "user", "content": "帮我把 100 美元换算成人民币，再用它乘以 1.08 的通胀系数。"}]}
)

print("=====================调用轨迹================================")
for message in result["messages"]:
    if isinstance(message, AIMessage):
        for call in message.tool_calls:
            print("请求", call["name"], call["args"], "ID:", call["id"])
        if not message.tool_calls:
            print("最终回复：", message.content[:80])
    if isinstance(message, ToolMessage):
        print("  返回", message.name, message.status, message.content, "ID:", message.tool_call_id)


print("=====================check_calculator================================")


def check_calculator(messages, amount=100, source="USD", factor=1.08):
    calls, requested_at = {}, {}
    for index, message in enumerate(messages):
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                calls[call["id"]], requested_at[call["id"]] = call, index
    succeeded = [(index, message) for index, message in enumerate(messages)
                 if isinstance(message, ToolMessage) and message.status == "success"
                 and message.tool_call_id in calls and calls[message.tool_call_id]["name"] == message.name]
    converted, converted_at = None, None
    for index, message in succeeded:
        args = calls[message.tool_call_id]["args"]
        if (message.name == "convert_currency" and args.get("amount") == amount
                and args.get("from_currency") == source and args.get("to_currency", "CNY") == "CNY"):
            converted, converted_at = json.loads(message.content), index  # pyright: ignore[reportArgumentType]
    assert converted and converted.get("currency") == "CNY", "没有成功的 100 USD → CNY 换算。"
    expected = converted["amount"] * factor

    later = [message for _, message in succeeded if message.name == "calculate"
             and requested_at[message.tool_call_id] > converted_at]
    assert later, "calculate 应在拿到换算结果之后再请求；同一次请求里同时调用两个工具时，算式还用不上换算结果。"
    chained = [message for message in later if any(
        math.isclose(float(number), converted["amount"])
        for number in re.findall(r"\d+(?:\.\d+)?", str(calls[message.tool_call_id]["args"].get("expression", ""))))]
    assert chained, f"calculate 的算式没有用到换算结果 {converted['amount']}。"
    assert any(math.isclose(float(message.content), expected) for message in chained),  f"calculate 没有算出 {converted['amount']} × {factor} = {expected:g}。" # pyright: ignore[reportArgumentType]
    assert isinstance(messages[-1], AIMessage) and not messages[-1].tool_calls, "缺少最终回复。"
    print(f"已验证：{amount} {source} → {converted['amount']} CNY，× {factor} = {expected:g}")


check_calculator(result["messages"])

# 短命令结束前等待 trace 上传，并关闭 LangSmith 后台线程
if os.getenv("LANGSMITH_TRACING", "").lower() in {"true", "1"}:
    get_client().close(timeout=10)
