# backend/rag/milvus_client.py
# Milvus 客户端：collection schema + upsert + dense 检索。
# 本项目文档量小，只做 Dense ANN（COSINE），不做 BGE-M3 的 sparse hybrid，也不做 reranker。

import hashlib

from pymilvus import DataType, MilvusClient

from backend.config import get_settings
from backend.core.logger import get_logger

logger = get_logger(__name__)

EMBED_DIM = 384  # all-MiniLM-L6-v2

_client = None
_initialized = False


def _schema():
    from pymilvus import CollectionSchema, FieldSchema
    fields = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=64),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=EMBED_DIM),
        FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=4096),
        FieldSchema(name="source_name", dtype=DataType.VARCHAR, max_length=512),
        FieldSchema(name="source_url", dtype=DataType.VARCHAR, max_length=1024),
        FieldSchema(name="language", dtype=DataType.VARCHAR, max_length=32),
        FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=512),
        FieldSchema(name="chunk_index", dtype=DataType.INT64),
        FieldSchema(name="document_id", dtype=DataType.VARCHAR, max_length=128),
        FieldSchema(name="tenant_id", dtype=DataType.VARCHAR, max_length=64),
    ]
    return CollectionSchema(fields, description="代码规范文档切片")


def get_client() -> MilvusClient:
    """懒初始化 MilvusClient 单例，并确保 collection 存在。"""
    global _client, _initialized
    s = get_settings()
    if _client is None:
        uri = f"http://{s.milvus_host}:{s.milvus_port}"
        _client = MilvusClient(uri=uri)
        logger.info("rag.milvus_connected", uri=uri)
    if not _initialized:
        _ensure_collection(s.rag_collection)
        _initialized = True
    return _client


def _ensure_collection(name: str) -> None:
    """collection 不存在则创建（含 AUTOINDEX 向量索引）。"""
    if _client.has_collection(name):
        return
    index_params = _client.prepare_index_params()
    index_params.add_index(
        field_name="embedding",
        index_type="AUTOINDEX",
        metric_type="COSINE",
    )
    _client.create_collection(
        collection_name=name,
        schema=_schema(),
        index_params=index_params,
    )
    logger.info("rag.collection_created", name=name)


def generate_chunk_id(content: str, document_id: str, chunk_index: int) -> str:
    """内容+位置不变则 ID 不变，支持幂等 upsert。"""
    raw = f"{document_id}_{chunk_index}_{content[:50]}"
    return hashlib.md5(raw.encode()).hexdigest()


def upsert_chunks(chunks: list[dict]) -> int:
    """批量写入切片。chunk 需含 content/embedding/source_name/source_url/language/title/chunk_index/document_id。"""
    if not chunks:
        return 0
    s = get_settings()
    data = [
        {
            "id": c.get("id") or generate_chunk_id(c["content"], c["document_id"], c["chunk_index"]),
            "embedding": c["embedding"],
            "content": c["content"][:4096],
            "source_name": c.get("source_name", ""),
            "source_url": c.get("source_url", ""),
            "language": c.get("language", "python"),
            "title": c.get("title", ""),
            "chunk_index": c["chunk_index"],
            "document_id": c["document_id"],
            "tenant_id": c.get("tenant_id", s.default_tenant_id),
        }
        for c in chunks
    ]
    get_client().upsert(collection_name=s.rag_collection, data=data)
    logger.info("rag.chunks_upserted", count=len(data))
    return len(data)


def search(query_vector: list[float], tenant_id: str, top_k: int = 3) -> list[dict]:
    """Dense 检索，返回 top-K 切片（含内容与来源元数据）。失败时返回空列表不阻断评审。"""
    s = get_settings()
    try:
        results = get_client().search(
            collection_name=s.rag_collection,
            data=[query_vector],
            limit=top_k,
            output_fields=[
                "content", "source_name", "source_url", "language",
                "title", "chunk_index", "document_id",
            ],
            filter=f'tenant_id == "{tenant_id}"',
        )
    except Exception as e:
        logger.error("rag.search_failed", error=str(e))
        return []
    hits = []
    for hit in results[0]:
        entity = hit.get("entity", {})
        hits.append({
            "content": entity.get("content", ""),
            "score": hit.get("distance", 0.0),
            "source_name": entity.get("source_name", ""),
            "source_url": entity.get("source_url", ""),
            "language": entity.get("language", ""),
            "title": entity.get("title", ""),
        })
    logger.info("rag.search_done", hits=len(hits))
    return hits
