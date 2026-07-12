"""Milvus 向量库封装。

collection 设计：主键用 MySQL chunks.id（IDENTICAL 双向可查），
标量字段冗余 document_id / page 以支持向量侧过滤，文本本体以 MySQL 为准。
索引 HNSW + COSINE：bge-m3 归一化向量下 cosine 与内积等价，语义直观。
"""

import logging

from pymilvus import DataType, MilvusClient

from app.core.config import settings
from app.core.embeddings import EMBEDDING_DIM

logger = logging.getLogger(__name__)

COLLECTION = "kb_chunks"


def get_client() -> MilvusClient:
    return MilvusClient(uri=settings.milvus_uri)


def ensure_collection(client: MilvusClient | None = None) -> None:
    client = client or get_client()
    if client.has_collection(COLLECTION):
        return
    schema = client.create_schema(auto_id=False)
    schema.add_field("chunk_id", DataType.INT64, is_primary=True)
    schema.add_field("document_id", DataType.VARCHAR, max_length=36)
    schema.add_field("page_start", DataType.INT32)
    schema.add_field("page_end", DataType.INT32)
    schema.add_field("vector", DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM)

    index_params = client.prepare_index_params()
    index_params.add_index(
        "vector", index_type="HNSW", metric_type="COSINE", params={"M": 16, "efConstruction": 200}
    )
    client.create_collection(COLLECTION, schema=schema, index_params=index_params)
    logger.info("Milvus collection %s 已创建（dim=%d, HNSW/COSINE）", COLLECTION, EMBEDDING_DIM)


def insert_chunks(rows: list[dict], client: MilvusClient | None = None) -> None:
    """rows: [{chunk_id, document_id, page_start, page_end, vector}]"""
    client = client or get_client()
    client.insert(COLLECTION, rows)


def delete_document(document_id: str, client: MilvusClient | None = None) -> None:
    """按文档删除向量（重试幂等 / 文档删除时用）。"""
    client = client or get_client()
    if client.has_collection(COLLECTION):
        client.delete(COLLECTION, filter=f'document_id == "{document_id}"')


def search(vector: list[float], top_k: int = 20, client: MilvusClient | None = None) -> list[dict]:
    """向量召回，返回 [{chunk_id, distance, document_id, page_start, page_end}]（阶段 3 主用）。"""
    client = client or get_client()
    hits = client.search(
        COLLECTION,
        data=[vector],
        limit=top_k,
        output_fields=["document_id", "page_start", "page_end"],
        search_params={"metric_type": "COSINE", "params": {"ef": 128}},
    )[0]
    return [
        {
            "chunk_id": h["id"],
            "score": h["distance"],
            **h["entity"],
        }
        for h in hits
    ]
