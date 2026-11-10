# backend/rag/retriever.py
# 高层检索接口：查询文本 → embedding → Milvus dense 检索 → top-K 规范判据。

from backend.rag.embedder import embed_texts
from backend.rag.milvus_client import search
from backend.config import get_settings


def retrieve(query: str, tenant_id: str = "tenant_default", top_k: int = 3) -> list[dict]:
    """检索与 query 相关的规范文档切片，返回带来源的判据列表。"""
    if not query.strip():
        return []
    vec = embed_texts([query])[0]
    return search(vec, tenant_id=tenant_id, top_k=top_k)
