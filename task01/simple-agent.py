import os
from deepagents.middleware.skills import SKILLS_SYSTEM_PROMPT
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
def get_weather(city_name:str) -> str:
    """
    获取城市名称，返回城市的实时天气情况
    """
    return f"{city_name} 阳光明媚"

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

# 短命令结束前等待 trace 上传，并关闭 LangSmith 后台线程
if os.getenv("LANGSMITH_TRACING", "").lower() in {"true", "1"}:
    get_client().close(timeout=10)
