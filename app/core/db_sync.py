"""同步 SQLAlchemy 会话，仅供 Celery worker 使用。

worker 是同步执行模型（Windows 开发用 solo pool），在里面跑 asyncio 事件循环
反而增加复杂度，所以 worker 侧直接用同步 driver（pymysql）。
API 进程继续用 async（aiomysql），两者共享同一套 ORM 模型。
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.mysql_dsn.replace("mysql+aiomysql://", "mysql+pymysql://"),
    pool_pre_ping=True,
    pool_recycle=3600,
)

SyncSessionLocal = sessionmaker(engine, expire_on_commit=False)
