# backend/db/migrations.py
# 幂等迁移：骨架期用 metadata.create_all 建表，后续可替换为 Alembic。

from backend.db.session import get_engine
from backend.db.models import Base


async def run_migrations() -> None:
    """幂等迁移入口：创建所有缺失的表，并给已有表补列。"""
    from sqlalchemy import text
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 已有表补列（幂等，create_all 不会改已存在表的列）
        await conn.execute(text("ALTER TABLE submissions ADD COLUMN IF NOT EXISTS status VARCHAR(16) DEFAULT 'completed'"))
        await conn.execute(text("ALTER TABLE submissions ADD COLUMN IF NOT EXISTS error TEXT"))
        await conn.execute(text("ALTER TABLE submissions ADD COLUMN IF NOT EXISTS agent_type VARCHAR(32) DEFAULT 'code-review'"))
