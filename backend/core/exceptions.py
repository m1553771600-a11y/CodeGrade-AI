# backend/core/exceptions.py
# 统一异常体系：区分可重试 / 不可重试。


class EvalBaseError(Exception):
    def __init__(self, message: str, agent_type: str = "", details: dict = None):
        super().__init__(message)
        self.agent_type = agent_type
        self.details = details or {}


class LLMAPIError(EvalBaseError):
    """大模型 API 调用失败（可重试）。"""


class AgentExecutionError(EvalBaseError):
    """Agent 业务执行失败。"""


class RepoParseError(EvalBaseError):
    """仓库解析失败（zip 损坏 / 语言不支持等）。"""


class InvalidInputError(EvalBaseError):
    """输入不合法（不可重试）。"""


class LinterError(EvalBaseError):
    """静态分析工具调用失败。"""