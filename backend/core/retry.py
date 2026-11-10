# backend/core/retry.py
# 三层兜底：自动重试 → 降级 → 系统兜底。

import asyncio
from functools import wraps
from typing import Callable, Any, Optional

from backend.core.exceptions import (
    LLMAPIError,
    InvalidInputError,
)
from backend.core.logger import get_logger

logger = get_logger(__name__)

RETRYABLE_ERRORS = (LLMAPIError, TimeoutError, ConnectionError)
NON_RETRYABLE_ERRORS = (InvalidInputError,)

MAX_RETRIES = 2
RETRY_DELAYS = [1.0, 3.0]
TIMEOUT_PER_ATTEMPT = 5 * 60


def with_retry(agent_type: str = ""):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_error: Optional[Exception] = None
            for attempt in range(MAX_RETRIES + 1):
                try:
                    result = await asyncio.wait_for(
                        func(*args, **kwargs), timeout=TIMEOUT_PER_ATTEMPT
                    )
                    if attempt > 0:
                        logger.info("retry.succeeded", agent_type=agent_type, attempt=attempt + 1)
                    return result
                except NON_RETRYABLE_ERRORS as e:
                    logger.warning("retry.non_retryable", agent_type=agent_type, error=str(e))
                    raise
                except Exception as e:
                    last_error = e
                    if attempt < MAX_RETRIES:
                        delay = RETRY_DELAYS[attempt]
                        logger.warning(
                            "retry.attempt_failed", agent_type=agent_type,
                            attempt=attempt + 1, delay=delay, error=str(e),
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error("retry.all_failed", agent_type=agent_type, error=str(e))

            # 第二层：降级
            try:
                fb = await AgentFallbackHandler.handle(agent_type, last_error)
                logger.info("retry.fallback_succeeded", agent_type=agent_type)
                return fb
            except Exception as e:
                logger.error("retry.fallback_failed", agent_type=agent_type, error=str(e))

            # 第三层：系统兜底
            logger.error("retry.system_fallback", agent_type=agent_type, error=str(last_error))
            return _system_fallback(agent_type)

        return wrapper
    return decorator


class AgentFallbackHandler:
    @classmethod
    async def handle(cls, agent_type: str, original_error: Exception) -> Any:
        if agent_type == "review":
            return {
                "fallback_used": True,
                "needs_review": True,
                "fallback_note": "评审服务暂时不可用，已标记为需人工复核。",
            }
        raise original_error


def _system_fallback(agent_type: str) -> dict:
    content = {
        "review": "代码评审服务暂时不可用，请稍后再试。",
    }.get(agent_type, "服务暂时不可用，请稍后再试。")
    return {
        "messages": [],
        "content": content,
        "fallback_used": True,
        "system_fallback": True,
        "structured_output": None,
    }