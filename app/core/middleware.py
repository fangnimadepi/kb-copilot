"""请求日志中间件 + 统一异常响应。

错误响应统一为 {"code": <机器可读>, "message": <人类可读>}——
这是从 Chatchat 学到的反面教训：它的异常直接崩成非 JSON，前端只能静默失败。
"""

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.services.chat_service import ConversationNotFound

logger = logging.getLogger("app.request")


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_logging(request: Request, call_next):
        request_id = uuid.uuid4().hex[:8]
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "[%s] %s %s -> %d (%.0fms)",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(ConversationNotFound)
    async def conversation_not_found(_: Request, exc: ConversationNotFound):
        return JSONResponse(
            status_code=404,
            content={"code": "conversation_not_found", "message": str(exc)},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"code": "validation_error", "message": str(exc.errors()[:3])},
        )

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception):
        logger.exception("未处理异常 %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"code": "internal_error", "message": "服务内部错误"},
        )
