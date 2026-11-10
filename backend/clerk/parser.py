# backend/clerk/parser.py
# 仓库解析官：安全解压 zip → 语言识别 → 三层分区（焦点/结构/忽略）→ 输出中间表示。

import os
import zipfile

from backend.config import get_settings
from backend.core.logger import get_logger
from backend.core.exceptions import RepoParseError

logger = get_logger(__name__)

# 忽略目录：生成物 / 依赖 / 工具目录
IGNORE_DIRS = {
    ".git", "node_modules", "dist", "build", "vendor", "__pycache__",
    ".idea", ".vscode", "target", ".venv", "venv", "env", ".mypy_cache",
    ".pytest_cache", ".tox", "coverage",
}

# 忽略的文件扩展名（二进制 / 媒体 / 包）
IGNORE_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".bmp", ".webp",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".tar", ".gz", ".rar", ".7z", ".jar", ".war", ".ear",
    ".pyc", ".pyo", ".class", ".so", ".dll", ".dylib", ".exe", ".bin",
    ".db", ".sqlite", ".sqlite3", ".lock", ".woff", ".ttf", ".eot", ".map",
    ".mp3", ".mp4", ".avi", ".mov",
}

CODE_EXTS = {".py": "python", ".java": "java", ".js": "javascript",
             ".ts": "typescript", ".go": "go", ".c": "c", ".cpp": "cpp"}

# 入口文件候选（按 basename）
ENTRY_NAMES = {
    "main.py", "app.py", "__main__.py", "manage.py", "run.py", "cli.py", "setup.py",
    "Main.java", "Application.java",
}

MAX_EXTRACT_BYTES = 500 * 1024 * 1024    # 解压总上限 500MB
MAX_FILE_BYTES = 50 * 1024 * 1024        # 单文件上限 50MB


def est_tokens(code: str) -> int:
    """粗略估算 token 数（英文代码约 4 字符 ≈ 1 token）。"""
    return max(1, len(code) // 4)


def safe_extract(zip_path: str) -> str:
    """安全解压：防 zip 炸弹 + 路径穿越。返回解压目录。"""
    extract_dir = os.path.join(os.path.dirname(zip_path), "extracted")
    os.makedirs(extract_dir, exist_ok=True)
    total = 0
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                # 防路径穿越
                norm = os.path.normpath(info.filename)
                if norm.startswith("..") or os.path.isabs(norm):
                    raise RepoParseError(f"非法路径条目: {info.filename}")
                total += info.file_size
                if total > MAX_EXTRACT_BYTES:
                    raise RepoParseError("解压总量超过 500MB 上限")
                if info.file_size > MAX_FILE_BYTES:
                    raise RepoParseError(f"单文件过大: {info.filename}")
            zf.extractall(extract_dir)
    except RepoParseError:
        raise
    except Exception as e:
        raise RepoParseError(f"解压失败: {e}")
    return extract_dir


def _read_code(full_path: str, max_bytes: int = 2 * 1024 * 1024) -> str:
    try:
        with open(full_path, "rb") as f:
            data = f.read(max_bytes)
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("gbk", errors="ignore")
        except Exception:
            return ""
    except Exception:
        return ""


def collect_source_files(root: str) -> list[dict]:
    """遍历收集源码文件；忽略层/二进制在此过滤。"""
    files = []
    ignored_count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            if ext in IGNORE_EXTS:
                ignored_count += 1
                continue
            if ext not in CODE_EXTS:
                ignored_count += 1
                continue
            code = _read_code(full)
            files.append({
                "rel_path": rel,
                "full_path": full,
                "ext": ext,
                "language": CODE_EXTS[ext],
                "lines": code.count("\n") + 1 if code else 0,
                "code": code,
            })
    return files, ignored_count


def detect_language(files: list[dict]) -> str:
    """按源码文件数统计主语言，默认 python。"""
    from collections import Counter
    counter = Counter(f["language"] for f in files)
    if not counter:
        return "python"
    return counter.most_common(1)[0][0]


def build_layers(files: list[dict], language: str) -> dict:
    """三层分区：入口优先进焦点层，其余按体量降序，受 token 预算与文件数上限约束。"""
    settings = get_settings()
    budget = settings.review_token_budget
    limit = settings.review_focus_file_limit
    giant_threshold = settings.review_giant_file_lines

    lang_files = [f for f in files if f["language"] == language]
    other_files = [f for f in files if f["language"] != language]
    # 稳定排序：入口在前，其余按行数降序
    lang_files.sort(key=lambda f: (
        0 if os.path.basename(f["rel_path"]) in ENTRY_NAMES else 1,
        -f["lines"],
    ))

    focus, structure = [], []
    used = 0
    for f in lang_files:
        is_giant = f["lines"] >= giant_threshold
        if not is_giant and len(focus) < limit and used + est_tokens(f["code"]) <= budget:
            focus.append(f)
            used += est_tokens(f["code"])
        else:
            structure.append(f)
    # 非主语言源码文件归入结构层（只做结构概览，不进焦点深评）
    structure.extend(other_files)

    giant_files = [
        {"path": f["rel_path"], "lines": f["lines"]}
        for f in files if f["lines"] >= giant_threshold
    ]
    return {
        "focus_layer": focus,
        "structure_layer": structure,
        "ignore_stats": {},
        "static_metrics": {"giant_files": giant_files, "focus_token_est": used},
    }


def detect_duplicates(files: list[dict], min_lines: int = 6, min_chars: int = 40) -> list[dict]:
    """跨文件重复块检测：规范化行 → 不重叠 n-gram 哈希 → 出现 ≥2 处即重复块。"""
    import hashlib
    from collections import defaultdict
    from typing import Optional

    def _norm(line: str) -> Optional[str]:
        s = line.strip()
        if not s or s.lstrip().startswith(("#", "//", "/*", "*", "'''", '"""')):
            return None
        return s

    groups: dict[str, list[dict]] = defaultdict(list)
    for f in files:
        normed = []
        for i, raw in enumerate(f.get("code", "").splitlines(), start=1):
            n = _norm(raw)
            if n is not None:
                normed.append((i, n))
        for start in range(0, len(normed) - min_lines + 1, min_lines):
            window = normed[start:start + min_lines]
            text = "\n".join(n for _, n in window)
            if len(text) < min_chars:
                continue
            h = hashlib.md5(text.encode("utf-8")).hexdigest()[:16]
            groups[h].append({
                "file": f["rel_path"],
                "start_line": window[0][0],
                "end_line": window[-1][0],
            })

    duplicated = []
    for h, occ in groups.items():
        if len(occ) >= 2:
            duplicated.append({"key": h, "lines": min_lines, "blocks": occ})
    return duplicated


def parse_repo(source_path: str) -> dict:
    """解析入口：zip 或目录 → 三层分区中间表示。"""
    if source_path.endswith(".zip"):
        extract_dir = safe_extract(source_path)
    else:
        extract_dir = source_path  # 已是目录（git clone 结果）
    files, ignored_count = collect_source_files(extract_dir)
    language = detect_language(files)
    layers = build_layers(files, language)
    layers["static_metrics"]["duplicated_blocks"] = detect_duplicates(files)
    layers["ignore_stats"] = {
        "ignored_count": ignored_count,
        "source_count": len(files),
        "focus_count": len(layers["focus_layer"]),
        "structure_count": len(layers["structure_layer"]),
    }
    return {"language": language, **layers}