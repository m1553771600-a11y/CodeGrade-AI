# backend/core/progress.py
# 评审进度发布/订阅（进程内内存队列），SSE 端点据此推送实时进度。

import asyncio
from collections import defaultdict
from typing import Any

_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)


def subscribe(submission_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _subscribers[submission_id].add(q)
    return q


def unsubscribe(submission_id: str, q: asyncio.Queue) -> None:
    qs = _subscribers.get(submission_id)
    if qs is not None:
        qs.discard(q)
        if not qs:
            _subscribers.pop(submission_id, None)


def publish(submission_id: str, event: dict[str, Any]) -> None:
    """发布一条进度事件；同步 put_nowait，不阻塞事件循环。"""
    for q in list(_subscribers.get(submission_id, ())):
        try:
            q.put_nowait(event)
        except Exception:
            pass
