"""第 9 章真实模型进阶实验：条件审批与文件系统路径审批。

两个案例分别验证：
1. interrupt_on 的 when 谓词只拦截 /protected/ 路径，普通路径自动执行。
2. FilesystemPermission(mode="interrupt") 在受保护文件写入前暂停。
所有副作用仅发生在内存列表或临时目录，不涉及真实业务系统。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from deepagents import FilesystemPermission, create_deep_agent
from deepagents.backends import FilesystemBackend
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.tools import tool
from langchain_core.tracers.langchain import wait_for_all_tracers
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from langsmith import Client, trace, tracing_context


# 与 live_hitl.py 一样，从 task7/.env 或 shell 环境取模型与追踪配置。
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def main() -> None:
    """让真实模型提出工具调用，再检查审批边界是否控制了实际副作用。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=os.getenv("LANGSMITH_PROJECT") or "deep-pilot-task7")
    args = parser.parse_args()
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    model_name = (os.getenv("AGENTSEEK_MODEL") or "").strip()
    if not key or not model_name or not (os.getenv("LANGSMITH_API_KEY") or "").strip():
        raise SystemExit("需要 OPENAI_API_KEY、AGENTSEEK_MODEL、LANGSMITH_API_KEY")
    if (os.getenv("AGENTSEEK_MODEL_PROVIDER") or "openai") != "openai":
        raise SystemExit("此实验使用 openai / OpenAI 兼容接口配置")
    model_kwargs = {"model_provider": "openai", "api_key": key, "temperature": 0}
    if base := (os.getenv("OPENAI_API_BASE") or "").strip():
        model_kwargs["base_url"] = base
    model = init_chat_model(model=model_name, **model_kwargs)
    client = Client()

    with tracing_context(enabled=True, project_name=args.project, client=client):
        with trace(
            "ch09-live-boundaries", run_type="chain",
            inputs={"cases": ["conditional", "filesystem-permission"]},
            tags=["task7", "ch09", "conditional", "permissions"],
        ) as root:
            # 第一组：自定义工具仅在 path 以 /protected/ 开头时需要人工审查。
            changes: list[tuple[str, str]] = []

            @tool
            def record_change(path: str, content: str) -> str:
                """把一条文件变更记录到本地列表；用于观察审批前后是否执行。"""
                changes.append((path, content))
                return f"记录完成：{path}"

            def needs_review(request) -> bool:
                """ToolCallRequest 中保留模型提出的原始参数。"""
                return str(request.tool_call["args"].get("path", "")).startswith("/protected/")

            conditional_agent = create_deep_agent(
                model=model,
                tools=[record_change],
                interrupt_on={
                    "record_change": {
                        "allowed_decisions": ["approve", "reject"],
                        "when": needs_review,
                    }
                },
                checkpointer=InMemorySaver(),
                system_prompt="按用户要求调用 record_change 一次。若审批拒绝，不要重试。",
            )
            safe_config = {"configurable": {"thread_id": f"safe-{uuid4().hex[:8]}"}}
            safe = conditional_agent.invoke(
                {"messages": [{"role": "user", "content":
                    "调用 record_change(path='/workspace/safe.txt', content='SAFE_MARKER')，只调用一次。"}]},
                config=safe_config, version="v2",
            )
            assert not safe.interrupts, "普通工作区路径不应触发审批"
            assert changes == [("/workspace/safe.txt", "SAFE_MARKER")]
            print("条件中断：/workspace/ 自动执行")

            # 相同工具换成受保护路径，应在追加第二条执行记录前暂停。
            protected_config = {"configurable": {"thread_id": f"protected-{uuid4().hex[:8]}"}}
            protected = conditional_agent.invoke(
                {"messages": [{"role": "user", "content":
                    "调用 record_change(path='/protected/config.txt', content='BLOCK_MARKER')，只调用一次。"}]},
                config=protected_config, version="v2",
            )
            assert protected.interrupts and len(changes) == 1
            action = protected.interrupts[0].value["action_requests"][0]
            assert action["name"] == "record_change"
            assert action.get("arguments", action.get("args", {}))["path"] == "/protected/config.txt"
            denied = conditional_agent.invoke(
                Command(resume={"decisions": [{
                    "type": "reject", "message": "拒绝受保护路径变更；不要重试。"
                }]}),
                config=protected_config, version="v2",
            )
            assert not denied.interrupts and len(changes) == 1
            print("条件中断：/protected/ 暂停，reject 后没有执行")

            # 第二组：内置 write_file 命中路径权限，无需自定义工具也能暂停。
            with TemporaryDirectory(prefix="ch09-permission-") as directory:
                disk_root = Path(directory)
                file_agent = create_deep_agent(
                    model=model,
                    backend=FilesystemBackend(root_dir=disk_root, virtual_mode=True),
                    permissions=[FilesystemPermission(
                        operations=["write"], paths=["/protected/**"], mode="interrupt"
                    )],
                    checkpointer=InMemorySaver(),
                    system_prompt="按用户要求调用 write_file 一次。若审批拒绝，不要重试。",
                )
                file_config = {"configurable": {"thread_id": f"file-{uuid4().hex[:8]}"}}
                target = disk_root / "protected" / "approved.txt"
                paused = file_agent.invoke(
                    {"messages": [{"role": "user", "content":
                        "请调用 write_file，把 PERMISSION_MARKER 写入 /protected/approved.txt，"
                        "只调用一次并报告工具结果。"}]},
                    config=file_config, version="v2",
                )
                assert paused.interrupts, "受保护文件写入前应暂停"
                assert not target.exists(), "审批前文件不应落盘"
                file_action = paused.interrupts[0].value["action_requests"][0]
                assert file_action["name"] == "write_file"
                approved = file_agent.invoke(
                    Command(resume={"decisions": [{"type": "approve"}]}),
                    config=file_config, version="v2",
                )
                assert not approved.interrupts
                assert "PERMISSION_MARKER" in target.read_text(encoding="utf-8")
                print("文件权限：write_file 审批前无文件，approve 后写入临时目录")

            root.add_outputs({"status": "passed", "conditional_changes": changes})
            print("\nPASS：条件中断与文件路径权限中断均符合预期")
            print(f"LangSmith run: {root.get_url()}")

    # 等待 LangSmith 上传后再关闭客户端。
    wait_for_all_tracers()
    client.flush(timeout=20)
    client.close(timeout=20)


if __name__ == "__main__":
    main()
