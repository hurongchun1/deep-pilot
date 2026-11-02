"""离线实验用预设回复；Agent 图、中间件与工具仍真实运行。"""

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field, PrivateAttr


class ScriptedModel(BaseChatModel):
    replies: list[AIMessage]
    prompts: list[str] = Field(default_factory=list)
    seen_tools: list[str] = Field(default_factory=list)
    _cursor: int = PrivateAttr(default=0)

    @property
    def _llm_type(self):
        return "task-planner-scripted"

    def bind_tools(self, tools, **kwargs):
        self.seen_tools = [tool.name if hasattr(tool, "name") else tool["name"]
                           for tool in tools]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.prompts.append("\n".join(str(message.content) for message in messages))
        if self._cursor >= len(self.replies):
            raise AssertionError("预设模型回复已用完，但 Agent 尚未停止")
        reply = self.replies[self._cursor]
        self._cursor += 1
        return ChatResult(generations=[ChatGeneration(message=reply)])


def call(name, args, call_id):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def planning_model(scenario: str) -> ScriptedModel:
    from sample_plan import sample_plan

    return ScriptedModel(replies=[
        call("write_todos", {"todos": [{"content": "拆解目标并保存检查计划", "status": "in_progress"}]}, "todo"),
        call("read_file", {"file_path": "/skills/task-planning/SKILL.md"}, "skill"),
        call("read_file", {"file_path": "/skills/task-planning/references/plan-outline.md"}, "outline"),
        call("save_plan", {"slug": scenario, "content": sample_plan(scenario)}, "save"),
        call("read_plan", {"slug": scenario}, "readback"),
        call("check_plan", {"slug": scenario}, "check"),
        call("write_todos", {"todos": [{"content": "拆解目标并保存检查计划", "status": "completed"}]}, "done"),
        AIMessage(content="行动计划已保存，结构检查通过，任务尚未实际执行。"),
    ])
