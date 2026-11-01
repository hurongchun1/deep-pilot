"""上线计划助手的资料、文件和结构检查工具。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from langchain_core.tools import tool

PROJECT_ROOT = Path(__file__).resolve().parent
SOURCE_NAMES = {"product-brief.md", "release-constraints.md"}
REQUIRED_HEADINGS = (
    "发布目标", "输入依据", "发布步骤", "验收指标", "回滚预案",
    "风险与负责人", "资料来源",
)
REQUIRED_MARKERS = (
    "sources/product-brief.md", "sources/release-constraints.md",
    "10%", "50%", "100%", "回滚",
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
def read_source(name: str) -> str:
    """按准确文件名读取 sources/ 中的一份产品发布资料。"""
    if name not in SOURCE_NAMES:
        raise ValueError(f"未知的资料文件：{name}")
    return _inside("sources", name).read_text(encoding="utf-8")


@tool
def save_plan(slug: str, content: str) -> str:
    """将 Markdown 上线计划保存为 artifacts/<slug>.md。"""
    if not content.strip():
        raise ValueError("计划内容不能为空")
    target = _plan_path(slug)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"已保存 artifacts/{slug}.md"


@tool
def read_plan(slug: str) -> str:
    """读回 artifacts/<slug>.md 中已保存的上线计划。"""
    return _plan_path(slug).read_text(encoding="utf-8")


@tool
def check_plan(slug: str) -> str:
    """检查已保存计划的章节、资料来源和灰度阶段文本。"""
    content = _plan_path(slug).read_text(encoding="utf-8")
    missing = [heading for heading in REQUIRED_HEADINGS
               if not re.search(rf"(?m)^#{{1,3}}\s+{re.escape(heading)}\s*$", content)]
    missing.extend(marker for marker in REQUIRED_MARKERS if marker not in content)
    return json.dumps({"ok": not missing, "missing": missing,
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
