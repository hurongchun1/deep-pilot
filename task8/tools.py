"""通用任务规划助手的资料、文件和结构检查工具。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from langchain_core.tools import tool

PROJECT_ROOT = Path(__file__).resolve().parent
REQUIRED_HEADINGS = (
    "任务目标", "已知条件", "行动步骤", "验收标准", "风险与调整",
    "待确认事项", "信息来源",
)


def _inside(*parts: str) -> Path:
    root = PROJECT_ROOT.resolve()
    target = root.joinpath(*parts).resolve()
    if not target.is_relative_to(root):
        raise ValueError("路径必须位于项目目录内")
    return target


def _plan_path(slug: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", slug):
        raise ValueError("slug 只能包含小写字母、数字、连字符或下划线")
    return _inside("artifacts", f"{slug}.md")


@tool
def list_sources() -> str:
    """列出 sources/ 下可选的 Markdown 补充资料；不要求每个任务都读取。"""
    folder = _inside("sources")
    names = sorted(path.name for path in folder.glob("*.md")
                   if path.is_file() and path.resolve().is_relative_to(folder.resolve()))
    return json.dumps(names, ensure_ascii=False)


@tool
def read_source(name: str) -> str:
    """读取 sources/ 中的一份 Markdown 补充资料，文件名从 list_sources 获取。"""
    if not re.fullmatch(r"[^/\\]+\.md", name) or name in {"..", "."}:
        raise ValueError("name 必须是 sources/ 下的 Markdown 文件名")
    return _inside("sources", name).read_text(encoding="utf-8")


@tool
def save_plan(slug: str, content: str) -> str:
    """将 Markdown 行动计划保存为 artifacts/<slug>.md。"""
    if not content.strip():
        raise ValueError("计划内容不能为空")
    target = _plan_path(slug)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"已保存 artifacts/{slug}.md"


@tool
def read_plan(slug: str) -> str:
    """读回 artifacts/<slug>.md 中已保存的行动计划。"""
    return _plan_path(slug).read_text(encoding="utf-8")


@tool
def check_plan(slug: str) -> str:
    """仅检查已保存计划的必要章节及非空正文，不评估可执行性或事实准确性。"""
    content = _plan_path(slug).read_text(encoding="utf-8")
    sections = {}
    matches = list(re.finditer(r"(?m)^(#{1,6})[ \t]+([^\r\n]+)[ \t]*$", content))
    for index, match in enumerate(matches):
        end = next((following.start() for following in matches[index + 1:]
                    if len(following.group(1)) <= len(match.group(1))), len(content))
        body = content[match.end():end]
        # 子标题下的正文也属于本节，但只有子标题仍算空章节。
        body = re.sub(r"(?m)^#{1,6}[ \t]+[^\r\n]*$", "", body)
        sections[match.group(2).strip()] = body.strip()
    missing = [heading for heading in REQUIRED_HEADINGS if heading not in sections]
    empty = [heading for heading in REQUIRED_HEADINGS
             if heading in sections and not sections[heading]]
    return json.dumps({"ok": not missing and not empty, "missing": missing, "empty": empty,
                       "path": f"artifacts/{slug}.md"}, ensure_ascii=False)


@tool
def save_preference(key: str, value: str) -> str:
    """仅保存用户明确要求记住的语言、语气或格式偏好。"""
    if key not in {"language", "tone", "format"}:
        return "参数错误：key 只能填写英文标识 language、tone 或 format；请改正后重试。"
    value = value.strip()
    if not value or len(value) > 200 or "\n" in value or "\r" in value:
        return "参数错误：value 必须是不超过 200 字符的非空单行文本；请改正后重试。"
    target = _inside("memory", "preferences.md")
    entries: dict[str, str] = {}
    if target.exists():
        for line in target.read_text(encoding="utf-8").splitlines():
            if ": " in line and not line.startswith("#"):
                name, old_value = line.split(": ", 1)
                if name in {"language", "tone", "format"}:
                    entries[name] = old_value
    entries[key] = value
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# 已保存的偏好\n\n" +
                      "".join(f"{name}: {entries[name]}\n" for name in sorted(entries)),
                      encoding="utf-8")
    return target.read_text(encoding="utf-8")
