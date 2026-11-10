# backend/api/v1/review.py
# 提交评审（zip 或 git 仓库）→ 异步后台执行 → 查询状态与结果。

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import uuid

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Query
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import select

from backend.config import get_settings
from backend.core.memory import build_config
from backend.core.security import get_current_user, decode_access_token
from backend.core import progress
from backend.orchestrator import route, run_agent
from backend.core.logger import get_logger
from backend.db.models import Review, Submission
from backend.db.session import get_session_factory

router = APIRouter()
logger = get_logger(__name__)


# ── 提交（异步）─────────────────────────────────────────────
@router.post("/")
async def submit_review(
    file: UploadFile = File(None),
    git_url: str = Form(""),
    session_id: str = Form(""),
    user: str = Depends(get_current_user),
):
    """提交评审（zip 或 git 仓库），异步后台执行，立即返回 submission_id。"""
    if not file and not git_url:
        raise HTTPException(status_code=400, detail="请提供 zip 文件或 git 仓库地址")

    sid = session_id or str(uuid.uuid4())
    tmp_dir = tempfile.mkdtemp()

    if file:
        if not (file.filename or "").endswith(".zip"):
            raise HTTPException(status_code=400, detail="仅支持 .zip 格式")
        source_path = os.path.join(tmp_dir, f"{sid}.zip")
        written = 0
        max_upload = get_settings().review_upload_max_bytes
        try:
            with open(source_path, "wb") as f:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_upload:
                        raise HTTPException(
                            status_code=413,
                            detail=f"上传文件超过 {max_upload // (1024 * 1024)}MB 上限",
                        )
                    f.write(chunk)
        except HTTPException:
            if os.path.exists(source_path):
                os.remove(source_path)
            raise
        source_type = "zip"
    else:
        source_path = git_url
        source_type = "git"

    await _create_submission(sid, user)
    asyncio.create_task(_run_review(sid, user, source_path, source_type, tmp_dir))

    return {"submission_id": sid, "status": "pending"}


async def _create_submission(submission_id: str, user_id: str) -> None:
    """创建 pending 状态的 submission 记录。"""
    try:
        factory = get_session_factory()
        async with factory() as session:
            session.add(Submission(id=submission_id, user_id=user_id, status="pending"))
            await session.commit()
    except Exception as e:
        logger.error("review.create_submission_failed", error=str(e))


async def _run_review(submission_id: str, user_id: str, source_path: str, source_type: str, tmp_dir: str) -> None:
    """后台任务：clone（如需）→ 评审 → 落库 → 更新状态。"""
    try:
        if source_type == "git":
            clone_dir = os.path.join(tmp_dir, "repo")
            cp = subprocess.run(
                ["git", "clone", "--depth", "1", source_path, clone_dir],
                capture_output=True, text=True, timeout=120,
            )
            if cp.returncode != 0:
                raise RuntimeError(f"git clone 失败: {(cp.stderr or '')[:200]}")
            source_path = clone_dir

        initial_state = {
            "messages": [],
            "user_id": user_id,
            "tenant_id": "tenant_default",
            "session_id": submission_id,
            "zip_local_path": source_path,
        }
        agent = await route(f"代码评审 {source_type}")
        await _update_submission(submission_id, status="pending", agent_type=agent.name)
        result = await run_agent(agent, initial_state, build_config(user_id, submission_id))

        if result.get("fallback_used"):
            # LLM 降级：不落库为正常结果，标记 failed 以在前端提示
            await _update_submission(submission_id, status="failed",
                                     error=result.get("review_summary", "评审服务暂时不可用，请稍后重试"))
            logger.warning("review.degraded", submission_id=submission_id)
        else:
            await _persist_review(submission_id, result)
            await _update_submission(submission_id, status="completed")
            logger.info("review.async_done", submission_id=submission_id)
    except Exception as e:
        logger.error("review.async_failed", error=str(e), exc_info=True)
        await _update_submission(submission_id, status="failed", error=str(e))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def _persist_review(submission_id: str, result: dict) -> None:
    """评审结果落库（更新 submission 统计 + 插入 review）；失败仅记日志。"""
    try:
        stats = result.get("ignore_stats", {})
        award = result.get("title_award", {})
        factory = get_session_factory()
        async with factory() as session:
            sub = await session.get(Submission, submission_id)
            if sub:
                sub.language = result.get("language", "")
                sub.source_count = stats.get("source_count", 0)
                sub.focus_count = stats.get("focus_count", 0)
                sub.structure_count = stats.get("structure_count", 0)
                sub.ignored_count = stats.get("ignored_count", 0)
            session.add(Review(
                submission_id=submission_id,
                total_score=result.get("total_score", 0),
                full_score=result.get("full_score", 100),
                summary=result.get("review_summary", ""),
                title=award.get("title", ""),
                level=award.get("level", 1),
                easter_egg=award.get("easter_egg", ""),
                reason=award.get("reason", ""),
                dimension_scores=result.get("dimension_scores", []),
                static_metrics=result.get("static_metrics", {}),
            ))
            await session.commit()
    except Exception as e:
        logger.error("review.persist_failed", error=str(e))


