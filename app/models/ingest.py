import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.chat import Base


class TaskStatus(str, enum.Enum):
    """任务状态机。合法迁移：

    pending -> parsing -> embedding -> done
        任意运行态 -> failed（记录 error）
        pending/parsing/embedding -> canceled（用户取消）
    failed/canceled -> pending（重试，需清理旧数据保证幂等）
    """

    pending = "pending"
    parsing = "parsing"
    embedding = "embedding"
    done = "done"
    failed = "failed"
    canceled = "canceled"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(512))  # 落盘位置（上传目录内）
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)  # 去重/幂等依据
    file_size: Mapped[int] = mapped_column(BigInteger)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class IngestTask(Base):
    __tablename__ = "ingest_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, native_enum=False, length=16), default=TaskStatus.pending, index=True
    )
    chunk_strategy: Mapped[str] = mapped_column(String(32), default="fixed")  # fixed / structured
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0~100，embedding 阶段按批推进
    error: Mapped[str | None] = mapped_column(Text, default=None)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Chunk(Base):
    """chunk 元数据（MySQL 为准），向量本体在 Milvus。页码支撑引用溯源。"""

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    page_start: Mapped[int] = mapped_column(Integer, default=0)  # 起始页码（1 起；md/docx 为 0）
    page_end: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
