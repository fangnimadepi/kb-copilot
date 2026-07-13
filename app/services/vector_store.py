"""向量库封装：Milvus / Qdrant 双后端，按 VECTOR_BACKEND 配置切换。

抽象动机（真实业务约束）：本地开发用 Milvus standalone（JD 高频、功能全），
但演示服务器只有 1C/1G——Milvus 空载即超内存，Qdrant 只要约 150MB。
参照 Chatchat 的 KBService 工厂模式，把差异收敛在本模块内，
调用方（ingest/retrieval）只依赖模块级函数，切换后端零改动。

统一契约：
  ensure_collection()                 建集合/索引（幂等）
  insert_chunks(rows)                 rows: [{chunk_id, document_id, page_start, page_end, vector}]
  delete_document(document_id)        按文档删向量（幂等重试/删除文档用）
  search(vector, top_k) -> [{chunk_id, score, document_id, page_start, page_end}]
  score 统一为 cosine 相似度（越大越相关）。
"""

import logging
from abc import ABC, abstractmethod
from functools import lru_cache

from app.core.config import settings
from app.core.embeddings import EMBEDDING_DIM

logger = logging.getLogger(__name__)

COLLECTION = "kb_chunks"


class VectorStore(ABC):
    @abstractmethod
    def ensure_collection(self) -> None: ...

    @abstractmethod
    def insert_chunks(self, rows: list[dict]) -> None: ...

    @abstractmethod
    def delete_document(self, document_id: str) -> None: ...

    @abstractmethod
    def search(self, vector: list[float], top_k: int) -> list[dict]: ...


class MilvusStore(VectorStore):
    def __init__(self) -> None:
        from pymilvus import MilvusClient

        self.client = MilvusClient(uri=settings.milvus_uri)

    def ensure_collection(self) -> None:
        from pymilvus import DataType

        if self.client.has_collection(COLLECTION):
            return
        schema = self.client.create_schema(auto_id=False)
        schema.add_field("chunk_id", DataType.INT64, is_primary=True)
        schema.add_field("document_id", DataType.VARCHAR, max_length=36)
        schema.add_field("page_start", DataType.INT32)
        schema.add_field("page_end", DataType.INT32)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM)
        index_params = self.client.prepare_index_params()
        index_params.add_index(
            "vector",
            index_type="HNSW",
            metric_type="COSINE",
            params={"M": 16, "efConstruction": 200},
        )
        self.client.create_collection(COLLECTION, schema=schema, index_params=index_params)
        logger.info("Milvus collection %s 已创建（dim=%d, HNSW/COSINE）", COLLECTION, EMBEDDING_DIM)

    def insert_chunks(self, rows: list[dict]) -> None:
        self.client.insert(COLLECTION, rows)

    def delete_document(self, document_id: str) -> None:
        if self.client.has_collection(COLLECTION):
            self.client.delete(COLLECTION, filter=f'document_id == "{document_id}"')

    def search(self, vector: list[float], top_k: int) -> list[dict]:
        hits = self.client.search(
            COLLECTION,
            data=[vector],
            limit=top_k,
            output_fields=["document_id", "page_start", "page_end"],
            search_params={"metric_type": "COSINE", "params": {"ef": 128}},
        )[0]
        return [{"chunk_id": h["id"], "score": h["distance"], **h["entity"]} for h in hits]


class QdrantStore(VectorStore):
    def __init__(self) -> None:
        from qdrant_client import QdrantClient

        self.client = QdrantClient(url=settings.qdrant_url)

    def ensure_collection(self) -> None:
        from qdrant_client import models

        if self.client.collection_exists(COLLECTION):
            return
        self.client.create_collection(
            COLLECTION,
            vectors_config=models.VectorParams(size=EMBEDDING_DIM, distance=models.Distance.COSINE),
        )
        # 按文档删除/过滤要走 payload 索引
        self.client.create_payload_index(
            COLLECTION, "document_id", field_schema=models.PayloadSchemaType.KEYWORD
        )
        logger.info("Qdrant collection %s 已创建（dim=%d, COSINE）", COLLECTION, EMBEDDING_DIM)

    def insert_chunks(self, rows: list[dict]) -> None:
        from qdrant_client import models

        self.client.upsert(
            COLLECTION,
            points=[
                models.PointStruct(
                    id=r["chunk_id"],
                    vector=r["vector"],
                    payload={
                        "document_id": r["document_id"],
                        "page_start": r["page_start"],
                        "page_end": r["page_end"],
                    },
                )
                for r in rows
            ],
        )

    def delete_document(self, document_id: str) -> None:
        from qdrant_client import models

        if self.client.collection_exists(COLLECTION):
            self.client.delete(
                COLLECTION,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="document_id", match=models.MatchValue(value=document_id)
                            )
                        ]
                    )
                ),
            )

    def search(self, vector: list[float], top_k: int) -> list[dict]:
        hits = self.client.query_points(COLLECTION, query=vector, limit=top_k).points
        return [
            {
                "chunk_id": h.id,
                "score": h.score,
                "document_id": h.payload["document_id"],
                "page_start": h.payload["page_start"],
                "page_end": h.payload["page_end"],
            }
            for h in hits
        ]


@lru_cache(maxsize=1)
def _store() -> VectorStore:
    backend = settings.vector_backend.lower()
    if backend == "milvus":
        return MilvusStore()
    if backend == "qdrant":
        return QdrantStore()
    raise ValueError(f"未知向量库后端: {backend}（可选 milvus / qdrant）")


# ---- 模块级函数：对调用方保持原有 API 不变 ----


def ensure_collection() -> None:
    _store().ensure_collection()


def insert_chunks(rows: list[dict]) -> None:
    _store().insert_chunks(rows)


def delete_document(document_id: str) -> None:
    _store().delete_document(document_id)


def search(vector: list[float], top_k: int = 20) -> list[dict]:
    return _store().search(vector, top_k)
