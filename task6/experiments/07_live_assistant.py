"""真实模型交互实验：需要 .env 中的模型配置，使用期间产生模型调用费用。"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

from _lab import User, InMemoryStore, config, content, memory_agent, seed, experiment_main
from deepagents import FilesystemPermission
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.types import Command


MEMORIES = ["preferences.md", "AGENTS.md", "research/sources.md", "research/notes.md",
            "research/progress.md", "research/report.md"]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
        epilog="追踪选项：--trace 强制开启；--no-trace 强制关闭；默认沿用环境变量。")
    parser.add_argument("--user", default="alice", help="初始用户标识")
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        parser.error("请在 task6/.env 或环境变量中设置 OPENAI_API_KEY")
    model = ChatOpenAI(model=os.getenv("AGENTSEEK_MODEL", "deepseek-flash"),
                       base_url=os.getenv("OPENAI_API_BASE"), temperature=0)
    store = InMemoryStore()

    def initialize(user):
        for path in MEMORIES:
            if store.get((user, "memories"), f"/{path}") is None:
                seed(store, f"/{path}", "# 记忆\n暂无记录。", user)

    initialize(args.user)
    agent = memory_agent(model, store, memory=[f"/memories/{p}" for p in MEMORIES],
        system_prompt=("你是跨会话学习和研究助手。用户明确要求记住的个人偏好保存到 "
            "/memories/preferences.md；可长期复用的回答规则保存到 /memories/AGENTS.md。"
            "临时要求不要固化。已有文件优先使用 edit_file，避免覆盖旧知识。"
            "研究资料、笔记、进度和报告分别更新 /memories/research/ 下的 sources.md、"
            "notes.md、progress.md、report.md。来源由用户提供，不要编造核验结果。"
            "临时草稿写 /workspace/。写入被拒绝时根据反馈调整，不要重复相同写入。"),
        permissions=[FilesystemPermission(operations=["write"], paths=["/memories/**"], mode="interrupt")])
    user, thread = args.user, uuid4().hex
    print("真实模型模式。数据仅保留在本次进程内；追踪设置见启动输出。")
    print("命令：/new 新线程；/user alice 切换用户并新建线程；/store 查看当前记忆；/quit 退出")
    try:
        while True:
            text = input(f"\n[{user}/{thread[:8]}] > ").strip()
            if not text:
                continue
            if text == "/quit":
                break
            if text == "/new":
                thread = uuid4().hex
                continue
            if text.startswith("/user "):
                new_user = text[6:].strip()
                if new_user:
                    user, thread = new_user, uuid4().hex
                    initialize(user)
                continue
            if text == "/store":
                for path in MEMORIES:
                    print(f"\n/{path}\n{content(store, '/' + path, user)}")
                continue
            try:
                result = agent.invoke({"messages": [{"role": "user", "content": text}]},
                    config=config(thread), context=User(user), version="v2")
                while result.interrupts:
                    assert len(result.interrupts) == 1, "此入口只处理单个中断批次"
                    review = result.interrupts[0].value
                    decisions = []
                    for action in review["action_requests"]:
                        print(json.dumps(action, ensure_ascii=False, indent=2))
                        allowed = next(c["allowed_decisions"] for c in review["review_configs"]
                                       if c["action_name"] == action["name"])
                        while True:
                            choice = input(f"决策 {allowed} > ").strip()
                            if choice not in allowed:
                                continue
                            decision = {"type": choice}
                            if choice == "edit":
                                try:
                                    edited = json.loads(input("输入完整的新参数 JSON（仅 args 对象）> "))
                                    if not isinstance(edited, dict):
                                        raise ValueError("参数必须是对象")
                                except ValueError as exc:
                                    print(f"参数无效：{exc}")
                                    continue
                                decision["edited_action"] = {"name": action["name"], "args": edited}
                            elif choice in ("reject", "respond"):
                                decision["message"] = input("反馈 > ")
                            decisions.append(decision)
                            break
                    result = agent.invoke(Command(resume={"decisions": decisions}),
                        config=config(thread), context=User(user), version="v2")
                print(result.value["messages"][-1].content)
            except Exception as exc:
                # 不自动重试，避免重复已发生的写入。新线程仍可读取已批准的记忆。
                print(f"本轮失败（{type(exc).__name__}）。请检查模型配置或输入，使用 /new 后继续。")
                thread = uuid4().hex
    except (EOFError, KeyboardInterrupt):
        print("\n退出；内存记忆随进程结束释放。")


if __name__ == "__main__":
    experiment_main(main)
