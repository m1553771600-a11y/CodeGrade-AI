# backend/db/session.py
# 异步数据库引擎与 session（SQLAlchemy 2.0 async + asyncpg）。

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.config import get_settings

_engine = None
_factory = None


def get_engine():
    """懒初始化全局异步引擎（create_async_engine 不建连接，首次执行才连）。"""
    global _engine
    if _engine is None:
        s = get_settings()
        _engine = create_async_engine(
            s.database_url,
            echo=s.app_debug,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """懒初始化 session 工厂。"""
    global _factory
    if _factory is None:
        _factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _factory
