"""离线验证读取 Skill 脚本后交给 QuickJS 执行。

当前锁定的 deepagents==0.7.8 要求 langchain-quickjs>=0.3.5；该版本的
CodeInterpreterMiddleware 不再接受 skills_backend，因此本实验不声称
验证 metadata.entrypoint 或 @/skills/... 的自动导入。

在 task5 目录运行：uv run --frozen --extra quickjs python experiments/ch07_interpreter.py
"""

from __future__ import annotations

import os
import sys

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from _scripted import ScriptedModel
from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.backends.utils import create_file_data
from langchain_core.messages import AIMessage, ToolMessage
from langchain_quickjs import CodeInterpreterMiddleware


SKILL_MD = """---
name: order-helpers
description: 整理订单状态时使用。
---

# 订单辅助函数

需要按状态分组时，先读取 `scripts/index.js`，再把函数交给解释器运行。
"""
HELPER_JS = """function groupByStatus(orders) {
  return orders.reduce((groups, order) => {
    (groups[order.status] ??= []).push(order.id);
    return groups;
  }, {});
}
"""


def main() -> None:
    model = ScriptedModel(
        replies=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_file",
                        "args": {"file_path": "/skills/order-helpers/scripts/index.js"},
                        "id": "read-helper",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "eval",
                        "args": {
                            "code": HELPER_JS
                            + "\nconsole.log(JSON.stringify(groupByStatus(["
                            "{id:'A',status:'new'},{id:'B',status:'done'},"
                            "{id:'C',status:'new'}])));"
                        },
                        "id": "run-helper",
                    }
                ],
            ),
            AIMessage(content="已按状态分组。"),
        ]
    )
    backend = StateBackend()
    graph = create_deep_agent(
        model=model,
        backend=backend,
        skills=["/skills/"],
        middleware=[CodeInterpreterMiddleware()],
    )
    result = graph.invoke(
        {
            "messages": [{"role": "user", "content": "按状态分组订单。"}],
            "files": {
                "/skills/order-helpers/SKILL.md": create_file_data(SKILL_MD),
                "/skills/order-helpers/scripts/index.js": create_file_data(HELPER_JS),
            },
        }
    )
    outputs = [str(m.content) for m in result["messages"] if isinstance(m, ToolMessage) and m.name == "eval"]
    reads = [str(m.content) for m in result["messages"] if isinstance(m, ToolMessage) and m.name == "read_file"]
    assert reads and "groupByStatus" in reads[0], "没有读到 Skill 脚本"
    assert outputs, "解释器没有返回工具结果"
    assert '"new":["A","C"]' in outputs[0], outputs[0]
    assert '"done":["B"]' in outputs[0], outputs[0]
    print("解释器：读取 Skill 中的 JS helper，交给 QuickJS 后得到确定的订单分组。")
    print("PASS：脚本读取与 CodeInterpreterMiddleware 执行实验通过。")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
