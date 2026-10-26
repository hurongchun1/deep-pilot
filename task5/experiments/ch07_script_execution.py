"""离线验证 Agent 读取并执行 Skill 脚本，记录本地 shell 与沙箱的边界。

本实验使用 LocalShellBackend，它在宿主机执行命令，不提供容器隔离。
在 task5 目录运行：uv run --frozen python experiments/ch07_script_execution.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from _scripted import ScriptedModel
from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from langchain_core.messages import AIMessage, ToolMessage


SKILL_MD = """---
name: order-normalizer
description: 统计订单状态时使用。
---

# 订单统计

需要统计订单状态时，运行 `scripts/count_orders.py`，读取标准输出中的 JSON。
"""
SCRIPT = """import json
from collections import Counter

orders = [{"id": "A", "status": "new"}, {"id": "B", "status": "done"}, {"id": "C", "status": "new"}]
print(json.dumps(dict(Counter(order["status"] for order in orders)), sort_keys=True))
"""


def main() -> None:
    with TemporaryDirectory(prefix="ch07-script-") as directory:
        root = Path(directory)
        skill_root = root / "skills" / "order-normalizer"
        script_path = skill_root / "scripts" / "count_orders.py"
        script_path.parent.mkdir(parents=True)
        (skill_root / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
        script_path.write_text(SCRIPT, encoding="utf-8")

        command = f'"{sys.executable}" "skills/order-normalizer/scripts/count_orders.py"'
        model = ScriptedModel(
            replies=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "read_file",
                            "args": {"file_path": "/skills/order-normalizer/SKILL.md"},
                            "id": "read-skill",
                        }
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "execute", "args": {"command": command}, "id": "run-script"}
                    ],
                ),
                AIMessage(content="已统计订单。"),
            ]
        )
        graph = create_deep_agent(
            model=model,
            backend=LocalShellBackend(root_dir=root, virtual_mode=True),
            skills=["/skills/"],
        )
        result = graph.invoke({"messages": [{"role": "user", "content": "统计订单状态。"}]})
        output = [
            str(m.content)
            for m in result["messages"]
            if isinstance(m, ToolMessage) and m.name == "execute"
        ]
        assert output and '"done": 1' in output[0] and '"new": 2' in output[0], output
        print("Agent 读取 Skill 后，通过 execute 运行脚本并收到 JSON 标准输出。")
        print("注意：LocalShellBackend 在宿主机执行；本实验不验证容器沙箱隔离。")
        print("PASS：Skill 脚本调用链通过。")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
