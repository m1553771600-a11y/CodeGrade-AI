# backend/clerk/nodes.py
# 评审 Agent 的图节点。

import asyncio
import os

from langchain_core.messages import SystemMessage, HumanMessage

from backend.clerk.state import ReviewState, ReviewScores, TitleAward
from backend.clerk.parser import parse_repo
from backend.clerk.linters import analyze_python_file, analyze_structure_python, summarize_giant_file, run_bandit
from backend.clerk.prompts import DIMENSIONS, SYSTEM_PROMPT, REVIEW_PROMPT, TITLE_PROMPT
from backend.core.llm_factory import get_structured_llm, get_llm
from backend.core.retry import with_retry
from backend.core.logger import get_logger
from backend.core.progress import publish

logger = get_logger(__name__)

# ── 段位表（按分数下限降序）──
TITLE_LEVELS = [
    (97, 10, "软件工程神谕"),
    (94, 9, "抽象画圣手"),
    (88, 8, "熵减贤者"),
    (80, 7, "单一职责修道僧"),
    (70, 6, "重构炼金师"),
    (55, 5, "if-else 编织者"),
    (40, 4, "熵增传道人"),
    (25, 3, "面条码圣"),
    (10, 2, "Ctrl-V 苦行僧"),
    (0, 1, "代码游魂"),
]


def level_from_score(score: int) -> tuple[str, int]:
    for min_score, level, title in TITLE_LEVELS:
        if score >= min_score:
            return title, level
    return "代码游魂", 1


def _egg_from_state(state: ReviewState) -> str:
    """彩蛋称号：基于维度/静态特征触发（规则引擎）。"""
    metrics = state.get("static_metrics", {})
    if metrics.get("giant_files"):
        return "巨石镇守者"
    scores = state.get("dimension_scores", [])
    by_key = {s["dimension"]: s for s in scores}
    if by_key.get("robustness", {}).get("score", 20) <= 0:
        return "裸奔代码骑士"
    if by_key.get("style", {}).get("score", 0) >= 15:
        return "格式化宗师"
    return ""


# ── 节点1：解析 ─────────────────────────────────────────────
async def parse_node(state: ReviewState) -> dict:
    parsed = parse_repo(state["zip_local_path"])
    logger.info("clerk.parse_done", language=parsed["language"],
                **parsed["ignore_stats"])
    publish(state["session_id"], {"stage": "parse", "message": "代码解析完成，开始静态分析"})
    return {
        "language": parsed["language"],
        "focus_layer": parsed["focus_layer"],
        "structure_layer": parsed["structure_layer"],
        "ignore_stats": parsed["ignore_stats"],
        "static_metrics": parsed["static_metrics"],
    }


# ── 节点2：静态分析 ─────────────────────────────────────────
async def lint_node(state: ReviewState) -> dict:
    from backend.config import get_settings
    giant_threshold = get_settings().review_giant_file_lines

    metrics = state.get("static_metrics", {})
    file_metrics = {}
    max_cyc = 0
    # 批量跑 bandit：避免逐文件子进程开销
    python_focus = [f for f in state.get("focus_layer", []) if f["language"] == "python"]
    bandit_map = run_bandit([f["full_path"] for f in python_focus]) if python_focus else {}
    for f in python_focus:
        issues = bandit_map.get(os.path.normcase(os.path.abspath(f["full_path"])), [])
        analysis = analyze_python_file(f["full_path"], f["code"], security_issues=issues)
        file_metrics[f["rel_path"]] = analysis
        max_cyc = max(max_cyc, analysis["cyclomatic_max"])

    # 结构层：轻量静态分析（只跑 radon，不跑 bandit），产出类/函数/命名问题概览
    structure_summary = []
    giant_summaries = []
    for f in state.get("structure_layer", []):
        if f["language"] == "python":
            s = analyze_structure_python(f["rel_path"], f["code"])
            structure_summary.append({
                "path": f["rel_path"],
                "lines": f["lines"],
                "class_count": s["class_count"],
                "func_count": len(s["funcs"]),
                "naming_issue_count": len(s["naming_issues"]),
            })
            if f["lines"] >= giant_threshold:
                giant_summaries.append(summarize_giant_file(f["rel_path"], f["code"]))
        else:
            structure_summary.append({
                "path": f["rel_path"],
                "lines": f["lines"],
                "class_count": 0,
                "func_count": 0,
                "naming_issue_count": 0,
            })

    metrics["file_metrics"] = file_metrics
    metrics["max_cyclomatic"] = max_cyc
    metrics["giant_summaries"] = giant_summaries
    logger.info("clerk.lint_done", files=len(file_metrics), max_cyclomatic=max_cyc,
                structure=len(structure_summary), giants=len(giant_summaries))
    publish(state["session_id"], {"stage": "lint", "message": "静态分析完成，开始 LLM 六维评审"})
    return {"static_metrics": metrics, "structure_summary": structure_summary}


