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
import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base

# 数据库文件放在 backend/data/ 下（已在 .gitignore 里，不会进版本库）
DATA_DIR = Path(os.environ.get("WUJI_DATA_DIR") or (Path(__file__).resolve().parents[2] / "data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
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


# 已有表新增的列。create_all 只会建缺失的**表**，不会给现有表补**列**——
# 老数据库启动后会直接报 "no such column"，而且是在玩家读档时才炸。
# 正式项目该用 Alembic；在那之前，至少要有这么一张明确的补列清单，
# 而不是让开发者自己记得删库重建。
_ADDED_COLUMNS: list[tuple[str, str, str]] = [
    # (表名, 列名, SQLite 列定义)
    ("saves", "schema_version", "INTEGER NOT NULL DEFAULT 1"),
    ("saves", "revision", "INTEGER NOT NULL DEFAULT 0"),
    ("npc_beliefs", "updated_turn", "INTEGER NOT NULL DEFAULT 0"),
]


def _add_missing_columns(conn) -> None:
    from sqlalchemy import text

    for table, column, ddl in _ADDED_COLUMNS:
        exists = conn.execute(
            text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
        ).first()
        if not exists:
            continue  # 表还没建，create_all 会带上这一列
        cols = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
        if column not in cols:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))

    # 旧 belief 只有 learned_turn。新增列后的 0 不是“第 0 回合更新”，而是
    # 尚未迁移；回填后才能可靠拒绝晚到的陈旧抽取结果。
    belief_table = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='npc_beliefs'")
    ).first()
    if belief_table:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(npc_beliefs)"))}
        if "updated_turn" in cols:
            conn.execute(text(
                "UPDATE npc_beliefs SET updated_turn = learned_turn "
                "WHERE updated_turn = 0 AND learned_turn > 0"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_belief_session_turn "
                "ON npc_beliefs (session_id, updated_turn)"
            ))


async def init_db() -> None:
    """
    建表并补齐缺失的列。应用启动时调用一次，可安全重复执行。
    """
    async with engine.begin() as conn:
        await conn.run_sync(_add_missing_columns)
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：每个请求一个数据库会话。"""
    async with SessionLocal() as session:
        yield session
