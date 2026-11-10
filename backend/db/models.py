# backend/db/models.py
# 落库表结构：submissions（提交）+ reviews（评审结果，维度得分/静态指标存 JSONB）。

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True, default="anonymous")
    tenant_id: Mapped[str] = mapped_column(String(64), default="tenant_default")
    language: Mapped[str] = mapped_column(String(16), default="python")
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    focus_count: Mapped[int] = mapped_column(Integer, default=0)
    structure_count: Mapped[int] = mapped_column(Integer, default=0)
    ignored_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="completed")  # pending / completed / failed
    agent_type: Mapped[str] = mapped_column(String(32), default="code-review")  # 由编排器路由决定
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    review: Mapped[Optional["Review"]] = relationship(back_populates="submission", uselist=False)


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    submission_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("submissions.id"), unique=True, index=True
    )
    total_score: Mapped[int] = mapped_column(Integer, default=0)
    full_score: Mapped[int] = mapped_column(Integer, default=100)
    summary: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(String(64), default="")
    level: Mapped[int] = mapped_column(Integer, default=1)
    easter_egg: Mapped[str] = mapped_column(String(64), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    dimension_scores: Mapped[list] = mapped_column(JSONB, default=list)
    static_metrics: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    submission: Mapped["Submission"] = relationship(back_populates="review")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
