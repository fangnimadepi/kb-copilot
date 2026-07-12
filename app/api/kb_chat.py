import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.db import get_db
from app.core.llm import stream_chat
from app.services import chat_service
from app.services.retrieval import RetrievedChunk, retrieve

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["kb-chat"])

REFUSAL = "知识库中未找到与该问题相关的内容，无法回答。"

RAG_PROMPT = """请严格根据以下知识库检索内容回答用户问题。

规则：
1. 只使用检索内容中的信息，不要编造或使用你自己的知识补充事实
2. 引用某段内容支撑结论时，在句末标注对应编号，如 [1]、[2]，可多个
3. 如果检索内容不足以回答问题，直接回答"知识库中未找到相关信息"，不要猜测
4. 涉及数字（金额、比例）时必须与原文一致

--- 检索内容 ---
{context}
--- 检索内容结束 ---

用户问题：{question}"""


class KbChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=8000)


def _build_context(chunks: list[RetrievedChunk]) -> str:
    blocks = []
    for i, c in enumerate(chunks, start=1):
        loc = (
            f"第{c.page_start}页"
            if c.page_start == c.page_end
            else f"第{c.page_start}-{c.page_end}页"
        )
        blocks.append(f"[{i}]（{c.filename} {loc}）\n{c.content}")
    return "\n\n".join(blocks)


def _refs_payload(chunks: list[RetrievedChunk]) -> list[dict]:
    return [
        {
            "ref": i,
            "filename": c.filename,
            "page_start": c.page_start,
            "page_end": c.page_end,
            "rerank_score": round(c.rerank_score, 4),
            "recall_score": round(c.recall_score, 4),
        }
        for i, c in enumerate(chunks, start=1)
    ]


@router.post("/kb_chat")
async def kb_chat(req: KbChatRequest, db: AsyncSession = Depends(get_db)) -> EventSourceResponse:
    """知识库问答（两阶段检索 + 引用溯源）。

    SSE 事件：meta -> refs（引用来源，含页码与分数）-> delta* -> done
    拒答：精排后无合格 chunk 时不调 LLM，直接回复拒答话术（refs 为空数组）。
    """
    conv = await chat_service.get_or_create_conversation(db, req.conversation_id)
    await chat_service.save_message(db, conv.id, "user", req.message)

    chunks = await retrieve(req.message, db)

    async def event_stream() -> AsyncIterator[dict]:
        yield {"event": "meta", "data": json.dumps({"conversation_id": conv.id})}
        yield {
            "event": "refs",
            "data": json.dumps(_refs_payload(chunks), ensure_ascii=False),
        }

        if not chunks:  # 拒答兜底：宁可不答，不可瞎编
            msg = await chat_service.save_message(db, conv.id, "assistant", REFUSAL)
            yield {"event": "delta", "data": json.dumps({"content": REFUSAL}, ensure_ascii=False)}
            yield {"event": "done", "data": json.dumps({"message_id": msg.id, "refused": True})}
            return

        history = await chat_service.build_llm_messages(db, conv.id)
        # 当前轮的用户消息替换为 RAG 模板（历史里保留的是原始问题）
        history[-1] = {
            "role": "user",
            "content": RAG_PROMPT.format(context=_build_context(chunks), question=req.message),
        }

        answer_parts: list[str] = []
        try:
            async for delta in stream_chat(history, temperature=0.3):
                answer_parts.append(delta)
                yield {"event": "delta", "data": json.dumps({"content": delta}, ensure_ascii=False)}
        except Exception:
            logger.exception("RAG 流式生成失败 conversation=%s", conv.id)
            yield {
                "event": "error",
                "data": json.dumps(
                    {"code": "llm_stream_error", "message": "生成中断，请重试"}, ensure_ascii=False
                ),
            }
            return

        answer = "".join(answer_parts)
        if answer:
            msg = await chat_service.save_message(db, conv.id, "assistant", answer)
            yield {
                "event": "done",
                "data": json.dumps({"message_id": msg.id, "refused": False}),
            }

    return EventSourceResponse(event_stream())
