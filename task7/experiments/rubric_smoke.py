"""无密钥实验：真实运行 RubricMiddleware，模型回复由脚本预设。"""

from __future__ import annotations

import json
import warnings
from copy import deepcopy
from typing import Callable

from deepagents import RubricMiddleware, create_deep_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langsmith import tracing_context
from pydantic import Field, PrivateAttr


SALES = [{"name": "茶", "amount": 30}, {"name": "咖啡", "amount": 50}]
CRITERIA = ["报告是 JSON 对象", "items 与输入明细一致", "total 等于销售额之和"]
BAD_REPORT = json.dumps({"items": SALES}, ensure_ascii=False)
GOOD_REPORT = json.dumps({"items": SALES, "total": 80}, ensure_ascii=False)
TASK = "根据茶 30 元、咖啡 50 元生成 JSON 报告，包含 items 和 total。只返回 JSON。"
RUBRIC = "\n".join(f"- {name}" for name in CRITERIA)


def assess_report(report: str) -> dict:
    """用确定性的 Python 逻辑检查报告，不依赖评分模型猜测。"""
    try:
        data = json.loads(report)
    except json.JSONDecodeError:
        data = None
    is_object = isinstance(data, dict)
    items_ok = is_object and data.get("items") == SALES
    total = data.get("total") if is_object else None
    total_ok = type(total) in (int, float) and total == 80
    checks = [
        (CRITERIA[0], is_object, "请返回 JSON 对象"),
        (CRITERIA[1], items_ok, "items 应保留商品、金额和顺序"),
        (CRITERIA[2], total_ok, "缺少或错误的 total；应为 80"),
    ]
    criteria = [
        {"name": name, "passed": passed, **({"gap": gap} if not passed else {})}
        for name, passed, gap in checks
    ]
    return {"ok": all(item["passed"] for item in criteria), "criteria": criteria}


def make_evidence_tool(records: list[dict]):
    @tool
    def check_report(report: str) -> dict:
        """检查当前候选 JSON 销售报告，并返回逐项通过状态和差距。"""
        evidence = assess_report(report)
        records.append({"report": report, "evidence": deepcopy(evidence)})
        return evidence

    return check_report


class ScriptedModel(BaseChatModel):
    """只预设模型回复；Agent 图、中间件和证据工具仍真实执行。"""

    replies: list[AIMessage] = Field(default_factory=list)
    responder: Callable[[list], AIMessage] | None = None
    calls: int = 0
    _cursor: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "task7-scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.calls += 1
        if self.responder is not None:
            reply = self.responder(messages)
        else:
            if self._cursor >= len(self.replies):
                raise AssertionError("预设工作回复耗尽：出现了意料之外的额外调用")
            reply = self.replies[self._cursor]
            self._cursor += 1
        return ChatResult(generations=[ChatGeneration(message=reply)])


def grader_reply(messages: list) -> AIMessage:
    """先请求真实工具；拿到工具返回后再给结构化评分。"""
    last = messages[-1]
    if isinstance(last, ToolMessage):
        evidence = json.loads(last.text)
        return AIMessage(content="", tool_calls=[{
            "name": "GraderResponse",
            "id": "verdict",
            "args": {
                "result": "satisfied" if evidence["ok"] else "needs_revision",
                "explanation": "全部通过" if evidence["ok"] else "请修订未通过的标准",
                "criteria": evidence["criteria"],
            },
        }])

    transcript = last.text
    latest = transcript.rsplit("[assistant] ", 1)[-1]
    candidate, _ = json.JSONDecoder().raw_decode(latest)
    return AIMessage(content="", tool_calls=[{
        "name": "check_report",
        "id": "check-current",
        "args": {"report": json.dumps(candidate, ensure_ascii=False)},
    }])


