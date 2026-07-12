"""文档入库任务：parsing -> embedding -> done/failed，支持取消与幂等重试。

幂等设计：任务开头先删除该文档已有的 chunks（MySQL）与向量（Milvus），
所以同一任务被重复投递/重试时结果一致——这是 acks_late 崩溃重投的前提。

取消语义：协作式。embedding 每批之间回查一次任务状态，收到 canceled 就
停止并保持已写入的部分被清理（下次重试会重头来）。
"""

import logging

from sqlalchemy import delete, select

from app.core.db_sync import SyncSessionLocal
from app.core.embeddings import embed_texts
from app.models.ingest import Chunk, Document, IngestTask, TaskStatus
from app.services import vector_store
from app.services.chunking import split_units
from app.services.parsing import parse_file
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

_EMBED_BATCH = 32


@celery_app.task(name="ingest.document", bind=True)
def ingest_document(self, task_id: str) -> str:
    with SyncSessionLocal() as db:
        task = db.get(IngestTask, task_id)
        if task is None:
            logger.error("任务不存在: %s", task_id)
            return "missing"
        if task.status == TaskStatus.canceled:
            return "canceled"
        doc = db.get(Document, task.document_id)

        try:
            # ---- 幂等清理：旧 chunk + 旧向量 ----
            db.execute(delete(Chunk).where(Chunk.document_id == doc.id))
            db.commit()
            vector_store.delete_document(doc.id)

            # ---- parsing ----
            _set(db, task, TaskStatus.parsing, progress=5)
            units = parse_file(doc.file_path)
            drafts = split_units(units, strategy=task.chunk_strategy)
            if not drafts:
                raise ValueError("解析结果为空：文件无可提取文本")

            chunks = [
                Chunk(
                    document_id=doc.id,
                    chunk_index=i,
                    page_start=d.page_start,
                    page_end=d.page_end,
                    content=d.content,
                    token_count=d.token_count,
                )
                for i, d in enumerate(drafts)
            ]
            db.add_all(chunks)
            db.commit()

            # ---- embedding（分批，批间可取消、报进度） ----
            _set(db, task, TaskStatus.embedding, progress=10)
            vector_store.ensure_collection()
            rows = (
                db.execute(
                    select(Chunk).where(Chunk.document_id == doc.id).order_by(Chunk.chunk_index)
                )
                .scalars()
                .all()
            )
            for start in range(0, len(rows), _EMBED_BATCH):
                if _is_canceled(db, task_id):
                    _cleanup(db, doc.id)
                    return "canceled"
                batch = rows[start : start + _EMBED_BATCH]
                vectors = embed_texts([c.content for c in batch])
                vector_store.insert_chunks(
                    [
                        {
                            "chunk_id": c.id,
                            "document_id": c.document_id,
                            "page_start": c.page_start,
                            "page_end": c.page_end,
                            "vector": v,
                        }
                        for c, v in zip(batch, vectors)
                    ]
                )
                done = min(start + _EMBED_BATCH, len(rows))
                _set(db, task, TaskStatus.embedding, progress=10 + int(88 * done / len(rows)))

            # ---- done ----
            doc.chunk_count = len(rows)
            _set(db, task, TaskStatus.done, progress=100)
            logger.info(
                "入库完成 doc=%s chunks=%d strategy=%s",
                doc.filename,
                len(rows),
                task.chunk_strategy,
            )
            return "done"

        except Exception as e:
            logger.exception("入库失败 task=%s doc=%s", task_id, doc.filename if doc else "?")
            _set(db, task, TaskStatus.failed, error=f"{type(e).__name__}: {e}")
            return "failed"


def _set(
    db, task: IngestTask, status: TaskStatus, progress: int | None = None, error: str | None = None
) -> None:
    task.status = status
    if progress is not None:
        task.progress = progress
    task.error = error
    db.commit()


def _is_canceled(db, task_id: str) -> bool:
    db.expire_all()  # 取消由 API 进程写入，必须绕过本会话缓存重新读
    task = db.get(IngestTask, task_id)
    return task is not None and task.status == TaskStatus.canceled


def _cleanup(db, document_id: str) -> None:
    db.execute(delete(Chunk).where(Chunk.document_id == document_id))
    db.commit()
    vector_store.delete_document(document_id)
