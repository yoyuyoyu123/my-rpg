"""
数据层 · 连接管理
=================
职责：创建数据库引擎、提供会话（Session）、建表。

用异步引擎的原因：
    FastAPI 是异步框架。如果这里用同步驱动，每次查库都会堵住整个事件循环，
    并发时其它请求只能干等。aiosqlite 让数据库 I/O 也是异步的。

依赖注入的用法（在路由里）：
    async def endpoint(db: AsyncSession = Depends(get_db)):
        ...
    FastAPI 会自动开启会话、请求结束后关闭，不用手写 try/finally。
"""
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base

# 数据库文件放在 backend/data/ 下（已在 .gitignore 里，不会进版本库）
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "wuji.db"

DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,          # 想看 SQL 就改成 True，调试时很有用
    future=True,
)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # commit 后对象仍可读，省去重新查询
)


async def init_db() -> None:
    """
    建表。应用启动时调用一次。

    真实项目通常用 Alembic 做迁移（能处理「表已存在但结构变了」的情况），
    现阶段表结构还在演进，先用 create_all 快速迭代。
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：每个请求一个数据库会话。"""
    async with SessionLocal() as session:
        yield session
