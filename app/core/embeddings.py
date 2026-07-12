"""bge-m3 embedding 客户端（硅基流动 OpenAI 兼容接口）。

同步实现，供 Celery worker 批量调用。批大小 64 是硅基流动单请求上限内的
稳妥值；重试策略与 LLM 客户端一致（指数退避，只重试可恢复错误）。
"""

import logging
import time

import openai
from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1024  # bge-m3 稠密向量维度
_BATCH_SIZE = 64

RETRYABLE_ERRORS = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.InternalServerError,
)

_client = OpenAI(
    api_key=settings.embedding_api_key,
    base_url=settings.embedding_base_url,
    timeout=60.0,
    max_retries=0,
)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量向量化，保持与输入同序。"""
    vectors: list[list[float]] = []
    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i : i + _BATCH_SIZE]
        # bge-m3 单条上限 8192 token，超长截断以免整批报错（chunk 正常不会触发）
        batch = [t[:6000] for t in batch]
        resp = _call_with_retry(batch)
        vectors.extend([d.embedding for d in resp.data])
    return vectors


def _call_with_retry(batch: list[str]):
    attempt = 0
    while True:
        try:
            return _client.embeddings.create(model=settings.embedding_model, input=batch)
        except RETRYABLE_ERRORS as e:
            attempt += 1
            if attempt > 3:
                raise
            delay = 0.5 * (2 ** (attempt - 1))
            logger.warning("embedding 调用失败，%.1fs 后第 %d 次重试: %s", delay, attempt, e)
            time.sleep(delay)
