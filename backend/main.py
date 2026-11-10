# backend/main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.core.logger import configure_logging, get_logger
from backend.api.router import api_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger = get_logger(__name__)
    logger.info("app.starting | env=%s port=%s", settings.app_env, settings.app_port)
    try:
        from backend.db.migrations import run_migrations
        await run_migrations()
        logger.info("db.migrated")
    except Exception as e:
        logger.warning("db.migrate_failed", error=str(e))  # DB 未起不阻断启动
    yield
    logger.info("app.shutting_down")


app = FastAPI(
    title="CodeEval API",
    description="工程代码质量评审平台 API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://localhost:5173", "http://localhost:8080",
        "http://127.0.0.1:3000", "http://127.0.0.1:5173", "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["系统"])
async def health_check():
    return {"status": "ok", "env": settings.app_env}