import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.tokens import count_tokens
from app.models.chat import Conversation, Message
from app.services.context import trim_messages

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = "你是 KB-Copilot，一个严谨的企业知识库问答助手。回答简洁、准确。"


async def get_or_create_conversation(db: AsyncSession, conversation_id: str | None) -> Conversation:
    if conversation_id:
        conv = await db.get(Conversation, conversation_id)
        if conv is None:
            raise ConversationNotFound(conversation_id)
        return conv
    conv = Conversation()
    db.add(conv)
    await db.commit()
    return conv


async def save_message(db: AsyncSession, conversation_id: str, role: str, content: str) -> Message:
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        token_count=count_tokens(content),
    )
    db.add(msg)
    await db.commit()
    return msg


async def build_llm_messages(db: AsyncSession, conversation_id: str) -> list[dict]:
    """取全量历史 → 组装 → 按 token 预算裁剪。

    历史长度上限由 token 预算控制而非条数，所以这里先取回全部再裁剪；
    等会话可能变得极长时，可以改为 LIMIT 最近 N 条再裁剪（N 取预算的宽松上界）。
    """
    rows = (
        (
            await db.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at, Message.id)
            )
        )
        .scalars()
        .all()
    )

    history = [{"role": m.role, "content": m.content, "token_count": m.token_count} for m in rows]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
    trimmed = trim_messages(messages, budget=settings.context_token_budget)
    if len(trimmed) < len(messages):
        logger.info(
            "上下文裁剪：%d 条 -> %d 条（预算 %d token）",
            len(messages),
            len(trimmed),
            settings.context_token_budget,
        )
    # 传给 LLM 前去掉内部字段
    return [{"role": m["role"], "content": m["content"]} for m in trimmed]


class ConversationNotFound(Exception):
    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id
        super().__init__(f"会话不存在: {conversation_id}")
