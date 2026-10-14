import re
import json
import math

from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain.messages import AIMessage,ToolMessage
from deepagents import create_deep_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel 


class ScriptedToolChatModel(FakeMessagesListChatModel):
    """预设回复序列的假模型。

    Agent 工厂调用模型前会执行 bind_tools（真实模型需要把工具 schema 发给 API），
    但假模型的回复已写死，不需要真绑定，直接返回自身即可。
    """

    def bind_tools(self, tools, **kwargs):
        return self


def calculate(expression: str) -> float:
    """Evaluate a math expression and return the result.

    Args:
        expression: A math expression, e.g. "1 + 2 * 3".
    """
    # 正文用 eval 演示；这里只放行数字和四则运算符号，不把任意代码交给 eval
    if not re.fullmatch(r"[\d\s.+\-*/()]+", expression) or "**" in expression:
        raise ValueError(f"只支持数字、括号和 + - * /：{expression!r}")
    return eval(expression)

print("============convert_currency==============")
def convert_currency(amount: float, from_currency: str, to_currency: str = "CNY") -> dict:
    """Convert an amount from one currency to another.

    Args:
        amount: The amount to convert.
        from_currency: The source currency code, e.g. "USD".
        to_currency: The target currency code, defaults to "CNY".
    """
    # 这里用固定汇率做演示；真实场景可接入汇率 API
    rates = {"USD": 7.2, "CNY": 1.0, "EUR": 7.8}
    # rates = {"USD": 7.0, "CNY": 1.0, "EUR": 7.8}
    cny = amount * rates[from_currency]
    return {"amount": round(cny / rates[to_currency], 2), "currency": to_currency}


print("直接调用函数：", calculate("1 + 2 * 3"), convert_currency(100, "USD"))

schemas = {}
for fn in (calculate, convert_currency):
    schema = convert_to_openai_tool(fn)["function"]
    schemas[schema["name"]] = schema
    params = schema["parameters"]
    print(f"工具 {schema['name']}：{schema['description']}")
    print("  必填参数：", params.get("required", []))
    for name, spec in params["properties"].items():
        default = f"，默认值 {spec['default']!r}" if "default" in spec else ""
        print(f"  - {name}: {spec['type']}{default}；{spec.get('description', '')}")

currency = schemas["convert_currency"]["parameters"]
assert currency["properties"]["amount"]["type"] == "number"      # 类型标注 float → number
assert currency["required"] == ["amount", "from_currency"]      # 有默认值的参数不必填
assert currency["properties"]["to_currency"]["default"] == "CNY"
print("\n已验证：类型标注、docstring 与默认值都进入了工具 Schema。")

calc_model = ScriptedToolChatModel(responses=[
    AIMessage(content="", tool_calls=[{
        "name": "convert_currency", "args": {"amount": 100, "from_currency": "USD"},
        "id": "ch02-convert",
    }]),
    AIMessage(content="", tool_calls=[{
        "name": "calculate", "args": {"expression": "720.0 * 1.08"}, "id": "ch02-calculate",
    }]),
    AIMessage(content="（脚本预设回复）换算与计算已完成，结果见工具返回。"),
])
calc_agent = create_deep_agent(
    model=calc_model,
    tools=[calculate, convert_currency],
    system_prompt="你是一个计算助手，能帮用户做数学运算和货币换算。",
)

calc_result = calc_agent.invoke(
    {"messages": [{"role": "user", "content": "帮我把 100 美元换算成人民币，再用它乘以 1.08 的通胀系数。"}]}
)

for message in calc_result["messages"]:
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


check_calculator(calc_result["messages"])

print("=====================run_scripted================================")
def run_scripted(tool_call):
    model = ScriptedToolChatModel(responses=[
        AIMessage(content="", tool_calls=[tool_call]),
        AIMessage(content="（脚本预设回复）结束。"),
    ])
    agent = create_deep_agent(model=model, tools=[calculate, convert_currency])
    return agent.invoke({"messages": [{"role": "user", "content": "换算"}]})

# 实验A
# bad_type = run_scripted({"name": "convert_currency", "id": "ch02-bad-type",
#                          "args": {"amount": "a lot", "from_currency": "USD"}})
# error_message = next(m for m in bad_type["messages"] if isinstance(m, ToolMessage))
# print("状态：", error_message.status)
# print("内容：", error_message.content)
# assert error_message.status == "error" and "amount" in error_message.content

try:
    # 实验B
    run_scripted({"name": "convert_currency", "id": "ch02-unknown-currency",
                  "args": {"amount": 1, "from_currency": "JPY"}})
except KeyError as error:
    print("\n函数内部异常中断了 invoke()：KeyError", error)
else:
    raise AssertionError("预期 rates['JPY'] 抛出 KeyError。")