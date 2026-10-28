"""
服务层 · 回合回滚
=================
把「一个回合」变成可以整体撤销的工作单元。

要解决的具体问题：
    玩家点「重写本回合」或「撤销上一回合」时，前端把历史和状态回退了，
    但服务端这一回合写进去的事实、事件、承诺、NPC 认知全都留着。
    后果不只是脏数据——被丢弃那版确立的设定会在下一回合注入提示词，
    而且重写出来的新版本一旦说了别的，会被矛盾检测当成穿帮拦下来。
    也就是说：矛盾检测本来是保一致性的，却在强制执行玩家已经否决的内容。

做法：所有叙事记录本来就带回合号，所以回滚 = 删掉回合号 >= N 的记录。
关键是别只删表面——事实用 superseded_by 串成链，删掉新事实必须把它顶掉的
旧事实重新激活，否则回滚完那条属性就凭空消失了。

回滚同时也是回合的幂等机制：先回滚到 N 再重跑第 N 回合，天然不会重复累积。
"""
import json

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    CharacterState, Commitment, Entity, EntityAlias, Fact, LedgerRevision,
    NarrativeEvent, NpcBelief, TurnCommit,
)


_REVISION_MODELS = {
    "commitment": (
        Commitment,
        ("id", "session_id", "kind", "owner_name", "counterparty_name", "text",
         "status", "hard", "created_turn", "updated_turn", "due_turn",
         "forbids_json", "source_event_id"),
    ),
    "belief": (
        NpcBelief,
        ("id", "session_id", "npc_name", "statement", "mode", "confidence",
         "source_name", "learned_turn", "updated_turn", "status"),
    ),
    "character_state": (
        CharacterState,
        ("id", "session_id", "entity_name", "identity_json", "mid_term_json",
         "short_term_json", "relationships_json", "updated_turn"),
    ),
}


async def _restore_ledger_revisions(
    db: AsyncSession, session_id: str, from_turn: int,
) -> None:
    """把所有后续更新恢复到 `from_turn` 之前最后一次可见的版本。"""
    revisions = list((await db.execute(
        select(LedgerRevision).where(
            LedgerRevision.session_id == session_id,
            LedgerRevision.change_turn >= from_turn,
        ).order_by(LedgerRevision.change_turn.asc(), LedgerRevision.id.asc())
    )).scalars())

    # 同一记录可能在第 6、8 回合各更新一次。回滚到第 6 回合时应恢复
    # “第 6 回合修改前”的最早快照，而不是第 8 回合修改前的中间状态。
    earliest: dict[tuple[str, str], LedgerRevision] = {}
    for revision in revisions:
        earliest.setdefault(
            (revision.record_type, revision.record_key), revision,
        )

    for (record_type, record_key), revision in earliest.items():
        spec = _REVISION_MODELS.get(record_type)
        if spec is None:
            continue
        model, fields = spec
        try:
            snapshot = json.loads(revision.snapshot_json)
        except (TypeError, json.JSONDecodeError):
            continue
        identity = record_key if record_type == "commitment" else int(record_key)
        row = await db.get(model, identity)
        values = {field: snapshot[field] for field in fields if field in snapshot}
        if row is None:
            row = model(**values)
            db.add(row)
        else:
            for field, value in values.items():
                if field not in {"id", "session_id"}:
                    setattr(row, field, value)

    # 后续的删除查询必须看到刚恢复的 updated_turn。
    await db.flush()
    if revisions:
        await db.execute(delete(LedgerRevision).where(
            LedgerRevision.session_id == session_id,
            LedgerRevision.change_turn >= from_turn,
        ))


async def rollback_to_turn(
    db: AsyncSession, session_id: str, from_turn: int
) -> dict[str, int]:
    """
    丢弃第 `from_turn` 回合及其之后写入的全部叙事记录。

    返回各类记录删了多少条，供前端如实告诉玩家动了什么。
    """
    from_turn = max(0, int(from_turn))
    removed = {"facts": 0, "entities": 0, "events": 0,
               "commitments": 0, "beliefs": 0, "character_states": 0,
               "turn_commits": 0}

    # ── 事实 ────────────────────────────────────────────────────
    # 先取出要删的，因为还得把它们顶掉的旧事实放回来
    doomed = list((await db.execute(
        select(Fact).where(Fact.session_id == session_id, Fact.turn >= from_turn)
    )).scalars())
    doomed_ids = [f.id for f in doomed]

    if doomed_ids:
        # 关键一步：被这些事实取代的旧事实要重新激活。
        # 少了这步，回滚之后那条属性就既没有新值也没有旧值了。
        await db.execute(
            update(Fact)
            .where(Fact.session_id == session_id, Fact.superseded_by.in_(doomed_ids))
            .values(superseded_by=None)
        )
        await db.execute(delete(Fact).where(Fact.id.in_(doomed_ids)))
        removed["facts"] = len(doomed_ids)

    # ── 实体 ────────────────────────────────────────────────────
    # 只在被丢弃的回合里出现过的实体，连同别名一起删掉——
    # 它们的存在本身就是那次叙事的产物。
    born_late = list((await db.execute(
        select(Entity).where(Entity.session_id == session_id, Entity.first_turn >= from_turn)
    )).scalars())
    for ent in born_late:
        await db.execute(delete(EntityAlias).where(EntityAlias.entity_id == ent.id))
        await db.delete(ent)
    removed["entities"] = len(born_late)

    # 活下来的实体，把「最后出现回合」退回到它剩余事实的真实位置，
    # 否则检索时会以为它刚刚还在场
    survivors = list((await db.execute(
        select(Entity).where(Entity.session_id == session_id, Entity.first_turn < from_turn)
    )).scalars())
    for ent in survivors:
        if ent.last_seen_turn >= from_turn:
            latest = await db.scalar(
                select(func.max(Fact.turn)).where(Fact.entity_id == ent.id)
            )
            ent.last_seen_turn = int(latest) if latest is not None else ent.first_turn

    # ── 叙事账本 ────────────────────────────────────────────────
    # 先恢复被后续回合原地修改的旧记录，再删除真正诞生于被丢弃区间的记录。
    # 没有这层版本快照，fulfilled/active、NPC认知和人物目标一旦更新就无法撤回。
    await _restore_ledger_revisions(db, session_id, from_turn)
    for model, key, field in (
        (NarrativeEvent, "events", NarrativeEvent.turn),
        (Commitment, "commitments", Commitment.created_turn),
        (NpcBelief, "beliefs", NpcBelief.learned_turn),
        (CharacterState, "character_states", CharacterState.updated_turn),
    ):
        rows = list((await db.execute(
            select(model).where(model.session_id == session_id, field >= from_turn)
        )).scalars())
        for row in rows:
            await db.delete(row)
        removed[key] = len(rows)

    commits = list((await db.execute(
        select(TurnCommit).where(
            TurnCommit.session_id == session_id,
            TurnCommit.turn_no >= from_turn,
        )
    )).scalars())
    for commit in commits:
        await db.delete(commit)
    removed["turn_commits"] = len(commits)

    await db.commit()
    return removed
