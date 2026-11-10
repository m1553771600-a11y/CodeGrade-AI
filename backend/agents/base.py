# backend/agents/base.py
# Agent 抽象基类：每个业务 Agent（代码评审 / QA / 面试…）都实现该接口，
# 供编排器统一路由与执行。

from abc import ABC, abstractmethod
from typing import Any


class Agent(ABC):
    """业务 Agent 统一接口。

    属性：
        name         唯一名（registry 的 key，如 "code-review"）
        display_name 展示名
        description  用途说明
        intents      意图关键词（编排器据此做意图路由）

    方法：
        build()      构建并返回编译好的 LangGraph（含 checkpointer）
    """

    name: str = ""
    display_name: str = ""
    description: str = ""
    intents: list[str] = []

    @abstractmethod
    def build(self) -> Any:
        """构建并返回编译好的图。"""
        raise NotImplementedError
