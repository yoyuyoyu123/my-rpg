"""
事实库测试
==========
这些行为是「上下文一致性」的核心保证，必须锁死。
"""
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Base, Session  # noqa: E402
from app.domain.ontology import EntityKind, Stability, attr_menu, stability_of  # noqa: E402
from app.services.memory import (  # noqa: E402
    record_fact, resolve_entity, retrieve_context, upsert_entity,
)

SID = "test-session"


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    """每个测试一个全新的内存数据库，互不干扰。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        s.add(Session(id=SID, title="t", world_id="wuxia"))
        await s.commit()
        yield s
    await engine.dispose()


# ── 本体设计 ────────────────────────────────────────────────────

def test_stability_classification() -> None:
    """出身不该变，居所可以变——这是矛盾检测的基础。"""
    assert stability_of(EntityKind.PERSON, "出身") is Stability.STABLE
    assert stability_of(EntityKind.PERSON, "居所") is Stability.MUTABLE
    assert stability_of(EntityKind.PLACE, "位置") is Stability.STABLE
    assert stability_of(EntityKind.FACTION, "领袖") is Stability.MUTABLE


def test_unknown_attr_defaults_mutable() -> None:
    """词表外的属性当可变——宁可漏报，不可误拦叙事。"""
    assert stability_of(EntityKind.PERSON, "某个没预料到的属性") is Stability.MUTABLE


def test_attr_menu_is_usable_in_prompt() -> None:
    menu = attr_menu(EntityKind.PERSON)
    assert "职业" in menu and "出身" in menu


# ── 实体解析 ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_alias_resolves_to_same_entity(db: AsyncSession) -> None:
    """AI 换个称呼不该变成新角色——这是「同一个人」的技术实现。"""
    e = await upsert_entity(db, SID, name="吴四娘", kind="person", turn=1,
                            aliases=["吴婶", "隔壁洗衣的"])
    await db.commit()
    for alias in ["吴四娘", "吴婶", "隔壁洗衣的"]:
        found = await resolve_entity(db, SID, alias)
        assert found is not None and found.id == e.id, f"{alias} 没解析到同一实体"


@pytest.mark.asyncio
async def test_upsert_is_idempotent(db: AsyncSession) -> None:
    a = await upsert_entity(db, SID, name="陈铁匠", kind="person", turn=1)
    b = await upsert_entity(db, SID, name="陈铁匠", kind="person", turn=5)
    await db.commit()
    assert a.id == b.id
    assert b.last_seen_turn == 5, "重复登记时应更新最后出现回合"


# ── 矛盾检测（核心）──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mutable_change_allowed(db: AsyncSession) -> None:
    """职业变了是正常剧情，不该拦。"""
    e = await upsert_entity(db, SID, name="吴四娘", kind="person", turn=1)
    await record_fact(db, SID, e, key="职业", value="洗衣妇", turn=1)
    fact, conflict = await record_fact(db, SID, e, key="职业", value="茶馆帮工", turn=9)
    assert conflict is None
    assert fact is not None


@pytest.mark.asyncio
async def test_stable_change_blocked(db: AsyncSession) -> None:
    """出身变了是穿帮，必须拦住并报清楚。"""
    e = await upsert_entity(db, SID, name="吴四娘", kind="person", turn=1)
    await record_fact(db, SID, e, key="出身", value="陈家渡本地人", turn=3)
    fact, conflict = await record_fact(db, SID, e, key="出身", value="府城来的", turn=12)
    assert fact is None, "冲突时不应写入"
    assert conflict is not None
    assert "第3回合" in conflict.describe()
    assert "陈家渡本地人" in conflict.describe()


@pytest.mark.asyncio
async def test_player_declaration_overrides(db: AsyncSession) -> None:
    """玩家亲口说的，优先于 AI 之前编的。"""
    e = await upsert_entity(db, SID, name="吴四娘", kind="person", turn=1)
    await record_fact(db, SID, e, key="出身", value="陈家渡本地人", turn=3)
    fact, conflict = await record_fact(db, SID, e, key="出身", value="府城来的",
                                       turn=12, source="player")
    assert conflict is None and fact is not None


@pytest.mark.asyncio
async def test_same_value_is_noop(db: AsyncSession) -> None:
    """重复说同一件事不该产生新记录。"""
    e = await upsert_entity(db, SID, name="吴四娘", kind="person", turn=1)
    await record_fact(db, SID, e, key="职业", value="洗衣妇", turn=1)
    fact, conflict = await record_fact(db, SID, e, key="职业", value="洗衣妇", turn=5)
    assert fact is None and conflict is None


@pytest.mark.asyncio
async def test_superseded_chain_preserved(db: AsyncSession) -> None:
    """旧事实标记为被取代而非删除，保证可追溯。"""
    from app.services.memory import active_facts
    e = await upsert_entity(db, SID, name="吴四娘", kind="person", turn=1)
    await record_fact(db, SID, e, key="居所", value="渡口西头", turn=1)
    await record_fact(db, SID, e, key="居所", value="槐树巷", turn=8)
    await db.commit()
    live = await active_facts(db, e.id, "居所")
    assert len(live) == 1 and live[0].value == "槐树巷", "生效的应只有最新一条"


# ── 检索注入 ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retrieval_includes_mentioned_entity(db: AsyncSession) -> None:
    e = await upsert_entity(db, SID, name="吴四娘", kind="person", turn=1, aliases=["吴婶"])
    await record_fact(db, SID, e, key="职业", value="洗衣妇", turn=1)
    await db.commit()
    ctx = await retrieve_context(db, SID, mentioned=["吴婶"])
    assert "吴四娘" in ctx and "洗衣妇" in ctx


@pytest.mark.asyncio
async def test_retrieval_empty_when_no_facts(db: AsyncSession) -> None:
    """没有事实时返回空串，避免往提示词里塞无用的空标题。"""
    assert await retrieve_context(db, SID, mentioned=["谁也不是"]) == ""


@pytest.mark.asyncio
async def test_retrieval_prioritises_stable_facts(db: AsyncSession) -> None:
    """稳定设定排在前面——它们最不该被改错。"""
    e = await upsert_entity(db, SID, name="陈铁匠", kind="person", turn=1)
    await record_fact(db, SID, e, key="现状", value="正在打铁", turn=5)
    await record_fact(db, SID, e, key="出身", value="祖传三代铁匠", turn=2)
    await db.commit()
    ctx = await retrieve_context(db, SID)
    assert ctx.index("出身") < ctx.index("现状")
