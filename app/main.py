import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.chat import router as chat_router
from app.core import middleware
from app.core.config import settings
from app.core.db import engine
from app.models.chat import Base

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 阶段 1 先用 create_all 建表；引入正式迁移（Alembic）计划在阶段 5
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="KB-Copilot", version="0.1.0", lifespan=lifespan)
middleware.install(app)
app.include_router(chat_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": settings.app_name}
