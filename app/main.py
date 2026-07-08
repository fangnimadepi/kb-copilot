from fastapi import FastAPI

from app.core.config import settings

app = FastAPI(title="KB-Copilot", version="0.1.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": settings.app_name}
