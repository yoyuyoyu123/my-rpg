"""回合记忆写入的事务边界回归测试。"""
import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Base, Fact, Session  # noqa: E402
from app.routers import memory as memory_router  # noqa: E402


@pytest.mark.asyncio
async def test_extracted_memory_is_atomic_when_ledger_write_fails(monkeypatch) -> None:
    """
    一次抽取产生的事实和叙事账本属于同一个回合提交。

    如果写事件/承诺时失败，前面的事实也必须回滚；否则玩家看到的是失败回合，
    数据库却会把它当正史注入下一回合。
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    sid = "atomic-memory-test"
    async with maker() as db:
        db.add(Session(id=sid, title="t", world_id="fantasy"))
        await db.commit()

        async def fail_ledger(*_args, **_kwargs):
            raise RuntimeError("simulated ledger failure")

        monkeypatch.setattr(memory_router, "write_ledger", fail_ledger)
        bundle = {
            "entities": [{
                "name": "王掌柜",
                "kind": "person",
                "aliases": [],
                "importance": 2,
                "facts": [{"key": "职业", "value": "茶馆掌柜"}],
            }],
            "events": [{
                "kind": "scene",
                "actor": "王掌柜",
                "action": "答应替玩家打听消息",
                "outcome": "约定明早再见",
            }],
        }

        with pytest.raises(RuntimeError, match="simulated ledger failure"):
            await memory_router._store_extracted(sid, 4, bundle, db)
        await db.rollback()

    # 用一个全新会话读取，确保检查的是数据库已提交状态，不是 identity map。
    async with maker() as probe:
        fact_count = await probe.scalar(select(func.count(Fact.id)))

    await engine.dispose()
    assert fact_count == 0, "账本失败后不应留下半个回合的事实"
