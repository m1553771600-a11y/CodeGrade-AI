# backend/core/memory.py
# MemorySaver（checkpointer）+ thread_id / config 构造。

from langgraph.checkpoint.memory import MemorySaver

from backend.core.logger import get_logger

logger = get_logger(__name__)

_memory_savers: dict[str, MemorySaver] = {}


def get_memory_saver(agent_type: str = "default") -> MemorySaver:
    """按类型取 MemorySaver 单例（不同类型独立，避免字段冲突）。"""
    if agent_type not in _memory_savers:
        _memory_savers[agent_type] = MemorySaver()
        logger.info("memory.saver_initialized", agent=agent_type)
    return _memory_savers[agent_type]


def build_thread_id(user_id: str, session_id: str) -> str:
    """Checkpointer 使用的 thread_id。"""
    return f"user_{user_id}_session_{session_id}"


def build_config(user_id: str, session_id: str) -> dict:
    """构建 graph.ainvoke 所需的 config 字典。"""
    return {"configurable": {"thread_id": build_thread_id(user_id, session_id)}}