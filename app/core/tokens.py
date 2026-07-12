"""token 计数。

DeepSeek 未公开 tokenizer，用 tiktoken cl100k_base 近似（中文约 1 字 ≈ 1 token，
实际略有偏差），因此裁剪预算要留余量，不能顶着模型上限用。
"""

from functools import lru_cache

import tiktoken


@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoding().encode(text))


def count_message_tokens(messages: list[dict]) -> int:
    # 每条消息按 OpenAI 的经验值附加 4 token 的角色/分隔开销
    return sum(count_tokens(m["content"]) + 4 for m in messages)
