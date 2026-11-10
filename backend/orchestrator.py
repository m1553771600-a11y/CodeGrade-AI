# backend/orchestrator.py
# 编排器：意图识别 + Agent 路由，是所有异步任务的统一执行入口。

import asyncio

from backend.agents.base import Agent
from backend.agents.registry import get_agent, resolve, resolve_semantic
from backend.core.logger import get_logger

logger = get_logger(__name__)

# 意图无法识别时的兜底 Agent
DEFAULT_AGENT = "code-review"


async def route(text: str) -> Agent:
    """意图识别并路由到 Agent：MiniLM 语义优先 → 关键词回退 → 默认 Agent。

    embedding 在子线程执行，避免阻塞事件循环。
    """
    agent = await asyncio.to_thread(resolve_semantic, text)
    if agent is None:
        agent = resolve(text)
    if agent is None:
        agent = get_agent(DEFAULT_AGENT)
    logger.info("orchestrator.route | agent=%s", agent.name if agent else None)
    return agent


async def run_agent(agent: Agent, state: dict, config: dict) -> dict:
    """执行某个 Agent 的图，返回最终 state（供上层落库）。"""
    graph = agent.build()
    return await graph.ainvoke(state, config=config)