async def _update_submission(
    submission_id: str,
    status: str,
    error: str = "",
    agent_type: str | None = None,
) -> None:
    """更新 submission 状态。"""
    try:
        factory = get_session_factory()
        async with factory() as session:
            sub = await session.get(Submission, submission_id)
            if sub:
                sub.status = status
                if error:
                    sub.error = error
                if agent_type:
                    sub.agent_type = agent_type
                await session.commit()
    except Exception as e:
        logger.error("review.update_submission_failed", error=str(e))


# ── 查询 ─────────────────────────────────────────────────
@router.get("/")
async def list_reviews(limit: int = 20, user: str = Depends(get_current_user)):
    """用户的历史提交列表（含状态；pending 的暂未生成结果）。"""
    try:
        factory = get_session_factory()
        async with factory() as session:
            stmt = (
                select(Submission, Review)
                .outerjoin(Review, Review.submission_id == Submission.id)
                .where(Submission.user_id == user)
                .order_by(Submission.created_at.desc())
                .limit(min(limit, 100))
            )
            rows = (await session.execute(stmt)).all()
    except Exception as e:
        logger.error("review.list_failed", error=str(e))
        raise HTTPException(status_code=503, detail="数据库不可用")
    return {
        "user_id": user,
        "count": len(rows),
        "items": [
            {
                "submission_id": sub.id,
                "language": sub.language,
                "status": sub.status,
                "total_score": rev.total_score if rev else None,
                "title": rev.title if rev else "",
                "level": rev.level if rev else None,
                "easter_egg": rev.easter_egg if rev else "",
                "created_at": sub.created_at.isoformat() if sub.created_at else None,
            }
            for sub, rev in rows
        ],
    }


@router.get("/{submission_id}/stream")
async def stream_progress(submission_id: str, token: str = Query(...)):
    """SSE：订阅评审进度（EventSource 无法带自定义请求头，token 走查询参数）。"""
    try:
        payload = decode_access_token(token)
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="凭证无效")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="凭证无效")

    factory = get_session_factory()
    try:
        async with factory() as session:
            sub = await session.get(Submission, submission_id)
            if sub is None or sub.user_id != username:
                raise HTTPException(status_code=404, detail="未找到该提交记录")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="数据库不可用")

    async def gen():
        q = progress.subscribe(submission_id)
        try:
            yield {"event": "ready", "data": json.dumps({"submission_id": submission_id})}
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                yield {"event": "progress", "data": json.dumps(event, ensure_ascii=False)}
        finally:
            progress.unsubscribe(submission_id, q)

    return EventSourceResponse(gen())


@router.get("/{submission_id}")
async def get_review(submission_id: str, user: str = Depends(get_current_user)):
    """按 submission_id 查询状态与评审结果。"""
    try:
        factory = get_session_factory()
        async with factory() as session:
            sub = await session.get(Submission, submission_id)
            if sub is None or sub.user_id != user:
                raise HTTPException(status_code=404, detail="未找到该提交记录")
            if sub.status == "pending":
                return {"submission_id": submission_id, "status": "pending"}
            if sub.status == "failed":
                return {"submission_id": submission_id, "status": "failed", "error": sub.error}
            rev = (await session.execute(
                select(Review).where(Review.submission_id == submission_id)
            )).scalar_one_or_none()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("review.get_failed", error=str(e))
        raise HTTPException(status_code=503, detail="数据库不可用")

    if rev is None:
        return {"submission_id": submission_id, "status": sub.status}

    return {
        "submission_id": submission_id,
        "status": sub.status,
        "language": sub.language,
        "stats": {
            "source_count": sub.source_count,
            "focus_count": sub.focus_count,
            "structure_count": sub.structure_count,
            "ignored_count": sub.ignored_count,
        },
        "total_score": rev.total_score,
        "full_score": rev.full_score,
        "dimension_scores": rev.dimension_scores,
        "title_award": {
            "title": rev.title,
            "level": rev.level,
            "easter_egg": rev.easter_egg,
            "reason": rev.reason,
        },
        "summary": rev.summary,
        "created_at": rev.created_at.isoformat() if rev.created_at else None,
    }
