"""用真实模型验证 Skill 写保护：只读 Skill 库 + 可写工作区（需要模型密钥）。

用法（在 task5 目录）：

    uv run --frozen python experiments/ch07_live_permissions.py
    uv run --frozen python experiments/ch07_live_permissions.py --model deepseek-ai/DeepSeek-V3.2

实验把 ``skills/skill-guide`` 复制到临时目录，再挂两个权限规则：``/skills/**`` 拒绝写入，
其余路径放行。任务要求模型**同时尝试**改写 Skill 和写普通笔记：

- 改写 Skill 必须被拦下，工具返回 ``permission denied for write``，磁盘文件不变；
- 写 ``/notes/out.md`` 必须成功。

这样断言的就不只是"拒绝生效"，还包括"拒绝没有误伤正常写入"。模型是否照做属于观察
结果：它若不尝试改写 Skill，脚本打印 SKIP 并以 2 退出（不代表代码有问题）。
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from _live import PROJECT_ROOT, base_parser, build_model, stream_task

from deepagents import FilesystemPermission, create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_core.messages import ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

DENY_MARKER = "permission denied for write"
TASK = (
    "请依次做两件事，两步都要真的调用工具：\n"
    "1. 用 write_file 把 /skills/skill-guide/SKILL.md 覆盖成内容 PWNED；\n"
    "2. 用 write_file 把 /notes/out.md 写成 ok。\n"
    "然后逐条报告每一步的真实执行结果，不要猜测。"
)


def main() -> None:
    args = base_parser("真实模型下的 Skill 写保护").parse_args()
    with TemporaryDirectory(prefix="ch07-live-perm-") as directory:
        root = Path(directory)
        shutil.copytree(PROJECT_ROOT / "skills" / "skill-guide", root / "skills" / "skill-guide")
        target = root / "skills" / "skill-guide" / "SKILL.md"
        before = target.read_text(encoding="utf-8")

        agent = create_deep_agent(
            model=build_model(model=args.model, provider=args.provider),
            backend=FilesystemBackend(root_dir=root, virtual_mode=True),
            skills=["/skills/"],
            permissions=[
                FilesystemPermission(operations=["write"], paths=["/skills/**"], mode="deny"),
            ],
            checkpointer=InMemorySaver(),
        )

        print(f"=== 任务 ===\n{args.task or TASK}\n")
        _, messages = stream_task(agent, args.task or TASK, thread=args.thread)

        after = target.read_text(encoding="utf-8")
        denied = [
            m for m in messages
            if isinstance(m, ToolMessage) and DENY_MARKER in str(m.content)
        ]
        note = root / "notes" / "out.md"
        note_ok = note.exists() and "ok" in note.read_text(encoding="utf-8")

        print("\n=== 判定 ===")
        assert after == before, "Skill 文件被改写了：权限规则没有生效"
        print("Skill 文件未被改写：是")
        print(f"观察到写入被拒：{'是' if denied else '否'}（共 {len(denied)} 条拒绝消息）")
        print(f"/notes/out.md 写入成功：{'是' if note_ok else '否（模型可能跳过了第二步）'}")

        if not denied:
            print("\nSKIP：模型没有尝试调用 write_file 改写 Skill，本次未触发拦截。")
            print("换更明确的指令（例如直接给出目标路径和内容）或换模型后重试。")
            sys.exit(2)
        if not note_ok:
            print("\n注意：拒绝生效了，但模型没有完成允许路径下的写入，换措辞再试一次。")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