def _render_style_guidelines(hits: list[dict]) -> str:
    """把 RAG 检索到的规范判据渲染成给 LLM 看的文本。"""
    if not hits:
        return "（无）"
    return "\n".join(
        f"- 【{h['title']}】{h['content']}（来源：{h['source_name']} {h['source_url']}）"
        for h in hits
    )


def _render_giant_summaries(giant_summaries: list[dict]) -> str:
    """把巨文件函数级摘要渲染成给 LLM 看的文本。"""
    if not giant_summaries:
        return "（无）"
    parts = []
    for g in giant_summaries:
        funcs = []
        for f in g.get("top_functions", []):
            name = f"{f['classname']}.{f['name']}" if f.get("classname") else f["name"]
            funcs.append(f"{name}（圈复杂度 {f['complexity']}）")
        parts.append(
            f"### {g['path']}（{g['total_lines']} 行，函数级摘要）\n"
            f"文件头部：\n```\n{g['head']}\n```\n"
            f"复杂度最高函数：{'；'.join(funcs)}"
        )
    return "\n\n".join(parts)


# ── 节点3：LLM 六维度评审 ──────────────────────────────────
@with_retry(agent_type="review")
async def _llm_review(state: ReviewState) -> ReviewScores:
    language = state.get("language", "python")
    metrics = state.get("static_metrics", {})

    dimension_rules = "\n".join(
        f"- {key}（{name}）：满分 {weight}，{desc}"
        for key, name, weight, desc in DIMENSIONS
    )
    focus_code = "\n\n".join(
        f"### 文件：{f['rel_path']} ({f['lines']} 行)\n```\n{f['code']}\n```"
        for f in state.get("focus_layer", [])
    )
    structure_summary = state.get("structure_summary", [])
    structure_text = "\n".join(
        f"- {s['path']}（{s['lines']} 行，{s.get('class_count', 0)} 类 / "
        f"{s.get('func_count', 0)} 函数 / 命名问题 {s.get('naming_issue_count', 0)}）"
        for s in structure_summary
    ) or "（无其他源码文件）"

    static_text = (
        f"最大圈复杂度：{metrics.get('max_cyclomatic', 0)}\n"
        f"疑似巨石文件：{metrics.get('giant_files', [])}\n"
        f"重复代码块：{len(metrics.get('duplicated_blocks', []))} 处\n"
        f"焦点层估算 token：{metrics.get('focus_token_est', 0)}"
    )

    giant_text = _render_giant_summaries(metrics.get("giant_summaries", []))

    # RAG：检索官方规范判据（Milvus 不可用/无数据时降级为「无」，不阻断评审）
    style_guidelines = ""
    try:
        from backend.rag.retriever import retrieve
        query = f"{language} 代码风格规范 命名 缩进 注释 类型注解 异常处理 import"
        hits = await asyncio.to_thread(retrieve, query, top_k=5)
        style_guidelines = _render_style_guidelines(hits)
    except Exception as e:
        logger.warning("clerk.rag_retrieve_failed", error=str(e))
        style_guidelines = "（无）"

    # 用户代码里可能含 { }，注入前转义，否则 str.format 会把它们当占位符抛错
    def _esc(s: str) -> str:
        return s.replace("{", "{{").replace("}", "}}")

    prompt = REVIEW_PROMPT.format(
        language=language,
        dimension_rules=dimension_rules,
        focus_code=_esc(focus_code),
        structure_summary=structure_text,
        static_metrics=static_text,
        giant_files=_esc(giant_text),
        style_guidelines=style_guidelines,
        keys=",".join(k for k, _, _, _ in DIMENSIONS),
    )
    llm = get_structured_llm("review", ReviewScores)
    return await llm.ainvoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])


