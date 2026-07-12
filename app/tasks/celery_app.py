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
    # Redis broker 的崩溃重投不是即时的：未确认消息躺在 unacked 集合，
    # 靠 visibility_timeout 超时扫描才回队列（默认 1 小时，对分钟级任务太久）。
    # 设为 10 分钟：必须大于单任务最长执行时间，否则运行中的任务会被误判超时重复投递
    broker_transport_options={"visibility_timeout": 600},
    worker_prefetch_multiplier=1,  # 长任务逐个取，避免一个 worker 囤积队列
    task_track_started=True,
    result_expires=86400,
    timezone="Asia/Shanghai",
)
