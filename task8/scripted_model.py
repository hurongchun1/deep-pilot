"""离线实验用预设回复；Agent 图、中间件与工具仍真实运行。"""

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field, PrivateAttr

class ScriptedModel(BaseChatModel):
    # 这是预先准备的模型回复，离线时不用请求真实模型，按剧本返回回复
    replies: list[AIMessage]
    # 每次调用模型时收到的消息内容，回头检查Skill、偏好、工具结果是否真的传给了模型
    prompts: list[str] = Field(default_factory=list)
    # 绑定到模型上的工具名称，观察框架向模型提供了哪些工具
    seen_tools: list[str] = Field(default_factory=list)
    # 下一条应该返回的回复下标，让多次调用依次推进，而不是始终返回第一条
    _cursor: int = PrivateAttr(default=0)

    @property
    def _llm_type(self):
        return "task-planner-scripted"
    # 绑定工具
    def bind_tools(self, tools, **kwargs):
        self.seen_tools = [tool.name if hasattr(tool, "name") else tool["name"]
                           for tool in tools]
        return self

    # 模型调用接口，收到消息后返回预设回复
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.prompts.append("\n".join(str(message.content) for message in messages))
        if self._cursor >= len(self.replies):
            raise AssertionError("预设模型回复已用完，但 Agent 尚未停止")
        reply = self.replies[self._cursor]
        self._cursor += 1
        return ChatResult(generations=[ChatGeneration(message=reply)])

# call是请求调用工具
def call(name, args, call_id):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


# 为规划按理准备的一套剧本
def planning_model(scenario: str) -> ScriptedModel:
    from task8.sample_plan import sample_plan

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
