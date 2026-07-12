from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "kb_copilot",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.ingest"],
)

celery_app.conf.update(
    # 迟确认 + worker 崩溃重投：worker 被杀后任务回到队列，重启即恢复——
    # 这是"任务可恢复"验收项的机制保障；代价是任务必须幂等（入库前先清旧数据）
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # 长任务逐个取，避免一个 worker 囤积队列
    task_track_started=True,
    result_expires=86400,
    timezone="Asia/Shanghai",
)
