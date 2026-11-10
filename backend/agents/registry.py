# backend/agents/registry.py
# Agent 注册表：集中登记所有业务 Agent，供编排器做意图路由。

import math

from backend.agents.base import Agent

_agents: dict[str, Agent] = {}

# 语义路由阈值：余弦相似度低于该值视为「无法识别」，回退关键词 / 默认 Agent
SEMANTIC_THRESHOLD = 0.3


def register(agent: Agent) -> Agent:
    """注册一个 Agent；name 冲突直接覆盖。"""
    if not agent.name:
        raise ValueError("Agent 必须声明唯一 name")
    _agents[agent.name] = agent
    return agent


def get_agent(name: str) -> Agent | None:
    return _agents.get(name)


def all_agents() -> list[Agent]:
    return list(_agents.values())


def resolve(text: str) -> Agent | None:
    """关键词路由：按意图关键词做子串匹配，命中多个取更长（更具体）者。"""
    best: Agent | None = None
    best_len = 0
    low = (text or "").lower()
    for agent in _agents.values():
        for kw in agent.intents:
            if kw and kw.lower() in low:
                if len(kw) > best_len:
                    best = agent
                    best_len = len(kw)
    return best


def resolve_semantic(text: str) -> Agent | None:
    """MiniLM 语义路由：对文本与各 Agent 意图编码，取余弦相似度最高且达阈值者。

    依赖 rag.embedder（all-MiniLM-L6-v2，进程内单例）。任一环节失败（模型未装、
    未联网下载等）返回 None，由编排器回退关键词路由，不影响可用性。
    """
    if not text:
        return None
    labels: list[str] = []
    agents: list[Agent] = []
    for agent in _agents.values():
        for kw in agent.intents:
            if kw:
                labels.append(kw)
                agents.append(agent)
    if not labels:
        return None
    try:
        from backend.rag.embedder import embed_texts

        vecs = embed_texts([text] + labels)
        q = vecs[0]
        best_idx = -1
        best_score = -1.0
        for i, v in enumerate(vecs[1:]):
            s = _cosine(q, v)
            if s > best_score:
                best_score = s
                best_idx = i
        if best_idx >= 0 and best_score >= SEMANTIC_THRESHOLD:
            return agents[best_idx]
    except Exception:
        return None
    return None


def _cosine(a: list[float], b: list[float]) -> float:
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(x * x for x in b))
    if da == 0 or db == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (da * db)


def register_all() -> None:
    """集中注册全部 Agent。在 agents/__init__ 导入时调用一次。"""
    from backend.agents.code_review import CodeReviewAgent
    from backend.agents.pr_review import PRReviewAgent
    from backend.agents.refactor import RefactorAgent

    register(CodeReviewAgent())
    register(PRReviewAgent())
    register(RefactorAgent())