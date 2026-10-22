from pathlib import Path
from typing import Any, Literal

import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from deepagents import SubAgent
from tavily import TavilyClient

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"  # experiment/ 的上一级 = task4/
load_dotenv(ENV_FILE)

# 定义一个类，用于存储输出的结构化信息
class ResearchFind(BaseModel):
    # 输入三个参数：摘要，置信度，信息来源
    summary: str = Field(...,description="摘要")
    confidence: float = Field(...,description="置信度")
    source: str  = Field(...,description="信息来源")

client = TavilyClient(os.environ["TAVILY_API_KEY"])

# 创建搜索功能
def internet_search(query: str,
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


# 通过字典式来生成子agent
# 加 SubAgent 注解：让字典字面量对着 TypedDict 做逐键检查，
# 否则推断出的类型是普通 dict[str, 联合值]，无法传给 create_deep_agent 的 subagents
search_subagent: SubAgent = {
    "name" : "search_subagent",
    "description" : "用于联网搜索某些特定领域的信息，最后返回结构化的内容",
    "tools": [internet_search],
    "response_format": ResearchFind,
    "system_prompt":"""你是一位研究员。
    工具使用指导：
    - 用 internet_search 搜索信息，每次查询不同的关键词
    - 搜索 3-5次 以获取全面的信息

    输出格式：
    - 摘要（2-3段）
    - 关键发现（要点列表）
    - 信息来源（附 URL）
    重点：返回结果控制在500字以内
    """
}
