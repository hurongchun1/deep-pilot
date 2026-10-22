"""用三个分工明确的子 Agent 演示数据收集、分析和报告编排。"""

import ipaddress
import json
import math
import os
import statistics
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from deepagents import SubAgent, create_deep_agent
from dotenv import load_dotenv
from langchain.agents.middleware import TodoListMiddleware
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from research_find import internet_search



PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"
if not ENV_FILE.is_file():
    raise SystemExit(f"找不到配置文件：{ENV_FILE}")
load_dotenv(ENV_FILE, override=True)

def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"请先在 {ENV_FILE} 中填写 {name}")
    return value

# 优先读取当前 .env 中的 BUB_*；也兼容 .env.example 的 OPENAI_* 配置。
if os.getenv("BUB_API_KEY", "").strip():
    model_key = required_env("BUB_API_KEY")
    model_name = os.getenv("BUB_MODEL", "").strip() or "deepseek-ai/DeepSeek-V3.2"
    base_url = os.getenv("BUB_API_BASE", "").strip() or None
else:
    model_key = required_env("OPENAI_API_KEY")
    model_name = os.getenv("AGENTSEEK_MODEL", "").strip() or "deepseek-ai/DeepSeek-V3.2"
    base_url = os.getenv("OPENAI_API_BASE", "").strip() or None

model = ChatOpenAI(
    model = model_name.removeprefix("openai:"),
    base_url = base_url,
    api_key= model_key,
)


def api_call(url: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    """调用公开的 HTTPS JSON API，返回来源、状态码和响应数据。

    Args:
        url: 公开 API 的完整 HTTPS 地址。
        params: 可选的查询参数，例如 {"limit": "5"}。
    """
    try:
        parsed = urlsplit(url)
    except ValueError:
        return {"error": "API 地址格式不正确"}
    hostname = parsed.hostname or ""
    if parsed.scheme != "https" or not hostname or parsed.username or parsed.password:
        return {"error": "请提供不含账号密码的公开 HTTPS API 地址"}
    if hostname == "localhost" or hostname.endswith(".local"):
        return {"error": "不允许访问本地地址"}
    try:
        if not ipaddress.ip_address(hostname).is_global:
            return {"error": "不允许访问私有或保留 IP 地址"}
    except ValueError:
        pass  # 普通域名由 HTTP 客户端解析。

    try:
        response = httpx.get(url, params=params, timeout=10, follow_redirects=False)
        if response.is_redirect:
            return {"error": "API 返回重定向，请提供最终的 HTTPS 地址", "status_code": response.status_code}
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return {"error": f"API 请求失败或响应不是 JSON：{exc}"}

    serialized = json.dumps(data, ensure_ascii=False)
    return {
        "source": str(response.url),
        "status_code": response.status_code,
        "data": data if len(serialized) <= 10_000 else serialized[:10_000],
        "truncated": len(serialized) > 10_000,
    }


def statistical_analysis(values: list[float], label: str = "数值") -> dict[str, Any]:
    """计算一组数值的数量、均值、中位数、范围和总体标准差。

    Args:
        values: 从来源中提取出的数值列表。
        label: 数值代表的指标名称和单位，例如「延迟（毫秒）」。
    """
    if not values:
        return {"error": "values 不能为空；请先从资料中提取真实数值"}
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in values):
        return {"error": "values 必须全部是有限数字"}
    return {
        "label": label,
        "count": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
        "population_std_dev": statistics.pstdev(values),
    }


def format_document(
    title: str,
    summary: str,
    findings: list[str],
    sources: list[str] | None = None,
) -> str:
    """将已有摘要、发现和来源排版成 Markdown 报告，不生成新事实。

    Args:
        title: 报告标题。
        summary: 基于已收集材料写出的摘要。
        findings: 已核实的关键发现。
        sources: 对应的来源 URL 或资料名称。
    """
    if not title.strip() or not summary.strip() or not any(finding.strip() for finding in findings):
        return "错误：报告标题、摘要和至少一条关键发现不能为空"
    lines = [f"# {title.strip()}", "", "## 摘要", "", summary.strip(), "", "## 关键发现", ""]
    lines.extend(f"{index}. {finding.strip()}" for index, finding in enumerate(findings, 1) if finding.strip())
    if sources:
        lines.extend(["", "## 来源", ""])
        lines.extend(f"- {source.strip()}" for source in sources if source.strip())
    return "\n".join(lines)


subagents: list[SubAgent] = [
    {
        # 三个必要参数：name,description,system_prompt
        "name":"data-collector",
        "description":"从多个来源收集原始数据，包括通过网络搜索和API调用的形式收集信息",
        "system_prompt" :"你是数据收集专家。搜索并整理相关数据，返回结构化的数据摘要",
        "tools":[internet_search,api_call]
    },
    {
        "name":"data-analyzer",
        "description":"对收集到的数据进行统计分析，提取关键信息",
        "system_prompt":"你是数据分析专家。分析数据并提取 3-5 个关键发现，控制在300字以内",
        "tools":[statistical_analysis]
    },
    {
        "name":"report-writer",
        "description":"根据分析结果，撰写一份专业报告",
        "system_prompt":"你是技术写作专家。根据提供的分析结果撰写清晰、专业的报告。",
        "tools":[format_document]
    }
]

# 创建主agent
agent = create_deep_agent(
    model = model,
    system_prompt= """你是一位项目协调者。面对复杂任务时：
1. 先用 write_todos 制定计划
2. 将数据收集委派给 data-collector
3. 将分析工作委派给 data-analyzer
4. 将报告撰写委派给 report-writer
5. 整合各子 Agent 的输出，形成最终结果
    """,
    middleware= [TodoListMiddleware()],
    subagents = subagents
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


