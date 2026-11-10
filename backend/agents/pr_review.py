# backend/agents/pr_review.py
# PR 评审 Agent：对 git diff 做增量评审，识别高复杂度热点后联动 RefactorAgent。

from functools import lru_cache
from typing import Annotated, Optional

from typing_extensions import TypedDict
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from backend.agents.base import Agent
from backend.agents.refactor import RefactorTarget
from backend.core.llm_factory import get_structured_llm
from backend.core.memory import get_memory_saver
from backend.core.retry import with_retry
from backend.core.logger import get_logger

logger = get_logger(__name__)


class DiffIssue(BaseModel):
    """单条增量评审问题（定位到文件/行）。"""
    file: str = ""
    line: Optional[int] = None
    severity: str = "medium"   # low / medium / high
    dimension: str = ""
    evidence: str = ""
    suggestion: str = ""


class PRReviewOutput(BaseModel):
    """PR 评审结构化输出：问题清单 + 需重构热点。"""
    issues: list[DiffIssue] = Field(default_factory=list)
    hotspots: list[RefactorTarget] = Field(
        default_factory=list,
        description="存在严重复杂度问题、建议交给重构 Agent 的代码片段",
    )
    summary: str = ""


class PRReviewState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    tenant_id: str
    session_id: str
    diff_text: str
    language: str
    issues: list[dict]
    hotspots: list[dict]
    refactor_results: list[dict]
    summary: str
    fallback_used: bool


SYSTEM_PROMPT = (
    "你是一位资深代码评审专家，负责对代码变更（git diff）做增量评审，"
    "重点关注可定位、可执行的具体问题。"
)

PR_REVIEW_PROMPT = """请对下面这段 {language} 代码变更（git diff）做增量评审。

【diff 内容】
```diff
{diff_text}
```

要求：
1. 在 issues 中列出可定位到文件/行的具体问题；severity 取 low/medium/high；
   dimension 取：structure / robustness / maintainability / complexity / style / readability；
2. 在 hotspots 中列出「存在严重复杂度问题、值得重构」的代码片段：
   - 只挑复杂度风险高（如新增函数圈复杂度过高、深层 if-else、重复逻辑）的热点；
   - code_snippet 从 diff 中摘录相关代码（含必要上下文，控制在 60 行内）；
   - 若无法从 diff 取到足够上下文，宁可不输出该热点；
3. summary 用 2-3 句总结本次改动的总体质量与最需优先改进的方向。"""


@with_retry(agent_type="pr-review")
async def _llm_pr_review(state: PRReviewState) -> PRReviewOutput:
    # diff 内容可能含 { }，注入前转义，避免被 str.format 当作占位符
    def _esc(s: str) -> str:
        return s.replace("{", "{{").replace("}", "}}")

    prompt = PR_REVIEW_PROMPT.format(
        language=state.get("language", "python"),
        diff_text=_esc(state.get("diff_text", "")),
    )
    llm = get_structured_llm("pr-review", PRReviewOutput)
    return await llm.ainvoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])


async def review_node(state: PRReviewState) -> dict:
    result = await _llm_pr_review(state)
    if isinstance(result, dict):
        logger.warning("pr_review.fallback_used")
        return {
            "issues": [], "hotspots": [],
            "summary": "评审服务暂时不可用，请稍后重试。", "fallback_used": True,
        }
    logger.info("pr_review.review_done", issues=len(result.issues), hotspots=len(result.hotspots))
    return {
        "issues": [i.model_dump() for i in result.issues],
        "hotspots": [h.model_dump() for h in result.hotspots],
        "summary": result.summary,
    }


async def refactor_node(state: PRReviewState, config: RunnableConfig) -> dict:
    """联动节点：对每个复杂度热点调用 RefactorAgent，收集重构 diff。"""
    from backend.agents.registry import get_agent

    refactor_agent = get_agent("refactor")
    hotspots = [RefactorTarget(**h) for h in (state.get("hotspots") or [])]
    if refactor_agent is None or not hotspots:
        return {"refactor_results": []}

    sub = refactor_agent.build()
    results = []
    for hs in hotspots:
        r = await sub.ainvoke(
            {
                "messages": [],
                "language": state.get("language", "python"),
                "target": hs.model_dump(),
            },
            config=config,
        )
        results.append({
            "file": hs.file,
            "function": hs.function,
            "reason": hs.reason,
            "refactor_diff": r.get("refactor_diff", ""),
            "summary": r.get("summary", ""),
        })
    logger.info("pr_review.refactor_done", count=len(results))
    return {"refactor_results": results}


def _should_refactor(state: PRReviewState) -> str:
    """条件边：存在复杂度热点才进入 refactor 节点。"""
    return "refactor" if state.get("hotspots") else END


def build_pr_review_graph():
    """构建 PR 评审图：review → [hotspots? refactor] → END。"""
    builder = StateGraph(PRReviewState)
    builder.add_node("review", review_node)
    builder.add_node("refactor", refactor_node)
    builder.add_edge(START, "review")
    builder.add_conditional_edges("review", _should_refactor, {"refactor": "refactor", END: END})
    builder.add_edge("refactor", END)
    return builder.compile(checkpointer=get_memory_saver("pr-review"))


class PRReviewAgent(Agent):
    name = "pr-review"
    display_name = "PR 增量评审"
    description = "对 git diff 做增量评审，识别复杂度热点并联动重构 Agent 生成重构 diff"

    intents = [
        "pr", "pull request", "merge request", "diff", "改动", "变更", "增量", "pr review",
    ]

    @lru_cache(maxsize=None)
    def build(self):
        return build_pr_review_graph()