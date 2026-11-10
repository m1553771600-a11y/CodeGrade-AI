# backend/clerk/profiler.py
# 能力画像：聚合历史评审数据，规则计算六维熟练度 + 薄弱点 + 趋势（不依赖 LLM）。

from datetime import datetime

from backend.clerk.prompts import DIMENSIONS

WEAK_THRESHOLD = 0.6  # 维度得分率低于此视为薄弱


def _overall_level(avg_total: float) -> str:
    if avg_total >= 80:
        return "优秀"
    if avg_total >= 70:
        return "良好"
    if avg_total >= 50:
        return "中等"
    return "待提升"


def compute_profile(reviews: list) -> dict:
    """聚合历史评审（Review ORM 对象），生成六维能力画像。"""
    dim_rates: dict[str, list[float]] = {}
    dim_issue_counts: dict[str, int] = {}
    total_scores: list[int] = []

    for r in reviews:
        total_scores.append(r.total_score)
        for d in (r.dimension_scores or []):
            dim = d.get("dimension", "")
            weight = d.get("weight") or 1
            rate = d["score"] / weight if weight else 0.0
            dim_rates.setdefault(dim, []).append(rate)
            dim_issue_counts[dim] = dim_issue_counts.get(dim, 0) + len(d.get("issues") or [])

    dimensions = []
    for dim, name, weight, _ in DIMENSIONS:
        rates = dim_rates.get(dim, [])
        avg_rate = round(sum(rates) / len(rates), 3) if rates else None
        dimensions.append({
            "dimension": dim,
            "name": name,
            "weight": weight,
            "avg_rate": avg_rate,
            "avg_score": round(avg_rate * weight, 1) if avg_rate is not None else None,
            "issue_count": dim_issue_counts.get(dim, 0),
        })

    # 薄弱点：得分率 < 阈值，按得分率升序（最薄弱在前）
    weak_points = [
        d for d in dimensions
        if d["avg_rate"] is not None and d["avg_rate"] < WEAK_THRESHOLD
    ]
    weak_points.sort(key=lambda d: d["avg_rate"])

    # 趋势：按时间升序
    trend = [
        {
            "submission_id": r.submission_id,
            "total_score": r.total_score,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in sorted(reviews, key=lambda r: r.created_at or datetime.min)
    ]

    avg_total = round(sum(total_scores) / len(total_scores), 1) if total_scores else None

    return {
        "review_count": len(reviews),
        "avg_total_score": avg_total,
        "overall_level": _overall_level(avg_total) if avg_total is not None else None,
        "dimensions": dimensions,
        "weak_points": weak_points,
        "trend": trend,
    }
