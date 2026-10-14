import os
from typing import Any, Literal
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from langchain.agents.middleware import TodoListMiddleware
from deepagents import create_deep_agent
from tavily import TavilyClient

# 通过deepseek的openAI方式接入模型
model = ChatOpenAI(
    model= "deepseek-flash",
    api_key= os.environ["DEEPSEEK_API_KEY"],  # pyright: ignore[reportArgumentType]
    base_url="https://api.deepseek.com/v1"
)

# 创建 Tavily 联网搜索工具
# 创建 Tavily 客户端
client = TavilyClient(os.environ["TAVILY_API_KEY"])

def search_tool(query: str,
    max_results: int =10,
    topic:Literal["general","news","finance"] = "general",
    include_raw_conntent: bool = False,
    ) -> dict[Any, Any]:
    """
    基于请求的内容得到相关联网搜索的内容

    Args:
        query: 请求内容
        max_results: 返回的结果数量
        topic: 搜索的主题，默认为 general
        include_raw_conntent: 是否包含原始内容，默认为 False
    """
    return client.search(
        query = query,
        search_depth= "basic",
        max_results = max_results,
        topic = topic,
        include_raw_content = include_raw_conntent,
    )

# 定义提示词
system_prompt = """你是一名严谨的研究助手，擅长通过联网搜索收集信息并撰写结构化研究报告。

工作流程：
1. 明确用户的研究问题，拆解出需要查证的关键点。
2. 使用联网搜索工具检索权威、最新的信息（优先官方文档、一手来源，交叉验证后再采信）。
3. 将检索到的内容整理归纳，剔除无关、重复或不可靠信息。
4. 基于可靠信息撰写研究报告，并对关键结论标注信息来源。

研究报告格式：
- 标题：一句话概括主题
- 摘要：3~5 句话总结核心结论
- 正文：分小节展开，论点清晰、论据充分
- 结论：总结要点，可给出行动建议或展望
- 参考来源：列出引用的链接

原则：
- 不臆测、不编造；搜索不到的信息要如实说明。
- 信息冲突时列出不同说法并说明取舍理由。
- 语气客观中立，结论有据可依。
"""

# 工具整合到Agent
agent = create_deep_agent(
    model = model,
    tools = [search_tool],
    system_prompt=system_prompt,
    # middleware = [TodoListMiddleware()]
)

# 验证注册工具
registered =  sorted(agent.nodes["tools"].bound.tools_by_name)
print("已注册的工具：",registered)
assert {"search_tool","write_todos","write_file"} <= set(registered)

# 运行结果
result = agent.invoke(
    {"messages": [{"role": "user", "content": "什么是 LangGraph？"}]}
)

print(result["messages"][-1].content)
