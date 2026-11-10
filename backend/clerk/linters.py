# backend/clerk/linters.py
# 静态分析封装：radon（复杂度/维护指数）+ bandit（安全）。
# 工具在 try/except 内调用，未安装或失败时降级为空结果，不阻断评审。

import ast
import json
import os
import re
import subprocess
import sys

from backend.core.logger import get_logger

logger = get_logger(__name__)


def analyze_python_file(path: str, code: str, security_issues: list | None = None) -> dict:
    """对单个 Python 文件跑 radon 静态分析；bandit 结果由外部批量传入。"""
    result = {
        "path": path,
        "cyclomatic_max": 0,
        "cyclomatic_avg": 0.0,
        "functions": [],
        "maintainability": None,
        "loc": 0,
        "lloc": 0,
        "comments": 0,
        "security_issues": list(security_issues or []),
    }
    _radon_analyze(path, code, result)
    return result


def _radon_analyze(path: str, code: str, result: dict) -> None:
    try:
        from radon.complexity import cc_visit
        from radon.metrics import mi_visit
        from radon.raw import analyze
    except Exception:
        logger.warning("linters.radon_unavailable")
        return
    try:
        raw = analyze(code)
        result["loc"] = raw.loc
        result["lloc"] = raw.lloc
        result["comments"] = raw.comments
        result["maintainability"] = round(mi_visit(code, multi=True), 2)

        complexities = []
        for block in cc_visit(code):
            if hasattr(block, "complexity"):
                c = block.complexity
                complexities.append(c)
                result["functions"].append({
                    "name": getattr(block, "name", ""),
                    "classname": getattr(block, "classname", ""),
                    "complexity": c,
                    "lineno": getattr(block, "lineno", None),
                })
        if complexities:
            result["cyclomatic_max"] = max(complexities)
            result["cyclomatic_avg"] = round(sum(complexities) / len(complexities), 2)
    except Exception as e:
        logger.warning("linters.radon_failed", path=path, error=str(e))


def run_bandit(paths: list[str]) -> dict[str, list[dict]]:
    """对一批 Python 文件一次性跑 bandit，返回 {归一化路径: issues}。"""
    out: dict[str, list[dict]] = {}
    if not paths:
        return out
    try:
        cp = subprocess.run(
            [sys.executable, "-m", "bandit", "-q", "-f", "json", *paths],
            capture_output=True, text=True, timeout=180,
        )
        if not cp.stdout.strip():
            return out
        data = json.loads(cp.stdout)
        for r in data.get("results", []):
            fname = r.get("filename", "")
            if not fname:
                continue
            key = os.path.normcase(os.path.abspath(fname))
            out.setdefault(key, []).append({
                "severity": r.get("issue_severity", ""),
                "text": r.get("issue_text", ""),
                "line": r.get("line_number"),
                "test": r.get("test_name", ""),
            })
    except Exception as e:
        logger.warning("linters.bandit_batch_failed", error=str(e))
    return out


def _is_snake_case(name: str) -> bool:
    """Python 标识符是否 snake_case（魔术方法直接放行）。"""
    if name.startswith("__") and name.endswith("__"):
        return True
    return bool(re.fullmatch(r"[a-z_][a-z0-9_]*", name))


def analyze_structure_python(path: str, code: str) -> dict:
    """结构层轻量静态分析：只跑 radon（复杂度/函数列表），不跑 bandit（省时）。"""
    result = {
        "path": path,
        "total_lines": code.count("\n") + 1 if code else 0,
        "class_count": 0,
        "funcs": [],
        "naming_issues": [],
    }
    try:
        from radon.complexity import cc_visit
    except Exception:
        return result
    # radon 不暴露函数参数个数，用 ast 补一份 name → 参数数
    param_map = {}
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                param_map.setdefault(node.name, len(node.args.args))
    except Exception:
        pass
    try:
        classes = set()
        for block in cc_visit(code):
            name = getattr(block, "name", "")
            classname = getattr(block, "classname", "")
            complexity = getattr(block, "complexity", 0)
            lineno = getattr(block, "lineno", 0)
            endline = getattr(block, "endline", 0)
            if hasattr(block, "methods"):
                # 类块：只记入类集合，不当作函数（其方法会单独出现）
                classes.add(name)
                continue
            if classname:
                classes.add(classname)
            result["funcs"].append({
                "name": name,
                "classname": classname,
                "complexity": complexity,
                "lines": max(1, endline - lineno + 1),
                "params": param_map.get(name, 0),
            })
            if name and not _is_snake_case(name):
                result["naming_issues"].append({
                    "name": f"{classname}.{name}" if classname else name,
                    "issue": "命名不符合 snake_case 规范",
                })
        result["class_count"] = len(classes)
    except Exception as e:
        logger.warning("linters.structure_failed", path=path, error=str(e))
    return result


def summarize_giant_file(path: str, code: str, top_k: int = 5, head_lines: int = 60) -> dict:
    """巨文件函数级聚合：文件头部 + Top-K 复杂度函数签名，不塞全文。"""
    lines = code.splitlines()
    head = "\n".join(lines[:head_lines])
    funcs = []
    try:
        from radon.complexity import cc_visit
        for block in cc_visit(code):
            funcs.append({
                "name": getattr(block, "name", ""),
                "classname": getattr(block, "classname", ""),
                "complexity": getattr(block, "complexity", 0),
                "lineno": getattr(block, "lineno", 0),
                "endline": getattr(block, "endline", 0),
            })
        funcs.sort(key=lambda x: -x["complexity"])
        funcs = funcs[:top_k]
    except Exception as e:
        logger.warning("linters.giant_summarize_failed", path=path, error=str(e))
    return {
        "path": path,
        "total_lines": len(lines),
        "head": head,
        "top_functions": funcs,
    }