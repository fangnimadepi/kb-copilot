import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.db import get_db
from app.core.llm import stream_chat
from app.models.chat import Message
from app.services import chat_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    conversation_id: str | None = None  # 不传则新建会话
    message: str = Field(min_length=1, max_length=8000)


@router.post("/chat")
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)) -> EventSourceResponse:
    """SSE 流式对话。

    事件协议：
      event: meta   -> {"conversation_id": ...}   开流即发，客户端拿到会话 id
      event: delta  -> {"content": "增量文本"}
      event: done   -> {"total_tokens": ...}
      event: error  -> {"code": ..., "message": ...}   流中失败时发出，随后关流
    """
    conv = await chat_service.get_or_create_conversation(db, req.conversation_id)
    await chat_service.save_message(db, conv.id, "user", req.message)
    llm_messages = await chat_service.build_llm_messages(db, conv.id)

    async def event_stream() -> AsyncIterator[dict]:
        yield {"event": "meta", "data": json.dumps({"conversation_id": conv.id})}
        answer_parts: list[str] = []
        try:
            async for delta in stream_chat(llm_messages):
                answer_parts.append(delta)
                yield {"event": "delta", "data": json.dumps({"content": delta}, ensure_ascii=False)}
        except Exception:
            logger.exception("流式生成失败 conversation=%s", conv.id)
            yield {
                "event": "error",
                "data": json.dumps(
                    {"code": "llm_stream_error", "message": "生成中断，请重试"},
                    ensure_ascii=False,
                ),
            }
            return
        answer = "".join(answer_parts)
        # 空回答不入库；正常回答落库后才发 done，保证客户端收到 done 时历史已一致
        if answer:
            msg = await chat_service.save_message(db, conv.id, "assistant", answer)
            yield {
                "event": "done",
                "data": json.dumps({"message_id": msg.id, "total_tokens": msg.token_count}),
            }

    return EventSourceResponse(event_stream())


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    conv = await chat_service.get_or_create_conversation(db, conversation_id)
    rows = (
        (
            await db.execute(
                select(Message)
                .where(Message.conversation_id == conv.id)
                .order_by(Message.created_at, Message.id)
            )
        )
        .scalars()
        .all()
    )
    return {
        "conversation_id": conv.id,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "token_count": m.token_count,
                "created_at": m.created_at.isoformat(),
            }
            for m in rows
        ],
    }
