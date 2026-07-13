import hashlib
import re
from email.header import decode_header, make_header
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db
from app.models.ingest import Document, IngestTask, TaskStatus
from app.tasks.ingest import ingest_document

router = APIRouter(prefix="/api", tags=["documents"])

_RUNNING = (TaskStatus.pending, TaskStatus.parsing, TaskStatus.embedding)


def _safe_filename(raw: str) -> str:
    """客户端文件名不可信：可能是 RFC 2047 编码（PowerShell 等客户端对非 ASCII
    文件名会这样编码）、可能带路径、可能含 Windows 非法字符。统一解码 + 清洗。"""
    try:
        name = str(make_header(decode_header(raw)))
    except Exception:
        name = raw
    name = Path(name).name  # 去路径分量，防目录穿越
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip()
    return name or "unnamed"


@router.post("/documents", status_code=202)
async def upload_documents(
    files: list[UploadFile] = File(...),
    chunk_strategy: str = Form("fixed"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """上传文档并创建异步入库任务，立即返回 task_id（不同步处理）。

    同内容文件（sha256 相同）直接复用已有 Document，重新入库视为重建。
    """
    if chunk_strategy not in ("fixed", "structured"):
        raise HTTPException(422, detail="chunk_strategy 只支持 fixed / structured")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for file in files:
        content = await file.read()
        sha256 = hashlib.sha256(content).hexdigest()
        filename = _safe_filename(file.filename or "unnamed")

        doc = (
            await db.execute(select(Document).where(Document.file_sha256 == sha256))
        ).scalar_one_or_none()
        if doc is None:
            dest = upload_dir / f"{sha256[:16]}_{filename}"
            dest.write_bytes(content)
            doc = Document(
                filename=filename,
                file_path=str(dest),
                file_sha256=sha256,
                file_size=len(content),
            )
            db.add(doc)
            await db.flush()

        task = IngestTask(document_id=doc.id, chunk_strategy=chunk_strategy)
        db.add(task)
        await db.commit()
        ingest_document.delay(task.id)
        results.append({"document_id": doc.id, "task_id": task.id, "filename": filename})
    return {"tasks": results}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    task = await db.get(IngestTask, task_id)
    if task is None:
        raise HTTPException(404, detail="任务不存在")
    return {
        "task_id": task.id,
        "document_id": task.document_id,
        "status": task.status,
        "progress": task.progress,
        "error": task.error,
        "retry_count": task.retry_count,
        "chunk_strategy": task.chunk_strategy,
        "updated_at": task.updated_at.isoformat(),
    }


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    task = await db.get(IngestTask, task_id)
    if task is None:
        raise HTTPException(404, detail="任务不存在")
    if task.status not in _RUNNING:
        raise HTTPException(409, detail=f"当前状态 {task.status} 不可取消")
    task.status = TaskStatus.canceled
    await db.commit()
    return {"task_id": task.id, "status": task.status}


@router.post("/tasks/{task_id}/retry")
async def retry_task(task_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    task = await db.get(IngestTask, task_id)
    if task is None:
        raise HTTPException(404, detail="任务不存在")
    if task.status not in (TaskStatus.failed, TaskStatus.canceled):
        raise HTTPException(409, detail=f"当前状态 {task.status} 不可重试")
    task.status = TaskStatus.pending
    task.progress = 0
    task.error = None
    task.retry_count += 1
    await db.commit()
    ingest_document.delay(task.id)
    return {"task_id": task.id, "status": task.status, "retry_count": task.retry_count}


@router.get("/documents/{document_id}/file")
async def download_document(document_id: str, db: AsyncSession = Depends(get_db)) -> FileResponse:
    """下载原始文档——供演示时核对引用真实性（回答页码 vs 原文）。"""
    doc = await db.get(Document, document_id)
    if doc is None or not Path(doc.file_path).is_file():
        raise HTTPException(404, detail="文档不存在")
    return FileResponse(doc.file_path, filename=doc.filename, media_type="application/pdf")


@router.get("/documents")
async def list_documents(db: AsyncSession = Depends(get_db)) -> dict:
    docs = (await db.execute(select(Document).order_by(Document.created_at.desc()))).scalars().all()
    return {
        "documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "file_size": d.file_size,
                "chunk_count": d.chunk_count,
                "created_at": d.created_at.isoformat(),
            }
            for d in docs
        ]
    }
