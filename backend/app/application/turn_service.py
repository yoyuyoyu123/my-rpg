"""TurnService 第一阶段：原子提交叙事账本与自动存档。"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Session, TurnCommit
from app.schemas.narrative import NarrativeLedgerResult
from app.schemas.turn_commit import TurnCommitRequest, TurnCommitResult
from app.services.narrative_memory import write_ledger
from app.services.save_store import SaveStoreError, prepare_save_write, to_summary


@dataclass
class TurnCommitError(Exception):
    status_code: int
    code: str
    message: str
    extra: dict = field(default_factory=dict)

    def detail(self) -> dict:
        return {"code": self.code, "message": self.message, **self.extra}


def _request_hash(req: TurnCommitRequest) -> str:
    raw = json.dumps(
        req.model_dump(mode="json", exclude={"commit_id"}),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validate_contract(session: Session, req: TurnCommitRequest) -> None:
    turn = req.ledger.turn
    payload_turn = int(req.save.payload.get("turns") or 0)
    lore_sid = str(req.save.payload.get("loreSid") or "")
    if req.save.base_revision is None:
        raise TurnCommitError(
            422, "turn_commit_requires_revision",
            "自动存档提交必须携带 base_revision，不能静默强制覆盖其它设备的进度",
        )
    if turn != req.save.turns or turn != payload_turn:
        raise TurnCommitError(
            422, "turn_number_mismatch",
            "账本回合、存档摘要回合和存档正文回合必须一致",
            {"ledger_turn": turn, "save_turns": req.save.turns, "payload_turns": payload_turn},
        )
    if lore_sid != session.id:
        raise TurnCommitError(
            422, "turn_session_mismatch",
            "存档 loreSid 与提交目标会话不一致",
        )
    if req.save.world_id != session.world_id:
        raise TurnCommitError(
            422, "turn_world_mismatch",
            "存档世界与会话世界不一致",
        )


async def commit_completed_turn(
    db: AsyncSession, session_id: str, req: TurnCommitRequest,
) -> TurnCommitResult:
    """账本、会话回合号、自动存档和幂等记录一次提交。"""
    request_hash = _request_hash(req)
    existing = await db.get(TurnCommit, req.commit_id)
    if existing is not None:
        if existing.session_id != session_id or existing.request_hash != request_hash:
            raise TurnCommitError(
                409, "commit_id_reused",
                "同一个 commit_id 已被用于不同的回合内容",
            )
        cached = TurnCommitResult.model_validate_json(existing.result_json)
        return cached.model_copy(update={"replayed": True})

    session = await db.get(Session, session_id)
    if session is None:
        raise TurnCommitError(404, "session_not_found", "存档不存在")
    _validate_contract(session, req)

    other = await db.scalar(select(TurnCommit).where(
        TurnCommit.session_id == session_id,
        TurnCommit.turn_no == req.ledger.turn,
    ))
    if other is not None:
        raise TurnCommitError(
            409, "turn_already_committed",
            f"第 {req.ledger.turn} 回合已经由另一个提交完成；重写前必须先回滚",
            {"existing_commit_id": other.id},
        )

    try:
        counts = await write_ledger(db, session_id, req.ledger)
        save, notes = await prepare_save_write(db, req.save_slot, req.save)
        session.turn_no = max(session.turn_no, req.ledger.turn)
        await db.flush()
        await db.refresh(save)
        summary = to_summary(save)
        summary.migrations = notes
        result = TurnCommitResult(
            commit_id=req.commit_id,
            turn=req.ledger.turn,
            ledger=NarrativeLedgerResult(**counts),
            save=summary,
        )
        db.add(TurnCommit(
            id=req.commit_id,
            session_id=session_id,
            turn_no=req.ledger.turn,
            save_slot=req.save_slot,
            request_hash=request_hash,
            result_json=result.model_dump_json(),
        ))
        await db.commit()
        return result
    except SaveStoreError as exc:
        await db.rollback()
        raise TurnCommitError(exc.status_code, exc.code, exc.message, exc.extra) from exc
    except Exception:
        await db.rollback()
        raise
