"""LLM 客户端封装：流式调用 + 超时 + 指数退避重试。

重试边界的设计：只在拿到首个数据块**之前**重试。流一旦开始，
部分内容可能已经推送给了前端，中途失败无法安全回滚，只能向上抛错，
由 API 层通过 SSE error 事件告知客户端。
"""

import asyncio
import logging
from collections.abc import AsyncIterator

import openai
from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

# 连接失败 / 超时 / 限流 / 服务端 5xx 才值得重试；4xx（如参数错误、鉴权失败）重试无意义
RETRYABLE_ERRORS = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.InternalServerError,
)

_client = AsyncOpenAI(
    api_key=settings.deepseek_api_key,
    base_url=settings.deepseek_base_url,
    timeout=settings.llm_timeout,
    max_retries=0,  # SDK 自带重试关掉，退避策略自己控制，便于打日志和调参
)


async def stream_chat(
    messages: list[dict],
    *,
    temperature: float = 0.7,
) -> AsyncIterator[str]:
    """流式对话，逐段产出内容增量（delta）。"""
    attempt = 0
    while True:
        try:
            stream = await _client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                temperature=temperature,
                stream=True,
            )
            break
        except RETRYABLE_ERRORS as e:
            attempt += 1
            if attempt > settings.llm_max_retries:
                logger.error("LLM 调用重试 %d 次后仍失败: %s", settings.llm_max_retries, e)
                raise
            delay = settings.llm_retry_base_delay * (2 ** (attempt - 1))
            logger.warning("LLM 调用失败，%.1fs 后第 %d 次重试: %s", delay, attempt, e)
            await asyncio.sleep(delay)

    async for chunk in stream:
        if chunk.choices and (delta := chunk.choices[0].delta.content):
            yield delta
