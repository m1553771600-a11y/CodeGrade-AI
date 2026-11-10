# backend/api/v1/auth.py
# 认证：注册 / 登录，签发 JWT。

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.core.logger import get_logger
from backend.core.security import create_access_token, hash_password, verify_password
from backend.db.models import User
from backend.db.session import get_session_factory

router = APIRouter()
logger = get_logger(__name__)


class Credentials(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=4, max_length=128)


def _token_response(username: str) -> dict:
    return {
        "access_token": create_access_token(username),
        "token_type": "bearer",
        "username": username,
    }


@router.post("/register", status_code=201)
async def register(body: Credentials):
    factory = get_session_factory()
    try:
        async with factory() as session:
            exists = (await session.execute(
                select(User).where(User.username == body.username)
            )).scalar_one_or_none()
            if exists:
                raise HTTPException(status_code=409, detail="用户名已存在")
            session.add(User(username=body.username, password_hash=hash_password(body.password)))
            await session.commit()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("auth.register_failed", error=str(e))
        raise HTTPException(status_code=503, detail="数据库不可用")
    logger.info("auth.register_ok", username=body.username)
    return _token_response(body.username)


@router.post("/login")
async def login(body: Credentials):
    factory = get_session_factory()
    try:
        async with factory() as session:
            user = (await session.execute(
                select(User).where(User.username == body.username)
            )).scalar_one_or_none()
    except Exception as e:
        logger.error("auth.login_failed", error=str(e))
        raise HTTPException(status_code=503, detail="数据库不可用")
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    logger.info("auth.login_ok", username=body.username)
    return _token_response(body.username)
