# backend/agents/__init__.py
# 包入口：导入即注册全部业务 Agent。

from backend.agents.base import Agent
from backend.agents.registry import (
    register,
    register_all,
    get_agent,
    all_agents,
    resolve,
)

register_all()

__all__ = [
    "Agent",
    "register",
    "register_all",
    "get_agent",
    "all_agents",
    "resolve",
]
