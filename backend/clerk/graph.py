# backend/clerk/graph.py
# 评审 Agent 的 LangGraph 状态图。

from langgraph.graph import StateGraph, START, END

from backend.clerk.state import ReviewState
from backend.clerk.nodes import parse_node, lint_node, review_node, award_node
from backend.core.memory import get_memory_saver


def build_review_graph():
    """构建并编译评审图：parse → lint → review → award → END。"""
    builder = StateGraph(ReviewState)

    builder.add_node("parse", parse_node)
    builder.add_node("lint", lint_node)
    builder.add_node("review", review_node)
    builder.add_node("award", award_node)

    builder.add_edge(START, "parse")
    builder.add_edge("parse", "lint")
    builder.add_edge("lint", "review")
    builder.add_edge("review", "award")
    builder.add_edge("award", END)

    checkpointer = get_memory_saver("review")
    return builder.compile(checkpointer=checkpointer)