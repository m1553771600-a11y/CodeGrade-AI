# backend/clerk/state.py
# 评审 Agent 的 State 与数据模型。

from typing import Annotated, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field


class IssueItem(BaseModel):
    """单条问题（定位到文件/行）。"""
    file: str = ""
    line: Optional[int] = None
    severity: str = "medium"   # low / medium / high
    evidence: str = ""
    suggestion: str = ""


class DimensionScore(BaseModel):
    """单个维度评审结果（LLM 结构化输出 + 内部存储共用）。"""
    dimension: str = ""        # 维度 key，如 structure
    score: int = 0
    weight: int = 0            # 代码层回填，LLM 不给
    issues: list[IssueItem] = Field(default_factory=list)


class ReviewScores(BaseModel):
    """LLM 六维度评审的顶层结构化输出。"""
    dimension_scores: list[DimensionScore]
    summary: str = Field(description="整体评审总结（2-3 句话，概括质量水平与最需改进的方向）")


class TitleAward(BaseModel):
    level: int = 0
    title: str = ""
    easter_egg: str = ""       # 彩蛋称号
    reason: str = ""           # 颁奖词


class ReviewState(TypedDict):
    """评审 Agent 完整 State。"""
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    tenant_id: str
    session_id: str
    zip_local_path: str

    # 解析结果（三层分区）
    language: str
    focus_layer: list[dict]
    structure_layer: list[dict]
    ignore_stats: dict
    static_metrics: dict

    # 评审结果
    dimension_scores: list[dict]
    total_score: int
    review_summary: str
    title_award: dict

    fallback_used: bool
    structured_output: Optional[dict]