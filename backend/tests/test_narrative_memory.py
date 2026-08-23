"""结构化叙事账本、承诺和 NPC 知识边界的回归测试。"""
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Base, NarrativeEvent, Session  # noqa: E402
from app.schemas.narrative import NarrativeLedgerWrite  # noqa: E402
from app.services.extractor import parse_bundle  # noqa: E402
from app.services.memory import retrieve_context_bundle  # noqa: E402
from app.services.narrative_memory import ledger_snapshot, write_ledger  # noqa: E402

SID = "narrative-test"


def test_extractor_bundle_sanitizes_all_memory_layers() -> None:
    raw = """```json
    {"entities":[],"events":[{"kind":"action","actor":"莉亚","action":"藏起钥匙", "visibility":"private"}],
    "commitments":[{"kind":"refusal","owner":"玩家","text":"不加入队伍","hard":true,"forbids":["不要重提"]}],
    "beliefs":[{"npc":"老板","statement":"钥匙丢了","mode":"misinformed","confidence":999}],
    "character_states":[{"name":"老板","mid_term":{"goal":"找帮工"}}]}
    ```"""
    bundle = parse_bundle(raw)
    assert bundle["events"][0]["visibility"] == "private"
    assert bundle["commitments"][0]["hard"] is True
    assert bundle["beliefs"][0]["confidence"] == 100
    assert bundle["character_states"][0]["mid_term"]["goal"] == "找帮工"


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        session.add(Session(id=SID, title="t", world_id="fantasy"))
        await session.commit()
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_ledger_write_is_idempotent(db: AsyncSession) -> None:
    payload = NarrativeLedgerWrite.model_validate({
        "turn": 3,
        "events": [{"kind": "player_turn", "actor": "玩家", "action": "去面包店问工作",
                    "outcome": "老板说明了工时", "participants": ["老板"]}],
    })
    first = await write_ledger(db, SID, payload)
    second = await write_ledger(db, SID, payload)
    await db.commit()
    count = await db.scalar(select(func.count(NarrativeEvent.id)))
    assert first["events_written"] == 1
    assert second["events_written"] == 0
    assert count == 1


@pytest.mark.asyncio
async def test_client_ids_are_namespaced_when_two_saves_reuse_them(db: AsyncSession) -> None:
    other = "narrative-other"
    db.add(Session(id=other, title="other", world_id="fantasy"))
    await db.commit()
    row = {"turn": 2, "commitments": [{"id": "com_same_text", "kind": "refusal",
           "owner": "玩家", "text": "我拒绝", "status": "rejected", "hard": True}]}
    await write_ledger(db, SID, NarrativeLedgerWrite.model_validate(row))
    await write_ledger(db, other, NarrativeLedgerWrite.model_validate(row))
    await db.commit()
    a = await ledger_snapshot(db, SID)
    b = await ledger_snapshot(db, other)
    assert len(a["commitments"]) == len(b["commitments"]) == 1
    assert a["commitments"][0]["id"] != b["commitments"][0]["id"]


@pytest.mark.asyncio
async def test_context_keeps_refusal_and_does_not_reinject_future_event(db: AsyncSession) -> None:
    await write_ledger(db, SID, NarrativeLedgerWrite.model_validate({
        "turn": 2,
        "events": [{"id": "evt_now", "actor": "玩家", "action": "拒绝加入冒险队",
                    "outcome": "双方结束谈话"}],
        "commitments": [{"id": "com_no_party", "kind": "refusal", "owner": "玩家",
                         "text": "玩家拒绝加入冒险队", "status": "rejected", "hard": True,
                         "forbids": ["不得把同一邀请换皮重提"]}],
    }))
    await write_ledger(db, SID, NarrativeLedgerWrite.model_validate({
        "turn": 9,
        "events": [{"id": "evt_future", "actor": "队长", "action": "再次发出邀请"}],
    }))
    await db.commit()
    ctx = await retrieve_context_bundle(db, SID, mentioned=["冒险队"], current_turn=3)
    assert "com_no_party" in ctx.text
    assert "不得把同一邀请换皮重提" in ctx.text
    assert "evt_future" not in ctx.text


@pytest.mark.asyncio
async def test_private_event_and_belief_respect_speaker_boundary(db: AsyncSession) -> None:
    await write_ledger(db, SID, NarrativeLedgerWrite.model_validate({
        "turn": 4,
        "events": [{"id": "evt_secret", "actor": "莉亚", "action": "把钥匙藏进花盆",
                    "participants": ["莉亚"], "visibility": "participants"}],
        "beliefs": [
            {"npc": "莉亚", "statement": "钥匙在花盆里", "mode": "knows"},
            {"npc": "老板", "statement": "钥匙已经丢了", "mode": "misinformed", "confidence": 80},
        ],
    }))
    await db.commit()
    lia = await retrieve_context_bundle(db, SID, mentioned=["莉亚"], current_turn=5, speaker="莉亚")
    boss = await retrieve_context_bundle(db, SID, mentioned=["老板"], current_turn=5, speaker="老板")
    assert "evt_secret" in lia.text and "钥匙在花盆里" in lia.text
    assert "evt_secret" not in boss.text
    assert "钥匙已经丢了" in boss.text and "钥匙在花盆里" not in boss.text


@pytest.mark.asyncio
async def test_character_state_layers_do_not_get_erased_by_empty_update(db: AsyncSession) -> None:
    await write_ledger(db, SID, NarrativeLedgerWrite.model_validate({
        "turn": 1,
        "character_states": [{"name": "老板", "identity": {"role": "店主"},
                              "mid_term": {"goal": "找到帮工"}}],
    }))
    await write_ledger(db, SID, NarrativeLedgerWrite.model_validate({
        "turn": 2,
        "character_states": [{"name": "老板", "short_term": {"mood": "忙碌"}}],
    }))
    await db.commit()
    snap = await ledger_snapshot(db, SID)
    row = snap["character_states"][0]
    assert row["identity"] == {"role": "店主"}
    assert row["mid_term"] == {"goal": "找到帮工"}
    assert row["short_term"] == {"mood": "忙碌"}
    ctx = await retrieve_context_bundle(db, SID, mentioned=["老板"], current_turn=8)
    assert "找到帮工" in ctx.text
    assert "忙碌" not in ctx.text
    assert any(x["reason"] == "短期状态已自然衰减" for x in ctx.trace)
