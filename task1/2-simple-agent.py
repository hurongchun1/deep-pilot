import os
from langchain_core.messages import ToolMessage,AIMessage
from langchain_openai import ChatOpenAI
from langchain_core.tracers.langchain import get_client
from deepagents import create_deep_agent


# 通过deepseek的openAI方式接入模型
model = ChatOpenAI(
    model= "deepseek-flash",
    api_key= os.environ["DEEPSEEK_API_KEY"],  # pyright: ignore[reportArgumentType]
    base_url="https://api.deepseek.com/v1"
)

# 实现获取天气状态工具
def get_weather(city:str) -> str:
    """
    获取城市名称，返回城市的实时天气情况
    """
    return f"{city} 阳光明媚"

# 将模型，工具，系统提示词整合到agent中
agent = create_deep_agent(
    model = model,
    tools= [get_weather],
    system_prompt="你是一个乐于助人的助手"
)


# 运行信息得出结果
# 标准的消息格式：
# {"messages": [{"role": "user", "content": "你的问题"}]}
result = agent.invoke(
    {"messages":[
        {"role":"user","content":"今天北京的天气怎么样"}
    ]}
)


# 打印结果
print(result["messages"][-1].content)

# 意味着 deep agent 里面自带files特性(虚拟文件系统)框架中自带的文件读写工具
print("状态中的键：", sorted(result))# 状态中的键： ['files', 'messages']


print("消息条数：", len(result["messages"]))

"""
这里是将AI的message属性值打印出来
message.type    消息角色(human/ai/tool)
:<5     左对齐并补空格到5字符宽
type(message).__name__      类名，如 HumanMessage、AIMessage、ToolMessage
[:80]       内容截取80个字符
"""
for index, message in enumerate(result["messages"]):
    print(f"[{index}] {message.type:<5} {type(message).__name__:<12} {str(message.content)[:80]}")
    if isinstance(message, AIMessage):
        for call in message.tool_calls:
            print("      请求工具:", call["name"], "参数:", call["args"], "调用 ID:", call["id"])
    if isinstance(message, ToolMessage):
        print("      回应调用 ID:", message.tool_call_id, "工具:", message.name, "状态:", message.status)


def check_weather(messages, city=("北京", "Beijing")):
    # 收集模型对 get_weather 的所有调用
    calls = {call["id"]: call for message in messages if isinstance(message, AIMessage)
             for call in message.tool_calls if call["name"] == "get_weather"}
    # 断言模型必须真调用了工具
    assert calls, "模型没有请求 get_weather。"
    # 查询的城市必须正确
    accepted = {name.casefold() for name in city}
    asked = [str(call["args"].get("city", "")) for call in calls.values()]
    calls = {call_id: call for call_id, call in calls.items()
             if str(call["args"].get("city", "")).strip().casefold() in accepted}
             
    assert calls, f"get_weather 查询的是 {asked}，不是题目要求的城市（{' / '.join(city)}）。"
    # 工具结果必须正确关联、且执行成功
    answered = [message for message in messages if isinstance(message, ToolMessage)
                and message.tool_call_id in calls and message.name == "get_weather"
                and message.status == "success"
                and message.content == f"{calls[message.tool_call_id]['args'].get('city')} 阳光明媚"]
    assert answered, "get_weather 没有成功返回与请求参数对应的结果。"
    assert isinstance(messages[-1], AIMessage) and not messages[-1].tool_calls and messages[-1].content, \
        "缺少最终回复。"
    print("已验证 get_weather 的请求、调用关联、成功状态与返回值：", answered[-1].content)


check_weather(result["messages"])

# 今天北京天气**阳光明媚** ☀️

# 适合出门活动，不过晴天紫外线可能较强，建议做好防晒、多补充水分。如果需要了解气温、风力等更详细的信息，可以告诉我 ，我再帮你查询。
# 状态中的键： ['files', 'messages']
# 消息条数： 4
# [0] human HumanMessage 今天北京的天气怎么样
# [1] ai    AIMessage
#       请求工具: get_weather 参数: {'city': '北京'} 调用 ID: call_00_p4Ann1a3xpVRp4aBN3xJ0807
# [2] tool  ToolMessage  北京 阳光明媚
#       回应调用 ID: call_00_p4Ann1a3xpVRp4aBN3xJ0807 工具: get_weather 状态: success
# [3] ai    AIMessage    今天北京天气**阳光明媚** ☀️

# 适合出门活动，不过晴天紫外线可能较强，建议做好防晒、多补充水分。如果需要了解气温、风力等更详细的信息，可以告诉我 ，我再帮你
# 已验证 get_weather 的请求、调用关联、成功状态与返回值： 北京 阳光明媚


'''
总结：

HumanMessage(人类输入)：这是人类输入问题的message。Agent运行时第一条消息。
AIMessage(模型输出)：模型输出时产生的 message。它的content存放文字回复：当模型决定调用工具时，调用请求放在tool_calls属性里（工具名、参数、调用ID）
ToolMessage（工具执行结果）：代表模型调用一次工具后，工具执行完毕回填的消息。

在状态中的键： ['files', 'messages']可以得知
deep agent的特点：
deep agent内置了 files 虚拟文件系统工具，因此返回状态字典的时候，还会多出一个 files键
'''