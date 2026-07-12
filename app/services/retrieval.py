"""两阶段检索：向量召回（宽）→ rerank 精排（严）→ 阈值过滤。

为什么两阶段：召回阶段用 ANN 索引在几万级向量里快速取 top20，保召回率；
精排用交叉编码器对 20 条精细打分取 top5，保精度。直接用 reranker 扫全库
算不动，直接拿向量分数排序精度不够——两阶段是召回率/精度/延迟的平衡点。
"""

import logging
from dataclasses import dataclass

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.embeddings import embed_query
from app.core.rerank import rerank
from app.models.ingest import Chunk, Document
from app.services import vector_store

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    chunk_id: int
    content: str
    filename: str
    page_start: int
    page_end: int
    recall_score: float  # 向量召回的 cosine 相似度
    rerank_score: float  # 精排相关性得分（拒答阈值作用于此）


async def retrieve(
    query: str,
    db: AsyncSession,
    *,
    recall_top_k: int | None = None,
    final_top_k: int | None = None,
    use_rerank: bool = True,
) -> list[RetrievedChunk]:
    """默认参数走 settings；关键字参数供评测实验注入对照配置。

    use_rerank=False 时退化为纯向量检索：直接取召回分 top final_top_k，
    不做阈值过滤（cosine 分数跨查询同样不可比，阈值只对 rerank 分有意义）。
    """
    recall_k = recall_top_k or settings.recall_top_k
    final_k = final_top_k or settings.rerank_top_k

    # 1) 召回：查询向量化 + Milvus ANN（pymilvus 是同步客户端，丢线程池防阻塞事件循环）
    vector = await embed_query(query)
    hits = await run_in_threadpool(vector_store.search, vector, recall_k)
    if not hits:
        return []

    # 2) 回表：从 MySQL 取 chunk 正文与文件名
    chunk_ids = [h["chunk_id"] for h in hits]
    rows = (
        await db.execute(
            select(Chunk, Document.filename)
            .join(Document, Chunk.document_id == Document.id)
            .where(Chunk.id.in_(chunk_ids))
        )
    ).all()
    by_id = {c.id: (c, filename) for c, filename in rows}
    candidates = [(h, *by_id[h["chunk_id"]]) for h in hits if h["chunk_id"] in by_id]

    if not use_rerank:  # 对照实验：纯向量召回
        results = [
            _to_result(hit, chunk, filename, rerank_score=-1.0)
            for hit, chunk, filename in candidates[:final_k]
        ]
        logger.info("检索(纯向量) query=%.30s... 召回=%d 返回=%d", query, len(hits), len(results))
        return results

    # 3) 精排 + 阈值过滤
    ranked = await rerank(query, [c.content for _, c, _ in candidates], top_n=final_k)
    results = []
    for idx, score in ranked:
        if score < settings.rerank_score_threshold:
            continue
        hit, chunk, filename = candidates[idx]
        results.append(_to_result(hit, chunk, filename, rerank_score=score))
    logger.info(
        "检索 query=%.30s... 召回=%d 精排后=%d（阈值 %.2f）",
        query,
        len(hits),
        len(results),
        settings.rerank_score_threshold,
    )
    return results


def _to_result(hit: dict, chunk: Chunk, filename: str, rerank_score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk.id,
        content=chunk.content,
        filename=filename,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        recall_score=hit["score"],
        rerank_score=rerank_score,
    )
