"""tools.py 学习实验：实际调用工具，在临时目录观察结果，不请求模型。"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from langchain_core.tools import tool

from task8 import tools


def tool_definition(root: Path) -> None:
    @tool
    def summarize_goal(goal: str) -> str:
        """返回待规划目标的简短确认信息，不实际执行目标。"""
        return f"待规划目标：{goal}"

    print("工具名称：", summarize_goal.name)
    print("工具说明：", summarize_goal.description)
    print("参数结构：", summarize_goal.args)
    print("调用结果：", summarize_goal.invoke({"goal": "学习 Python 文件操作"}))
    # 练习：增加一个必填参数，比较参数结构和原调用的变化。


def file_access(root: Path) -> None:
    folder = root / "sources"
    folder.mkdir()
    (folder / "schedule.md").write_text("本周可投入 3 小时。", encoding="utf-8")
    print("资料列表：", tools.list_sources.invoke({}))
    print("资料内容：", tools.read_source.invoke({"name": "schedule.md"}))
    for slug in ("my-plan", "_plan", "../outside"):
        try:
            path = tools._plan_path(slug)
            print(f"slug={slug!r} → {path}，文件存在：{path.exists()}")
        except ValueError as exc:
            print(f"slug={slug!r} → {type(exc).__name__}: {exc}")
    # 练习：单独调用 _inside("..", "outside.md")，观察另一道路径检查。


def plan_workflow(root: Path) -> None:
    incomplete = "# 实验计划\n\n## 任务目标\n学习文件操作。\n\n## 已知条件\n"
    complete = "# 实验计划\n\n" + "\n\n".join(
        f"## {heading}\n这是实验正文，不代表任务已执行。"
        for heading in tools.REQUIRED_HEADINGS
    )
    for slug, content in (("incomplete", incomplete), ("complete", complete)):
        print("\n保存结果：", tools.save_plan.invoke({"slug": slug, "content": content}))
        print("读回内容：\n", tools.read_plan.invoke({"slug": slug}))
        print("检查结果：", json.loads(tools.check_plan.invoke({"slug": slug})))
    # 练习：在完整计划中增加一个没有正文的额外章节，先预测检查结果。
    # 练习：必要章节都保留正文，但把排期写得不合理，检查器会发现吗？


def concurrent_preferences(root: Path) -> None:
    preferences = {"language": "中文", "format": "分节 Markdown", "tone": "简洁"}
    start = Barrier(len(preferences))

    def save(item: tuple[str, str]) -> str:
        key, value = item
        start.wait(timeout=5)
        return tools.save_preference.invoke({"key": key, "value": value})

    with ThreadPoolExecutor(max_workers=len(preferences)) as pool:
        results = list(pool.map(save, preferences.items()))
    for key, result in zip(preferences, results):
        print(f"\n保存 {key} 的返回值：\n{result}")
    print("\n最终文件：\n", (root / "memory/preferences.md").read_text(encoding="utf-8"))
    # 练习：用相同 key 保存新值，观察哪些字段被更新、哪些被保留。
    # 并发时返回值可能对应不同更新阶段，不要求三个返回值完全相同。
    # 此例只观察加锁后的行为；要证明锁的必要性，另做简化读改写对照实验。


EXPERIMENTS = {
    "1": tool_definition,
    "2": file_access,
    "3": plan_workflow,
    "4": concurrent_preferences,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", choices=EXPERIMENTS, default="1")
    args = parser.parse_args()
    with TemporaryDirectory(prefix="task8-tools-learning-") as folder:
        root = Path(folder)
        original_root = tools.PROJECT_ROOT
        tools.PROJECT_ROOT = root
        try:
            print("实验工作目录：", root)
            EXPERIMENTS[args.experiment](root)
        finally:
            tools.PROJECT_ROOT = original_root
    print("\n实验结束，临时目录已清理。")


if __name__ == "__main__":
    main()