def _default_summary(total: int, dimension_scores: list[dict]) -> str:
    """LLM 未返回 summary 时，用维度得分规则生成兜底总结。"""
    names = {k: n for k, n, _, _ in DIMENSIONS}
    if not dimension_scores:
        return f"综合得分 {total}/100。"
    ranked = sorted(dimension_scores, key=lambda s: s["score"] / s["weight"] if s["weight"] else 0)
    low = ranked[0]
    high = ranked[-1]
    level = "良好" if total >= 70 else "中等" if total >= 50 else "有待提升"
    return (f"综合得分 {total}/100，整体表现{level}。"
            f"亮点在「{names.get(high['dimension'], high['dimension'])}」，"
            f"短板在「{names.get(low['dimension'], low['dimension'])}」。")


async def review_node(state: ReviewState) -> dict:
    result = await _llm_review(state)
    if isinstance(result, dict):
        # LLM 失败走降级：标记降级，返回空结果，不崩溃
        logger.warning("clerk.review_fallback_used")
        publish(state["session_id"], {"stage": "review", "message": "LLM 评审降级，生成称号"})
        return {"dimension_scores": [], "total_score": 0,
                "review_summary": "评审服务暂时不可用，请稍后重试。",
                "fallback_used": True}
    weight_map = {k: w for k, _, w, _ in DIMENSIONS}
    total = 0
    dimension_scores = []
    for ds in result.dimension_scores:
        weight = weight_map.get(ds.dimension, 0)
        score = max(0, min(ds.score, weight))
        total += score
        dimension_scores.append({
            "dimension": ds.dimension,
            "score": score,
            "weight": weight,
            "issues": [i.model_dump() for i in ds.issues],
        })
    summary = result.summary or _default_summary(total, dimension_scores)
    logger.info("clerk.review_done", total=total)
    publish(state["session_id"], {"stage": "review", "message": "六维评审完成，生成称号"})
    return {"dimension_scores": dimension_scores, "total_score": total, "review_summary": summary}


# ── 节点4：称号 + 颁奖词 ───────────────────────────────────
async def award_node(state: ReviewState) -> dict:
    total = state.get("total_score", 0)
    title, level = level_from_score(total)
    easter_egg = _egg_from_state(state)

    scores = state.get("dimension_scores", [])
    names = {k: n for k, n, _, _ in DIMENSIONS}
    dimension_brief = ", ".join(f"{names.get(s['dimension'], s['dimension'])} {s['score']}/{s['weight']}" for s in scores)

    # 突出点：得分率最低 vs 最高
    def _rate(s):
        return s["score"] / s["weight"] if s["weight"] else 0
    ranked = sorted(scores, key=_rate)
    highlight = "整体均衡"
    if ranked:
        low = ranked[0]
        high = ranked[-1]
        highlight = (
            f"短板在「{names.get(low['dimension'], low['dimension'])}」，"
            f"亮点在「{names.get(high['dimension'], high['dimension'])}」"
        )

    reason = ""
    try:
        llm = get_llm("title")
        resp = await llm.ainvoke([HumanMessage(content=TITLE_PROMPT.format(
            total_score=total, full_score=100, title=title,
            dimension_brief=dimension_brief, highlight=highlight,
        ))])
        reason = resp.content if isinstance(resp.content, str) else str(resp.content)
        reason = reason.strip()
    except Exception as e:
        logger.warning("clerk.title_failed", error=str(e))

    award = TitleAward(level=level, title=title, easter_egg=easter_egg, reason=reason)
    publish(state["session_id"], {"stage": "award", "message": "评审完成"})
    return {"title_award": award.model_dump()}