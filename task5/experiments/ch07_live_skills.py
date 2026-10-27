"""用真实模型观察 Skill 的三层加载（需要 .env 里的模型密钥）。

用法（在 task5 目录）：

    Copy-Item .env.example .env      # 填 OPENAI_API_KEY，按需改 OPENAI_API_BASE
    uv run --frozen python experiments/ch07_live_skills.py
    uv run --frozen python experiments/ch07_live_skills.py --task "..." --skills /skills/
    uv run --frozen python experiments/ch07_live_skills.py --dry-run   # 不调用模型

这个脚本不预设模型回复：模型是否先读 SKILL.md、读完正文是否再读 references/assets，
都由模型自己决定。脚本只打印"每次请求实际收到了什么"和"它调用了什么"，并断言一条
与模型选择无关的事实：**首轮请求里不可能出现任何 Skill 正文或资源内容**。

想逐字复现加载顺序，用离线脚本 ch07_progressive_disclosure.py；那个脚本用预设调用
证明机制，这个脚本用真实调用观察行为，两者结论不能互相替代。
"""

from __future__ import annotations

import sys

from _live import (
    PROJECT_ROOT,
    SKILLS_SECTION_HEADING,
    base_parser,
    build_model,
    print_request_summary,
    skill_markers,
    stage_of,
    stream_task,
)

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

DEFAULT_TASK = "请写一份关于Deep Agent Skill.md 三层加载是怎么回事。"


def main() -> None:
    args = base_parser("真实模型下的 Skill 三层加载观察").parse_args()
    skills = args.skills or ["/skills/"]
    markers = skill_markers(PROJECT_ROOT)

    print("=== 本地可发现的 Skill ===")
    for marker in markers:
        resources = ", ".join(marker["resources"]) or "（无）"
        body = (marker["body"] or "")[:40]
        print(f"{marker['name']}: 正文特征行={body!r}；资源={resources}")
    print(f"\n配置的 Skill 源：{skills}")
    if args.dry_run:
        print("\n--dry-run：只扫描本地文件，没有调用模型，也没有创建 Agent。")
        return

    agent = create_deep_agent(
        model=build_model(model=args.model, provider=args.provider),
        backend=FilesystemBackend(root_dir=PROJECT_ROOT, virtual_mode=True),
        skills=skills,
        checkpointer=InMemorySaver(),
    )

    task = args.task or DEFAULT_TASK
    print(f"\n=== 任务 ===\n{task}\n")
    recorder, messages = stream_task(agent, task, thread=args.thread)

    print_request_summary(recorder, markers)

    # 与模型选择无关：Skills 中间件在首轮只注入元数据，正文/资源必须靠工具返回。
    skills_requests = [r for r in recorder.requests if SKILLS_SECTION_HEADING in r["context"]]
    assert skills_requests, "没有任何请求包含 Skills 段，检查 skills= 参数是否指向 Skill 的父目录"
    first_stage = stage_of(skills_requests[0]["context"], markers)
    assert first_stage == "Level 1（仅元数据）", f"首轮就泄漏了正文/资源：{first_stage}"

    read_paths = [
        call["args"].get("file_path", "")
        for message in messages
        if isinstance(message, AIMessage)
        for call in message.tool_calls
        if call["name"] == "read_file"
    ]
    read_skill = any(path.endswith("/SKILL.md") for path in read_paths)
    read_resource = any("/references/" in path or "/assets/" in path for path in read_paths)

    final = next((m for m in reversed(messages) if isinstance(m, AIMessage) and m.content), None)
    print("\n=== 判定 ===")
    print(f"首轮只有元数据：是（{first_stage}）")
    print(f"模型自行读取 SKILL.md：{'是' if read_skill else '否'}")
    print(f"模型继续读取 references/assets：{'是' if read_resource else '否'}")
    if not read_skill:
        print("注意：模型没选这个 Skill。这是模型选择的结果，不是加载机制失败；换任务措辞或换模型再试。")
    if final is not None:
        print(f"最终回答开头：{str(final.content).strip()[:200]}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
