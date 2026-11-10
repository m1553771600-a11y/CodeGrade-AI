# backend/agents/refactor.py
# 重构 Agent：针对高复杂度代码片段，生成可参考的重构 diff。
# 既能独立路由（"重构"/"refactor"），也作为 pr-review 联动时的下游 Agent。

from functools import lru_cache
from typing import Annotated, Optional

from typing_extensions import TypedDict
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from backend.agents.base import Agent
from backend.core.llm_factory import get_structured_llm
from backend.core.memory import get_memory_saver
from backend.core.retry import with_retry
from backend.core.logger import get_logger

logger = get_logger(__name__)


class RefactorTarget(BaseModel):
    """待重构的代码片段（pr-review 联动时产出，RefactorAgent 消费）。"""
    file: str = ""
    function: str = ""
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    code_snippet: str = ""
    reason: str = ""


class RefactorResult(BaseModel):
    """重构产物：统一 diff 补丁 + 说明。"""
    refactor_diff: str = Field(description="unified diff 格式的重构补丁")
    summary: str = Field(description="用 2-3 句说明重构要点与收益")


class RefactorState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    language: str
    target: dict          # RefactorTarget.model_dump()
    refactor_diff: str
    summary: str
    fallback_used: bool


SYSTEM_PROMPT = (
    "你是一位资深重构专家，擅长在不改变外部行为的前提下，"
    "用更清晰、更低复杂度、更可维护的方式改写代码。"
)

REFACTOR_PROMPT = """请对下面这段 {language} 代码进行重构。

【文件】{file}
【函数/位置】{function}
【重构原因】{reason}

【待重构代码】
```{language}
{code_snippet}
```

要求：
1. 保持原有功能与外部行为不变；
2. 优先降低圈复杂度：拆分长函数、提取方法、用字典/策略替代过深 if-else、消除重复逻辑；
3. 在 refactor_diff 字段输出 unified diff 格式补丁（以 ---/+++ 开头，含 @@ 行号），可直接参考；
4. 若代码片段信息不足、无法给出可靠 diff，refactor_diff 留空，并在 summary 中说明原因。"""


@with_retry(agent_type="refactor")
async def _llm_refactor(state: RefactorState) -> RefactorResult:
    target = state.get("target") or {}
    # 代码片段可能含 { }，注入前转义，避免被 str.format 当作占位符
    def _esc(s: str) -> str:
        return s.replace("{", "{{").replace("}", "}}")

    prompt = REFACTOR_PROMPT.format(
        language=state.get("language", "python"),
        file=target.get("file", ""),
        function=target.get("function", ""),
        reason=target.get("reason", ""),
        code_snippet=_esc(target.get("code_snippet", "")),
    )
    llm = get_structured_llm("refactor", RefactorResult)
    return await llm.ainvoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])


async def refactor_node(state: RefactorState) -> dict:
    target = state.get("target") or {}
    result = await _llm_refactor(state)
    if isinstance(result, dict):
        # 重试/降级兜底：返回空结果，不阻断 pr-review 联动
        logger.warning("refactor.fallback_used", file=target.get("file"))
        return {"refactor_diff": "", "summary": "", "fallback_used": True}
    logger.info("refactor.done", file=target.get("file"), function=target.get("function"))
    return {"refactor_diff": result.refactor_diff, "summary": result.summary}


def build_refactor_graph():
    """构建重构图：单节点 refactor → END。"""
    builder = StateGraph(RefactorState)
    builder.add_node("refactor", refactor_node)
    builder.add_edge(START, "refactor")
    builder.add_edge("refactor", END)
    return builder.compile(checkpointer=get_memory_saver("refactor"))


class RefactorAgent(Agent):
    name = "refactor"
    display_name = "代码重构"
    description = "针对高复杂度代码片段生成可参考的重构 diff"

    intents = [
        "重构", "重写代码", "优化代码", "降低复杂度", "refactor",
        "简化", "拆分函数", "消除重复",
    ]

    @lru_cache(maxsize=None)
    def build(self):
        return build_refactor_graph()