def accepted(result: dict, evaluations: list[dict], records: list[dict]) -> bool:
    """只有明确通过，且最后证据对应最新候选时才接收。"""
    if not evaluations or evaluations[-1]["result"] != "satisfied" or not records:
        return False
    candidates = [m for m in result["messages"] if isinstance(m, AIMessage)]
    if not candidates or candidates[-1].tool_calls:
        return False
    latest = candidates[-1].text
    try:
        same_candidate = json.loads(records[-1]["report"]) == json.loads(latest)
    except json.JSONDecodeError:
        return False
    return same_candidate and records[-1]["evidence"]["ok"] and assess_report(latest)["ok"]


def run_case(name: str, *, max_iterations: int = 2, with_rubric: bool = True) -> None:
    records: list[dict] = []
    evaluations: list[dict] = []
    working = ScriptedModel(replies=[AIMessage(content=BAD_REPORT), AIMessage(content=GOOD_REPORT)])
    grader = ScriptedModel(responder=grader_reply)
    middleware = RubricMiddleware(
        model=grader,
        tools=[make_evidence_tool(records)],
        system_prompt="按 Rubric 评分。必须先调用 check_report 检查最新候选，再逐项返回 GraderResponse。",
        max_iterations=max_iterations,
        on_evaluation=lambda ev: evaluations.append(deepcopy(ev)),
    )
    agent = create_deep_agent(model=working, middleware=[middleware])
    request = {"messages": [HumanMessage(content=TASK)]}
    if with_rubric:
        request["rubric"] = RUBRIC
    result = agent.invoke(request, config={"recursion_limit": 24})
    verdicts = [ev["result"] for ev in evaluations]

    print(f"\n=== {name} ===")
    print("工作模型调用次数：", working.calls)
    print("评分模型调用次数：", grader.calls)
    for index, record in enumerate(records):
        print(f"第 {index} 次检查：ok={record['evidence']['ok']}; report={record['report']}")
        for criterion in record["evidence"]["criteria"]:
            if not criterion["passed"]:
                print("  未通过：", criterion["name"], "—", criterion["gap"])
    print("评分结论：", " -> ".join(verdicts) if verdicts else "无评分")
    feedback = [m.text for m in result["messages"] if isinstance(m, HumanMessage) and "Criteria that still need work" in m.text]
    if feedback:
        print("中间件反馈包含 total=80：", "total" in feedback[0] and "80" in feedback[0])
    print("最终是否交付：", accepted(result, evaluations, records))

    assert result["messages"], "即使未验收，工作 Agent 也应留下候选消息"
    if name == "两轮修订":
        assert working.calls == 2 and verdicts == ["needs_revision", "satisfied"]
        assert len(records) == 2 and records[0]["evidence"]["ok"] is False
        assert records[1]["evidence"]["ok"] is True
        assert accepted(result, evaluations, records)
        assert feedback and "total" in feedback[0] and "80" in feedback[0]
    elif name == "一轮预算":
        assert working.calls == 1 and verdicts == ["max_iterations_reached"]
        assert len(records) == 1 and not accepted(result, evaluations, records)
    elif name == "没有 Rubric":
        assert working.calls == 1 and not evaluations and not records
        assert not accepted(result, evaluations, records)


def main() -> None:
    warnings.filterwarnings("ignore", message="The middleware `RubricMiddleware` is in beta.*")
    # 无密钥实验默认离线；不继承用户环境中的 LangSmith 后台追踪设置。
    with tracing_context(enabled=False):
        probe_records: list[dict] = []
        probe = make_evidence_tool(probe_records)
        assert not probe.invoke({"report": BAD_REPORT})["ok"]
        assert probe.invoke({"report": GOOD_REPORT})["ok"]
        assert not probe.invoke({"report": "不是 JSON"})["ok"]
        assert len(probe_records) == 3
        print("证据工具的三种输入检查通过。")
        run_case("两轮修订")
        run_case("一轮预算", max_iterations=1)
        run_case("没有 Rubric", with_rubric=False)
        print("\nPASS：三种场景均符合预期。")


if __name__ == "__main__":
    main()
