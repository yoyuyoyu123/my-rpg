"""比散文摘要更可靠的叙事账本与知识边界。"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    CharacterState, Commitment, LedgerRevision, NarrativeEvent, NpcBelief,
)
from app.schemas.narrative import NarrativeLedgerWrite


def _json(value: Any, fallback: str) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")) if value is not None else fallback


def _load(value: str, fallback: Any) -> Any:
    try:
        data = json.loads(value or "")
        return data
    except (TypeError, json.JSONDecodeError):
        return fallback


def _fingerprint(prefix: str, session_id: str, turn: int, *parts: str) -> str:
    raw = "\x1f".join([session_id, str(turn), *[str(x or "").strip() for x in parts]])
    return prefix + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


async def _remember_revision(
    db: AsyncSession,
    *,
    session_id: str,
    record_type: str,
    record_key: str | int,
    change_turn: int,
    snapshot: dict[str, Any],
) -> None:
    """同一记录每回合只保存一次“修改前”快照。"""
    key = str(record_key)
    exists = await db.scalar(select(LedgerRevision.id).where(
        LedgerRevision.session_id == session_id,
        LedgerRevision.record_type == record_type,
        LedgerRevision.record_key == key,
        LedgerRevision.change_turn == change_turn,
    ))
    if exists is None:
        db.add(LedgerRevision(
            session_id=session_id,
            record_type=record_type,
            record_key=key,
            change_turn=change_turn,
            snapshot_json=_json(snapshot, "{}"),
        ))


async def write_ledger(
    db: AsyncSession, session_id: str, payload: NarrativeLedgerWrite,
) -> dict[str, int]:
    """幂等写入一批结构化叙事状态；同一回合重试不会制造重复记录。"""
    counts = {"events_written": 0, "commitments_written": 0,
              "beliefs_written": 0, "character_states_written": 0}

    for row in payload.events[:12]:
        action = row.action.strip()
        outcome = row.outcome.strip()
        if not action and not outcome:
            continue
        eid = row.id.strip() or _fingerprint(
            "evt_", session_id, payload.turn, row.kind, row.actor, action, outcome,
        )
        old = await db.get(NarrativeEvent, eid)
        if old is not None and old.session_id != session_id:
            # 前端/模型给的短 ID 可能在另一局重复；绝不能跨存档复用主键。
            eid = _fingerprint("evt_", session_id, payload.turn, row.kind, row.actor, action, outcome)
            old = await db.get(NarrativeEvent, eid)
        if old is None:
            db.add(NarrativeEvent(
                id=eid, session_id=session_id, turn=payload.turn,
                kind=row.kind.strip() or "scene", actor=row.actor.strip(),
                action=action, outcome=outcome, location=row.location.strip(),
                participants_json=_json([x.strip()[:80] for x in row.participants[:12] if x.strip()], "[]"),
                cause_ids_json=_json([x.strip()[:64] for x in row.cause_ids[:8] if x.strip()], "[]"),
                visibility=row.visibility, source=row.source.strip() or "narrative",
            ))
            counts["events_written"] += 1

    for row in payload.commitments[:12]:
        text = row.text.strip()
        if not text:
            continue
        cid = row.id.strip() or _fingerprint(
            "com_", session_id, payload.turn, row.kind, row.owner, row.counterparty, text,
        )
        old = await db.get(Commitment, cid)
        if old is not None and old.session_id != session_id:
            cid = _fingerprint(
                "com_", session_id, payload.turn, row.kind, row.owner, row.counterparty, text,
            )
            old = await db.get(Commitment, cid)
        if old is None:
            db.add(Commitment(
                id=cid, session_id=session_id, kind=row.kind,
                owner_name=row.owner.strip(), counterparty_name=row.counterparty.strip(),
                text=text, status=row.status, hard=1 if row.hard else 0,
                created_turn=payload.turn, updated_turn=payload.turn, due_turn=row.due_turn,
                forbids_json=_json([x.strip()[:240] for x in row.forbids[:8] if x.strip()], "[]"),
                source_event_id=row.source_event_id.strip(),
            ))
            counts["commitments_written"] += 1
        else:
            if payload.turn < old.updated_turn:
                continue  # 后台抽取晚到：旧回合不得覆盖已经确认的新回合
            await _remember_revision(
                db,
                session_id=session_id,
                record_type="commitment",
                record_key=old.id,
                change_turn=payload.turn,
                snapshot={
                    "id": old.id,
                    "session_id": old.session_id,
                    "kind": old.kind,
                    "owner_name": old.owner_name,
                    "counterparty_name": old.counterparty_name,
                    "text": old.text,
                    "status": old.status,
                    "hard": old.hard,
                    "created_turn": old.created_turn,
                    "updated_turn": old.updated_turn,
                    "due_turn": old.due_turn,
                    "forbids_json": old.forbids_json,
                    "source_event_id": old.source_event_id,
                },
            )
            old.status = row.status
            old.updated_turn = payload.turn
            old.due_turn = row.due_turn
            old.hard = 1 if row.hard else old.hard
            if row.forbids:
                old.forbids_json = _json(row.forbids[:8], "[]")

    for row in payload.beliefs[:24]:
        npc, statement = row.npc.strip(), row.statement.strip()
        if not npc or not statement:
            continue
        stmt = select(NpcBelief).where(
            NpcBelief.session_id == session_id,
            NpcBelief.npc_name == npc,
            NpcBelief.statement == statement,
        )
        old = (await db.execute(stmt)).scalar_one_or_none()
        if old is None:
            db.add(NpcBelief(
                session_id=session_id, npc_name=npc, statement=statement,
                mode=row.mode, confidence=row.confidence, source_name=row.source.strip(),
                learned_turn=payload.turn, updated_turn=payload.turn, status=row.status,
            ))
            counts["beliefs_written"] += 1
        else:
            if payload.turn < max(old.learned_turn, old.updated_turn):
                continue
            await _remember_revision(
                db,
                session_id=session_id,
                record_type="belief",
                record_key=old.id,
                change_turn=payload.turn,
                snapshot={
                    "id": old.id,
                    "session_id": old.session_id,
                    "npc_name": old.npc_name,
                    "statement": old.statement,
                    "mode": old.mode,
                    "confidence": old.confidence,
                    "source_name": old.source_name,
                    "learned_turn": old.learned_turn,
                    "updated_turn": old.updated_turn,
                    "status": old.status,
                },
            )
            old.mode = row.mode
            old.confidence = row.confidence
            old.source_name = row.source.strip() or old.source_name
            old.status = row.status
            old.updated_turn = payload.turn

    for row in payload.character_states[:12]:
        name = row.name.strip()
        if not name:
            continue
        stmt = select(CharacterState).where(
            CharacterState.session_id == session_id, CharacterState.entity_name == name,
        )
        old = (await db.execute(stmt)).scalar_one_or_none()
        if old is None:
            db.add(CharacterState(
                session_id=session_id, entity_name=name,
                identity_json=_json(row.identity, "{}"),
                mid_term_json=_json(row.mid_term, "{}"),
                short_term_json=_json(row.short_term, "{}"),
                relationships_json=_json(row.relationships, "{}"),
                updated_turn=payload.turn,
            ))
            counts["character_states_written"] += 1
        else:
            if payload.turn < old.updated_turn:
                continue
            await _remember_revision(
                db,
                session_id=session_id,
                record_type="character_state",
                record_key=old.id,
                change_turn=payload.turn,
                snapshot={
                    "id": old.id,
                    "session_id": old.session_id,
                    "entity_name": old.entity_name,
                    "identity_json": old.identity_json,
                    "mid_term_json": old.mid_term_json,
                    "short_term_json": old.short_term_json,
                    "relationships_json": old.relationships_json,
                    "updated_turn": old.updated_turn,
                },
            )
            # 空层不覆盖已有层：抽取器没观察到，不等于人物失去目标或关系。
            if row.identity:
                old.identity_json = _json(row.identity, "{}")
            if row.mid_term:
                old.mid_term_json = _json(row.mid_term, "{}")
            if row.short_term:
                old.short_term_json = _json(row.short_term, "{}")
            if row.relationships:
                old.relationships_json = _json(row.relationships, "{}")
            old.updated_turn = payload.turn

    return counts


def _mentions(text: str, names: list[str]) -> bool:
    folded = re.sub(r"\s+", "", text).casefold()
    return any(n and re.sub(r"\s+", "", n).casefold() in folded for n in names)


async def retrieve_narrative_context(
    db: AsyncSession,
    session_id: str,
    *,
    mentioned: list[str] | None = None,
    current_turn: int = 0,
    speaker: str = "",
    max_events: int = 6,
    max_commitments: int = 8,
) -> tuple[list[str], list[dict[str, Any]], dict[str, int]]:
    """返回提示词段、可解释检索轨迹和各类命中计数。"""
    names = [x.strip() for x in (mentioned or []) if x.strip()]
    trace: list[dict[str, Any]] = []
    sections: list[str] = []
    counts = {"event_count": 0, "commitment_count": 0,
              "belief_count": 0, "character_state_count": 0}

    event_stmt = select(NarrativeEvent).where(NarrativeEvent.session_id == session_id)
    if current_turn > 0:
        event_stmt = event_stmt.where(NarrativeEvent.turn <= current_turn)
    events = list((await db.execute(
        event_stmt.order_by(NarrativeEvent.turn.desc(), NarrativeEvent.created_at.desc()).limit(40)
    )).scalars())
    chosen_events: list[NarrativeEvent] = []
    for event in events:
        participants = _load(event.participants_json, [])
        blob = " ".join([event.actor, event.action, event.outcome, event.location, *participants])
        relevant = bool(names and _mentions(blob, names))
        visible = event.visibility == "public" or not speaker or speaker in participants or speaker == event.actor
        if not visible:
            trace.append({"id": event.id, "type": "event", "included": False,
                          "reason": f"对 {speaker} 不可见", "source": event.source or "narrative",
                          "turn": event.turn, "version": event.id})
            continue
        if relevant or len(chosen_events) < max(2, max_events // 2):
            chosen_events.append(event)
            trace.append({"id": event.id, "type": "event", "included": True,
                          "reason": "提及实体命中" if relevant else "近期事件",
                          "source": event.source or "narrative", "turn": event.turn,
                          "version": event.id})
        if len(chosen_events) >= max_events:
            break
    if chosen_events:
        lines = []
        for event in reversed(chosen_events):
            visibility = "" if event.visibility == "public" else f"；可见性={event.visibility}"
            outcome = f" → {event.outcome}" if event.outcome else ""
            lines.append(f"- [{event.id}｜第{event.turn}回合] {event.actor or '场景'}：{event.action}{outcome}{visibility}")
        sections.append("【相关事件时间线——按因果与时间保持一致】\n" + "\n".join(lines))
        counts["event_count"] = len(chosen_events)

    com_stmt = select(Commitment).where(
        Commitment.session_id == session_id,
        Commitment.status.in_(["active", "rejected"]),
    )
    if current_turn > 0:
        com_stmt = com_stmt.where(Commitment.created_turn <= current_turn)
    commitments = list((await db.execute(
        com_stmt.order_by(Commitment.hard.desc(), Commitment.updated_turn.desc()).limit(max_commitments * 3)
    )).scalars())
    chosen_coms: list[Commitment] = []
    for item in commitments:
        blob = " ".join([item.owner_name, item.counterparty_name, item.text])
        relevant = not names or _mentions(blob, names) or bool(item.hard)
        if relevant:
            chosen_coms.append(item)
            trace.append({"id": item.id, "type": "commitment", "included": True,
                          "reason": "硬约束" if item.hard else "人物/主题命中",
                          "source": item.source_event_id or "ledger", "turn": item.updated_turn,
                          "version": item.id})
        if len(chosen_coms) >= max_commitments:
            break
    if chosen_coms:
        lines = []
        for item in chosen_coms:
            forbids = _load(item.forbids_json, [])
            tail = ("；禁止=" + "／".join(forbids)) if forbids else ""
            due = f"；最迟第{item.due_turn}回合" if item.due_turn is not None else ""
            lines.append(
                f"- [{item.id}｜{item.kind}｜{item.status}] {item.owner_name or '未注明'}：{item.text}{due}{tail}"
            )
        sections.append("【活跃承诺与拒绝——必须兑现或尊重，不得换皮重置】\n" + "\n".join(lines))
        counts["commitment_count"] = len(chosen_coms)

    state_stmt = select(CharacterState).where(CharacterState.session_id == session_id)
    states = list((await db.execute(
        state_stmt.order_by(CharacterState.updated_turn.desc()).limit(30)
    )).scalars())
    chosen_states = [x for x in states if (x.entity_name in names or x.entity_name == speaker)][:8]
    if chosen_states:
        lines = []
        for item in chosen_states:
            layers = []
            for label, raw in (("身份", item.identity_json), ("中期", item.mid_term_json),
                               ("眼前", item.short_term_json), ("关系", item.relationships_json)):
                value = _load(raw, {})
                # 没有后续事件维持时，短期情绪/眼前动作 4 回合后不再注入；
                # 数据仍保留在账本中供回溯，但不会把人物永久锁成某种心情。
                if label == "眼前" and current_turn > 0 and current_turn - item.updated_turn > 4:
                    if value:
                        trace.append({"id": f"char:{item.id}:short", "type": "character_state",
                                      "included": False, "reason": "短期状态已自然衰减",
                                      "source": "ledger", "turn": item.updated_turn,
                                      "version": item.id})
                    value = {}
                if value:
                    layers.append(label + "=" + json.dumps(value, ensure_ascii=False, separators=(",", ":")))
            if layers:
                lines.append(f"- {item.entity_name}（第{item.updated_turn}回合更新）：" + "；".join(layers))
                trace.append({"id": f"char:{item.id}", "type": "character_state",
                              "included": True, "reason": "在场人物", "source": "ledger",
                              "turn": item.updated_turn, "version": item.id})
        if lines:
            sections.append("【人物动态状态——短期情绪不能覆盖身份与长期目标】\n" + "\n".join(lines))
            counts["character_state_count"] = len(lines)

    belief_names = [speaker] if speaker else names
    if belief_names:
        belief_stmt = select(NpcBelief).where(
            NpcBelief.session_id == session_id,
            NpcBelief.npc_name.in_(belief_names),
            NpcBelief.status == "active",
        )
        if current_turn > 0:
            belief_stmt = belief_stmt.where(NpcBelief.learned_turn <= current_turn)
        beliefs = list((await db.execute(
            belief_stmt.order_by(NpcBelief.learned_turn.desc()).limit(24)
        )).scalars())
        if beliefs:
            lines = [
                f"- {b.npc_name} [{b.mode}，置信{b.confidence}%]：{b.statement}"
                + (f"（来源={b.source_name}）" if b.source_name else "")
                for b in beliefs
            ]
            sections.append(
                "【NPC 各自知识边界——belief 不是世界真相】\n" + "\n".join(lines)
                + "\nNPC 只能据自己的条目、当场可见证据和公开信息行动；不得读取其它 NPC 的条目或后台正史。"
            )
            counts["belief_count"] = len(beliefs)
            trace.extend({"id": f"belief:{b.id}", "type": "belief", "included": True,
                          "reason": "当前说话者" if speaker else "提及 NPC",
                          "source": b.source_name or "ledger", "turn": b.learned_turn,
                          "version": b.id} for b in beliefs)

    return sections, trace, counts


async def ledger_snapshot(db: AsyncSession, session_id: str, limit: int = 30) -> dict[str, list[dict[str, Any]]]:
    """供监视器/调试页读取，内容经过限额，不返回提示词或凭据。"""
    events = list((await db.execute(
        select(NarrativeEvent).where(NarrativeEvent.session_id == session_id)
        .order_by(NarrativeEvent.turn.desc()).limit(limit)
    )).scalars())
    commitments = list((await db.execute(
        select(Commitment).where(Commitment.session_id == session_id)
        .order_by(Commitment.updated_turn.desc()).limit(limit)
    )).scalars())
    beliefs = list((await db.execute(
        select(NpcBelief).where(NpcBelief.session_id == session_id)
        .order_by(NpcBelief.learned_turn.desc()).limit(limit)
    )).scalars())
    states = list((await db.execute(
        select(CharacterState).where(CharacterState.session_id == session_id)
        .order_by(CharacterState.updated_turn.desc()).limit(limit)
    )).scalars())
    return {
        "events": [{"id": x.id, "turn": x.turn, "kind": x.kind, "actor": x.actor,
                    "action": x.action, "outcome": x.outcome, "location": x.location,
                    "participants": _load(x.participants_json, []), "visibility": x.visibility}
                   for x in events],
        "commitments": [{"id": x.id, "kind": x.kind, "owner": x.owner_name,
                         "counterparty": x.counterparty_name, "text": x.text,
                         "status": x.status, "hard": bool(x.hard), "updated_turn": x.updated_turn,
                         "forbids": _load(x.forbids_json, [])} for x in commitments],
        "beliefs": [{"id": x.id, "npc": x.npc_name, "statement": x.statement,
                     "mode": x.mode, "confidence": x.confidence, "source": x.source_name,
                     "learned_turn": x.learned_turn, "updated_turn": x.updated_turn,
                     "status": x.status} for x in beliefs],
        "character_states": [{"id": x.id, "name": x.entity_name,
                              "identity": _load(x.identity_json, {}),
                              "mid_term": _load(x.mid_term_json, {}),
                              "short_term": _load(x.short_term_json, {}),
                              "relationships": _load(x.relationships_json, {}),
                              "updated_turn": x.updated_turn} for x in states],
    }
