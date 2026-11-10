# backend/core/llm_factory.py
# LLM 工厂：统一封装 DeepSeek（OpenAI 兼容接口），按业务类型路由。

from typing import Type, Any
import httpx
from pydantic import BaseModel
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable

from backend.config import get_settings
from backend.core.logger import get_logger

logger = get_logger(__name__)

# 绕过 Windows 系统代理（DeepSeek 国内直连，走代理会 TLS 失败）
_HTTP_ASYNC_CLIENT = httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(120.0, connect=15.0))
_HTTP_SYNC_CLIENT = httpx.Client(trust_env=False, timeout=httpx.Timeout(120.0, connect=15.0))

_BUILTIN_AGENT_TYPES = {"review", "title", "summarize", "pr-review", "refactor"}


class LLMFactory:
    _instances: dict[str, BaseChatModel] = {}

    @classmethod
    def _build_kwargs(cls) -> dict[str, Any]:
        s = get_settings()
        return {
            "model": s.deepseek_model,
            "model_provider": "openai",
            "api_key": s.deepseek_api_key,
            "base_url": s.deepseek_base_url,
            "max_retries": 0,  # 重试统一由 retry.py 管
            "http_async_client": _HTTP_ASYNC_CLIENT,
            "http_client": _HTTP_SYNC_CLIENT,
        }

    @classmethod
    def get_llm(cls, agent_type: str, temperature: float = 0, streaming: bool = False) -> BaseChatModel:
        if agent_type not in _BUILTIN_AGENT_TYPES:
            raise ValueError(f"未知 agent_type: '{agent_type}'，可用：{sorted(_BUILTIN_AGENT_TYPES)}")
        cache_key = f"{agent_type}_{temperature}_{streaming}"
        if cache_key not in cls._instances:
            kwargs = cls._build_kwargs()
            kwargs.update(
                temperature=temperature,
                streaming=streaming,
                extra_body={"thinking": {"type": "disabled"}},
            )
            cls._instances[cache_key] = init_chat_model(**kwargs)
            logger.info("llm_factory.model_initialized", agent_type=agent_type)
        return cls._instances[cache_key]

    @classmethod
    def get_structured_llm(cls, agent_type: str, output_schema: Type[BaseModel]) -> Runnable:
        llm = cls.get_llm(agent_type)
        return llm.with_structured_output(output_schema, method="function_calling")

    @classmethod
    def clear_cache(cls) -> None:
        cls._instances.clear()


def get_llm(agent_type: str, temperature: float = 0, streaming: bool = False) -> BaseChatModel:
    return LLMFactory.get_llm(agent_type, temperature=temperature, streaming=streaming)


def get_structured_llm(agent_type: str, output_schema: Type[BaseModel]) -> Runnable:
    return LLMFactory.get_structured_llm(agent_type, output_schema)