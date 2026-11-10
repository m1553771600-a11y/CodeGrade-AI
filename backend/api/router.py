# backend/api/router.py
from fastapi import APIRouter

from backend.api.v1 import auth, profile, review

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["认证"])
api_router.include_router(review.router, prefix="/review", tags=["评审"])
api_router.include_router(profile.router, prefix="/profile", tags=["能力画像"])