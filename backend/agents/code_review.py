# backend/agents/code_review.py
# 代码评审 Agent：包装现有 clerk 引擎，作为首个业务 Agent 注册。

from functools import lru_cache

from backend.agents.base import Agent
from backend.clerk.graph import build_review_graph


class CodeReviewAgent(Agent):
    name = "code-review"
    display_name = "代码评审"
    description = "对 zip/git 提交的工程代码做六维质量评审，并颁发称号"

    # 编排器据此识别「代码评审」意图（keyword 路由，后续可换 MiniLM 语义路由）
    intents = [
        "代码", "评审", "代码评审", "code review", "code-review",
        "仓库", "repository", "zip", "git", "源码", "工程", "review",
    ]

    @lru_cache(maxsize=None)
    def build(self):
        return build_review_graph()
