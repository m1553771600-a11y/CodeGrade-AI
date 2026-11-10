# backend/api/v1/profile.py
# 能力画像：按 user_id 聚合历史评审数据。

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select

from backend.clerk.profiler import compute_profile
from backend.core.logger import get_logger
from backend.core.security import get_current_user
from backend.db.models import Review, Submission
from backend.db.session import get_session_factory

router = APIRouter()
logger = get_logger(__name__)


@router.get("/me")
async def get_profile(user: str = Depends(get_current_user)):
    """返回当前用户的能力画像（六维熟练度 + 薄弱点 + 趋势）。"""
    try:
        factory = get_session_factory()
        async with factory() as session:
            stmt = (
                select(Review)
                .join(Submission, Review.submission_id == Submission.id)
                .where(Submission.user_id == user)
                .order_by(Review.created_at)
            )
            reviews = (await session.execute(stmt)).scalars().all()
    except Exception as e:
        logger.error("profile.query_failed", error=str(e))
        raise HTTPException(status_code=503, detail="数据库不可用")

    profile = compute_profile(list(reviews))
    profile["user_id"] = user
    return profile
