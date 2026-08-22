"""
回合回滚测试
============
「一个回合是可以整体撤销的工作单元」——这是回合契约的核心含义。

不做的代价实测过：玩家点「重写本回合」，前端历史回退了，但服务端这一回合
写进去的事实全留着。被丢弃那版确立的设定会注入下一回合的提示词，而且
重写出来的新版本一旦说了别的，会被矛盾检测当成穿帮拦下来——
矛盾检测本来是保一致性的，却在强制执行玩家已经否决的内容。
"""
import asyncio
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Base, Entity, Fact, NarrativeEvent, Session  # noqa: E402
from app.services.memory import (  # noqa: E402
    active_facts, record_fact, resolve_entity, upsert_entity,
)
from app.services.turn_rollback import rollback_to_turn  # noqa: E402

SID = "roll-test"


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        s.add(Session(id=SID, title="t", world_id="wuxia"))
        await s.commit()
        yield s
    await engine.dispose()


async def _fact(db: AsyncSession, name: str, key: str, value: str, turn: int):
    ent = await upsert_entity(db, SID, name=name, kind="person", turn=turn)
    fact, conflict = await record_fact(db, SID, ent, key=key, value=value, turn=turn)
    await db.commit()
    return fact, conflict


# ── 基本回滚 ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rollback_discards_that_turn(db: AsyncSession) -> None:
    await _fact(db, "吴四娘", "职业", "洗衣妇", 3)
    await _fact(db, "吴四娘", "居所", "槐树巷", 5)

    removed = await rollback_to_turn(db, SID, 5)
    assert removed["facts"] == 1

    ent = await resolve_entity(db, SID, "吴四娘")
    keys = {f.key for f in await active_facts(db, ent.id)}
    assert keys == {"职业"}          # 第 5 回合那条没了
    assert ent.last_seen_turn == 3   # 「最后出现」退回真实位置


@pytest.mark.asyncio
async def test_rollback_reactivates_superseded_fact(db: AsyncSession) -> None:
    """
    最容易漏的一步：事实靠 superseded_by 串成链。
    只删掉新事实而不把它顶掉的旧事实放回来，那条属性就既没有新值
    也没有旧值——回滚反而把设定弄丢了。
    """
    await _fact(db, "吴四娘", "职业", "洗衣妇", 3)
    await _fact(db, "吴四娘", "职业", "茶馆帮工", 7)

    ent = await resolve_entity(db, SID, "吴四娘")
    assert [f.value for f in await active_facts(db, ent.id)] == ["茶馆帮工"]

    await rollback_to_turn(db, SID, 7)
    assert [f.value for f in await active_facts(db, ent.id)] == ["洗衣妇"]


@pytest.mark.asyncio
async def test_entity_born_in_discarded_turn_is_removed(db: AsyncSession) -> None:
    """只在被丢弃那回合出现过的人物，本身就是那次叙事的产物。"""
    await _fact(db, "吴四娘", "职业", "洗衣妇", 3)
    await _fact(db, "路人甲", "职业", "货郎", 9)

    removed = await rollback_to_turn(db, SID, 9)
    assert removed["entities"] == 1
    assert await resolve_entity(db, SID, "路人甲") is None
    assert await resolve_entity(db, SID, "吴四娘") is not None


@pytest.mark.asyncio
async def test_alias_of_removed_entity_is_gone(db: AsyncSession) -> None:
    """别名跟着实体走，否则下回合用别名还能「解析」到一个已经不存在的人。"""
    await upsert_entity(db, SID, name="王掌柜", kind="person", turn=9,
                        aliases=["老王"])
    await record_fact(db, SID, await resolve_entity(db, SID, "王掌柜"),
                      key="职业", value="掌柜", turn=9)
    await db.commit()

    await rollback_to_turn(db, SID, 9)
    assert await resolve_entity(db, SID, "老王") is None


# ── 重写回合的完整场景 ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_regenerated_turn_is_not_blocked_by_discarded_version(db: AsyncSession) -> None:
    """
    这条就是整个功能存在的理由。

    第 5 回合叙事说「府城来的」→ 玩家不满意点重写 →
    没有回滚的话，重写出的「陈家渡本地人」会被当成矛盾拦下，
    玩家已经否决的那版反而赢了。
    """
    _, conflict = await _fact(db, "吴四娘", "出身", "府城来的", 5)
    assert conflict is None

    # 回滚这一回合，然后重跑
    await rollback_to_turn(db, SID, 5)
    _, conflict = await _fact(db, "吴四娘", "出身", "陈家渡本地人", 5)

    assert conflict is None, "重写后的新版本不该被已丢弃的那版拦住"
    ent = await resolve_entity(db, SID, "吴四娘")
    assert [f.value for f in await active_facts(db, ent.id)] == ["陈家渡本地人"]


@pytest.mark.asyncio
async def test_rollback_is_idempotent(db: AsyncSession) -> None:
    """
    回滚也是回合的幂等机制：先回滚到 N 再重跑第 N 回合，天然不会重复累积。
    所以重复回滚本身必须安全。
    """
    await _fact(db, "吴四娘", "职业", "洗衣妇", 3)
    await _fact(db, "吴四娘", "居所", "槐树巷", 5)

    first = await rollback_to_turn(db, SID, 5)
    second = await rollback_to_turn(db, SID, 5)
    assert first["facts"] == 1 and second["facts"] == 0

    ent = await resolve_entity(db, SID, "吴四娘")
    assert len(await active_facts(db, ent.id)) == 1


@pytest.mark.asyncio
async def test_rollback_to_zero_clears_everything(db: AsyncSession) -> None:
    await _fact(db, "吴四娘", "职业", "洗衣妇", 0)
    await _fact(db, "陈家渡", "类型", "渡口小镇", 2)

    await rollback_to_turn(db, SID, 0)
    assert await resolve_entity(db, SID, "吴四娘") is None
    assert await resolve_entity(db, SID, "陈家渡") is None


@pytest.mark.asyncio
async def test_earlier_turns_survive_untouched(db: AsyncSession) -> None:
    """回滚是「从第 N 回合起」，之前的进度一个字都不能动。"""
    for turn, key, value in ((1, "职业", "洗衣妇"), (2, "居所", "河边"),
                             (8, "现状", "病了")):
        await _fact(db, "吴四娘", key, value, turn)

    await rollback_to_turn(db, SID, 8)
    ent = await resolve_entity(db, SID, "吴四娘")
    assert {f.key for f in await active_facts(db, ent.id)} == {"职业", "居所"}


# ── 叙事账本一起回滚 ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_narrative_events_are_rolled_back_too(db: AsyncSession) -> None:
    """事实库和叙事账本必须同进同退，否则两边说的话对不上。"""
    db.add(NarrativeEvent(id="e1", session_id=SID, turn=4, kind="scene",
                          action="进城", outcome="到了"))
    db.add(NarrativeEvent(id="e2", session_id=SID, turn=6, kind="scene",
                          action="被丢弃的事", outcome="x"))
    await db.commit()

    removed = await rollback_to_turn(db, SID, 6)
    assert removed["events"] == 1
    left = list((await db.execute(
        __import__("sqlalchemy").select(NarrativeEvent)
    )).scalars())
    assert [e.id for e in left] == ["e1"]
