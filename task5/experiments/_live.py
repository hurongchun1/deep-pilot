"""真实模型实验的公共装配：从 .env 建模型、抓真实请求、打印工具轨迹。

与离线实验的分工：

- 这里**不预设模型的任何回复**，模型必须自己决定读不读 Skill、调不调工具；
- 需要断言的只有"与模型选择无关的事实"（例如首轮请求里不可能有正文，
  或权限拒绝后文件必须原样），模型选不选只是观察结果，打印出来即可；
- 想要逐字复现加载顺序时，仍用 ``experiments/ch07_progressive_disclosure.py``
  的脚本模型，两者互补，不要互相替代。

脚本按 ``python experiments/xxx.py`` 运行；``from _live import ...`` 依赖脚本
目录在 ``sys.path`` 上，因此不要改用 ``-m experiments.xxx``。
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

PROVIDER_ALIASES = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "google_genai",
    "google_genai": "google_genai",
    "gemini": "google_genai",
}

PROVIDER_CREDENTIALS = {
    "openai": ("OPENAI_API_KEY", "OPENAI_API_BASE"),
    "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_API_URL"),
    "google_genai": ("GOOGLE_API_KEY", "GOOGLE_API_BASE"),
}

# `SkillsMiddleware.SKILLS_SYSTEM_PROMPT` 的固定首行；版本升级时改这里。
SKILLS_SECTION_HEADING = "## Skills System"


def build_model(
    *,
    model: str | None = None,
    provider: str | None = None,
    temperature: float | None = None,
):
    """按 .env 的约定构造聊天模型，参数与 task5.agent 保持一致。"""
    raw_provider = (provider or os.getenv("AGENTSEEK_MODEL_PROVIDER") or "openai").strip()
    normalized = PROVIDER_ALIASES.get(raw_provider.replace("-", "_").lower())
    if normalized is None:
        raise SystemExit(f"不支持的 provider: {raw_provider!r}")
    model_name = (model or os.getenv("AGENTSEEK_MODEL") or "deepseek-ai/DeepSeek-V3.2").strip()

    key_name, base_name = PROVIDER_CREDENTIALS[normalized]
    api_key = (os.getenv(key_name) or "").strip()
    if not api_key:
        raise SystemExit(
            f"缺少 {key_name}。先执行 `Copy-Item .env.example .env`，"
            f"填入 {key_name} 后重试（纯离线实验不需要密钥）。"
        )

    kwargs: dict[str, Any] = {"model_provider": normalized, "api_key": api_key}
    base_url = (os.getenv(base_name) or "").strip()
    if base_url:
        kwargs["base_url"] = base_url
    if temperature is not None:
        kwargs["temperature"] = temperature
    if normalized == "openai":
        parallel = (os.getenv("AGENTSEEK_PARALLEL_TOOL_CALLS") or "").strip().lower()
        if parallel in {"true", "false"}:
            kwargs["model_kwargs"] = {"parallel_tool_calls": parallel == "true"}
    return init_chat_model(model=model_name, **kwargs)


def message_text(message: BaseMessage) -> str:
    """取出消息的纯文本。

    0.7.x 的系统提示可能以 content blocks（``[{"type": "text", ...}]``）形式
    挂载，直接 ``str(content)`` 会得到带转义 ``\\n`` 的 repr，行首锚点全部失效。
    优先用 ``.text``，再退回逐块拼接。
    """
    text = getattr(message, "text", None)
    if isinstance(text, str) and text:
        return text
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)


class RequestRecorder(BaseCallbackHandler):
    """记录每次聊天模型**实际收到**的消息，用于核对披露顺序。

    用 ``on_chat_model_start`` 而不是自定义中间件：它在最终系统提示（含
    Skills 段）组装完成之后才触发，且对真实模型和脚本模型都有效。
    """

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def on_chat_model_start(self, serialized, messages, **kwargs):  # noqa: ANN001
        for batch in messages:
            self.requests.append(
                {
                    "context": "\n".join(message_text(m) for m in batch),
                    "tool_ids": {
                        getattr(m, "tool_call_id", None)
                        for m in batch
                        if isinstance(m, ToolMessage)
                    },
                }
            )


def stream_task(graph, task: str, *, thread: str = "ch07-live") -> tuple[RequestRecorder, list[BaseMessage]]:
    """跑一轮任务，边跑边打印模型请求之外的工具轨迹，返回记录与消息。"""
    recorder = RequestRecorder()
    config = {
        "configurable": {"thread_id": thread},
        "callbacks": [recorder],
        "recursion_limit": 24,
    }
    messages: list[BaseMessage] = []
    for chunk in graph.stream(
        {"messages": [{"role": "user", "content": task}]},
        config,
        stream_mode="updates",
    ):
        for update in chunk.values():
            if not isinstance(update, dict):
                continue
            for message in update.get("messages") or []:
                messages.append(message)
                _print_message(message)
    return recorder, messages


def _print_message(message: BaseMessage) -> None:
    if isinstance(message, AIMessage):
        for call in message.tool_calls:
            print(f"  -> {call['name']}({call['args']})  [id={call.get('id')}]")
        text = message_text(message).strip()
        if text:
            print(f"  agent: {_clip(text, lines=4)}")
    elif isinstance(message, ToolMessage):
        status = getattr(message, "status", "success")
        body = message_text(message).strip()
        print(f"  <- {message.name or 'tool'} [{status}] {_clip(body, lines=3)}")


def _clip(text: str, *, lines: int) -> str:
    head = "\n".join(text.splitlines()[:lines])
    return head + ("\n     …" if len(text.splitlines()) > lines else "")


MIN_MARKER_LENGTH = 12


def distinctive_line(text: str, *, exclude: str = "") -> str | None:
    """挑一条只在该文件出现的行。

    不能用第一个标题：``skill-guide`` 的正文标题是"Skills 学习指南"，而它的
    description 里也有同样的字样，拿标题当特征会误判成 Level 2。这里要求长度
    达到下限、且没有在 ``exclude``（frontmatter 或整份 SKILL.md）里出现过。
    """
    for line in text.splitlines():
        candidate = line.strip().lstrip("#").strip()
        if len(candidate) >= MIN_MARKER_LENGTH and candidate not in exclude:
            return candidate
    return None


def skill_markers(skills_root: Path) -> list[dict[str, Any]]:
    """为每个 Skill 提取正文/资源的特征行，用来判断请求走到了第几层。"""
    markers: list[dict[str, Any]] = []
    for skill_md in sorted((skills_root / "skills").glob("*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        frontmatter, _, body = text.removeprefix("---\n").partition("\n---\n")
        resources: dict[str, str | None] = {}
        for sub in ("references", "assets"):
            for path in sorted((skill_md.parent / sub).glob("*")):
                if path.is_file():
                    resources[path.relative_to(skill_md.parent).as_posix()] = distinctive_line(
                        path.read_text(encoding="utf-8"),
                        exclude=text,
                    )
        markers.append(
            {
                "name": skill_md.parent.name,
                "path": f"/skills/{skill_md.parent.name}/SKILL.md",
                "body": distinctive_line(body, exclude=frontmatter),
                "resources": resources,
            }
        )
    return markers


def stage_of(context: str, markers: list[dict[str, Any]]) -> str:
    for marker in markers:
        body = marker["body"]
        if not body or body not in context:
            continue
        if any(heading and heading in context for heading in marker["resources"].values()):
            return "Level 3（正文 + 资源）"
        return "Level 2（正文）"
    return "Level 1（仅元数据）"


def skills_in_prompt(context: str) -> list[str]:
    return re.findall(r"^- \*\*([a-z0-9][a-z0-9-]*)\*\*:", context, flags=re.MULTILINE)


def print_request_summary(recorder: RequestRecorder, markers: list[dict[str, Any]]) -> None:
    print("\n=== 每次模型请求实际收到的内容 ===")
    for index, request in enumerate(recorder.requests, start=1):
        context = request["context"]
        if SKILLS_SECTION_HEADING not in context:
            print(f"第 {index} 次请求：无 Skills 段（子 Agent 请求，或主 Agent 未启用 skills）")
            continue
        names = skills_in_prompt(context)
        print(f"第 {index} 次请求：{stage_of(context, markers)}；技能列表：{', '.join(names) or '（空）'}")


def base_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--task", default=None, help="用户任务；不填则用脚本内置的默认任务")
    parser.add_argument("--model", default=None, help="覆盖 AGENTSEEK_MODEL")
    parser.add_argument("--provider", default=None, help="覆盖 AGENTSEEK_MODEL_PROVIDER")
    parser.add_argument("--skills", nargs="+", default=None, help="Skill 父目录，默认 /skills/")
    parser.add_argument("--thread", default="ch07-live", help="checkpoint 线程 id")
    parser.add_argument("--dry-run", action="store_true", help="只扫描本地 Skill，不调用模型")
    return parser
