# scripts/build_kb.py
# 构建规范知识库：内置精选规范条目 → embedding → 入库 Milvus。
# 用法：docker exec code_eval_backend python scripts/build_kb.py

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.rag.embedder import embed_texts
from backend.rag.milvus_client import upsert_chunks

# 精选规范条目（source_name / source_url / language / title / content）
# 来源只做官方文档（PEP 8 = PSF License，Google Style = CC BY 3.0，均保留出处链接）。
STYLE_ENTRIES = [
    # ── 命名规范 ──
    ("PEP 8", "https://peps.python.org/pep-0008/#naming-conventions", "python",
     "函数与变量命名",
     "函数名、变量名、属性名应使用小写字母，单词之间用下划线分隔（snake_case），例如 my_function、total_count。禁止使用 camelCase 或 PascalCase 命名函数。"),
    ("PEP 8", "https://peps.python.org/pep-0008/#naming-conventions", "python",
     "类命名",
     "类名应使用 CapWords（PascalCase）约定，例如 MyClass、UserService。类内部方法名仍使用 snake_case。"),
    ("PEP 8", "https://peps.python.org/pep-0008/#naming-conventions", "python",
     "常量命名",
     "模块级常量应使用全大写字母，单词之间用下划线分隔（UPPER_CASE），例如 MAX_OVERFLOW、DEFAULT_TIMEOUT。"),
    ("PEP 8", "https://peps.python.org/pep-0008/#naming-conventions", "python",
     "避免误导性命名",
     "不要使用单个字母 l、O、I 作为变量名（易与数字 1、0 混淆）。避免使用无意义或过于泛化的名称，如 data、info、temp。"),
    ("Google Style", "https://google.github.io/styleguide/pyguide.html#3164-guidelines-derived-from-guidos-recommendations", "python",
     "单字母变量仅限计数器",
     "单字符变量名仅在计数器或迭代器场景可用（如 i、j）。其他场景应使用描述性名称，避免命名过于简短无法自解释。"),

    # ── 缩进与格式 ──
    ("PEP 8", "https://peps.python.org/pep-0008/#indentation", "python",
     "缩进规则",
     "每个缩进层级使用 4 个空格，禁止使用 Tab 键。同一代码块内缩进必须一致，不得混用空格与 Tab。"),
    ("PEP 8", "https://peps.python.org/pep-0008/#maximum-line-length", "python",
     "行宽限制",
     "所有行不超过 79 个字符，文档字符串或注释不超过 72 个字符。过长的表达式应使用括号换行。"),
    ("PEP 8", "https://peps.python.org/pep-0008/#blank-lines", "python",
     "空行规范",
     "顶层函数与类定义之间用 2 个空行分隔，类内方法之间用 1 个空行分隔。适当使用空行组织代码逻辑块。"),
    ("Google Style", "https://google.github.io/styleguide/pyguide.html#32-line-length", "python",
     "行宽（Google）",
     "每行最多 80 个字符。Python 代码中，隐式续行（括号内换行）优先于显式续行（反斜杠）。"),

    # ── import 规范 ──
    ("PEP 8", "https://peps.python.org/pep-0008/#imports", "python",
     "import 规范",
     "每个 import 语句单独占一行（import os 而非 import os, sys）。import 应分组：标准库、第三方库、本地模块，组间用空行分隔。"),
    ("PEP 8", "https://peps.python.org/pep-0008/#imports", "python",
     "避免通配符导入",
     "禁止使用 from module import *，会导致命名空间污染、可读性下降，且难以追踪符号来源。"),

    # ── 注释与文档 ──
    ("PEP 8", "https://peps.python.org/pep-0008/#comments", "python",
     "注释规范",
     "注释应是完整句子，首字母大写。行内注释与代码至少间隔 2 个空格。注释应解释「为什么」而非「做了什么」（代码本身已说明做了什么）。"),
    ("PEP 8", "https://peps.python.org/pep-0008/#documentation-strings", "python",
     "docstring 规范",
     "所有公共模块、函数、类、方法都应写 docstring。docstring 描述函数用途、参数与返回值，用三引号包裹。"),
    ("Google Style", "https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings", "python",
     "docstring 三要素",
     "函数 docstring 应包含三要素：Args（参数说明）、Returns（返回值说明）、Raises（可能抛出的异常）。"),

    # ── 类型注解 ──
    ("Google Style", "https://google.github.io/styleguide/pyguide.html#319-type-annotations", "python",
     "类型注解",
     "公共 API 的函数签名应使用类型注解，提升可读性与静态检查能力。例如 def add(a: int, b: int) -> int:。"),

    # ── 健壮性与风格 ──
    ("Google Style", "https://google.github.io/styleguide/pyguide.html#37-main", "python",
     "文件编码",
     "源代码文件使用 UTF-8 编码，读取文件时显式指定 encoding='utf-8'，避免依赖平台默认编码。"),
    ("PEP 8", "https://peps.python.org/pep-0008/#whitespace-in-expressions-and-statements", "python",
     "空格规范",
     "二元运算符两侧各加一个空格（a = b + c）。逗号、冒号、分号后加空格，前不加。函数默认参数的等号两侧不加空格（def f(x=1)）。"),
    ("PEP 8", "https://peps.python.org/pep-0008/#programming-recommendations", "python",
     "布尔判断",
     "与 None 比较使用 is / is not，而非 ==。空序列判断直接使用 if seq 而非 if len(seq) == 0。"),
    ("Google Style", "https://google.github.io/styleguide/pyguide.html#21-lint", "python",
     "魔法数字",
     "避免在代码中使用含义不明的魔法数字，应提取为具名常量。例如使用 MAX_RETRIES = 3 而非直接写 3。"),
    ("PEP 8", "https://peps.python.org/pep-0008/#programming-recommendations", "python",
     "异常处理",
     "捕获异常时尽量具体（except ValueError 而非裸 except），不要用异常做正常流程控制，异常信息应提供上下文。"),
]


def main() -> None:
    chunks = []
    for i, (source_name, source_url, language, title, content) in enumerate(STYLE_ENTRIES):
        vec = embed_texts([content])[0]
        chunks.append({
            "content": content,
            "embedding": vec,
            "source_name": source_name,
            "source_url": source_url,
            "language": language,
            "title": title,
            "chunk_index": i,
            "document_id": f"{source_name}:{title}",
        })
    n = upsert_chunks(chunks)
    print(f"知识库入库完成：{n} 条切片")


if __name__ == "__main__":
    main()
