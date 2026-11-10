# backend/rag/embedder.py
# 轻量 embedding（all-MiniLM-L6-v2，384 维 dense），进程内单例。

from backend.config import get_settings
from backend.core.logger import get_logger

logger = get_logger(__name__)

_instance = None


def get_embedder():
    """懒加载 embedding 模型单例（首次调用约几秒）。"""
    global _instance
    if _instance is None:
        from sentence_transformers import SentenceTransformer
        model = get_settings().embedding_model
        logger.info("rag.embedder_loading", model=model)
        _instance = SentenceTransformer(model)
        logger.info("rag.embedder_loaded", model=model)
    return _instance


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量编码文本，返回 384 维归一化向量（list[list[float]]）。"""
    model = get_embedder()
    return model.encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()
