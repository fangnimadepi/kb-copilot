"""bge-reranker 重排客户端（硅基流动 /rerank 接口）。

rerank 模型与 embedding 模型的本质区别：embedding 是双塔（query/doc 各自
编码成向量，离线可算，配合 ANN 索引做大规模召回）；reranker 是交叉编码器
（query 和 doc 拼在一起过模型，精度高但只能在线逐对算），所以只能用在
召回后的小候选集上——这就是"两阶段"的由来。
"""

import httpx

from app.core.config import settings

_client = httpx.AsyncClient(
    base_url=settings.embedding_base_url,
    headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
    timeout=30.0,
)


async def rerank(query: str, documents: list[str], top_n: int) -> list[tuple[int, float]]:
    """返回 [(原候选下标, 相关性得分)]，按得分降序，取前 top_n。"""
    resp = await _client.post(
        "/rerank",
        json={
            "model": settings.rerank_model,
            "query": query,
            "documents": documents,
            "top_n": top_n,
            "return_documents": False,
        },
    )
    resp.raise_for_status()
    results = resp.json()["results"]
    return [(r["index"], r["relevance_score"]) for r in results]
