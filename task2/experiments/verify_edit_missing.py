"""验证 edit_file 对不存在文件的行为。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ch03_lab import ScriptedModel, call, done, show_tools
from deepagents import create_deep_agent

model = ScriptedModel(
    replies=[
        # 对不存在的文件执行编辑
        call(
            "edit_file",
            {"file_path": "/notes/ghost.md", "old_string": "old", "new_string": "new"},
            "edit-missing",
        ),
        # 对照组：先创建再编辑
        call("write_file", {"file_path": "/notes/real.md", "content": "old text"}, "write"),
        call(
            "edit_file",
            {"file_path": "/notes/real.md", "old_string": "old", "new_string": "new"},
            "edit-existing",
        ),
        done(),
    ]
)
agent = create_deep_agent(model=model)
result = agent.invoke({"messages": [{"role": "user", "content": "测试编辑不存在的文件"}]})
show_tools(result)
print("\nState 中的文件：", list(result.get("files", {})))
