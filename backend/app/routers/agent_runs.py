"""AgentRun 的轻量持久化与查询接口。"""

from __future__ import annotations

import json
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRun, Session
from app.db.session import get_db
from app.schemas.agent_run import AgentRunOut, AgentRunStatus, AgentRunWrite


router = APIRouter(prefix="/api", tags=["Agent 监视器"])


def _iso(value) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat() if value else ""


def _out(row: AgentRun) -> AgentRunOut:
    def load(raw: str, fallback):
        try:
            value = json.loads(raw or "")
            return value if isinstance(value, type(fallback)) else fallback
        except (TypeError, ValueError):
            return fallback

    return AgentRunOut(
        run_id=row.run_id,
        parent_id=row.parent_id or "",
        session_id=row.session_id or "",
        turn_id=row.turn_no or 0,
        agent=row.agent,
        title=row.title,
        status=row.status,
        provider=row.provider,
        model=row.model,
        thinking=bool(row.thinking),
        input=row.input_text,
        output=row.output_text,
        reasoning=row.reasoning_text,
        error=row.error_text,
        usage=load(row.usage_json, {}),
        stages=load(row.stages_json, []),
        meta=load(row.meta_json, {}),
        retries=row.retries or 0,
        started_at=row.started_at,
        duration_ms=row.duration_ms or 0,
        created_at=_iso(row.created_at),
        updated_at=_iso(row.updated_at),
    )


async def _require_session(db: AsyncSession, session_id: str) -> None:
    if not session_id:
        return
    if await db.get(Session, session_id) is None:
        raise HTTPException(status_code=404, detail="会话不存在")


@router.post("/agent-runs", response_model=AgentRunOut, summary="写入或更新 AgentRun")
async def write_agent_run(
    body: AgentRunWrite,
    db: AsyncSession = Depends(get_db),
) -> AgentRunOut:
    await _require_session(db, body.session_id)
    row = await db.get(AgentRun, body.run_id)
    if row is not None:
        if (row.session_id or "") != body.session_id or row.turn_no != body.turn_id:
            raise HTTPException(status_code=409, detail="run_id 已绑定到其它会话或回合")
    else:
        row = AgentRun(run_id=body.run_id)
        db.add(row)

    row.session_id = body.session_id or None
    row.parent_id = body.parent_id
    row.turn_no = body.turn_id
    row.agent = body.agent
    row.title = body.title
    row.status = body.status
    row.provider = body.provider
    row.model = body.model
    row.thinking = body.thinking
    row.input_text = body.input
    row.output_text = body.output
    row.reasoning_text = body.reasoning
    row.error_text = body.error
    row.usage_json = json.dumps(body.usage, ensure_ascii=False)
    row.stages_json = json.dumps(body.stages, ensure_ascii=False)
    row.meta_json = json.dumps(body.meta, ensure_ascii=False)
    row.retries = body.retries
    row.started_at = body.started_at
    row.duration_ms = body.duration_ms
    await db.commit()
    await db.refresh(row)
    return _out(row)


@router.get(
    "/sessions/{session_id}/agent-runs",
    response_model=list[AgentRunOut],
    summary="查询会话的 AgentRun",
)
async def list_agent_runs(
    session_id: str,
    turn_id: int | None = Query(default=None, ge=0),
    agent: str | None = Query(default=None, min_length=1, max_length=32),
    status: AgentRunStatus | None = Query(default=None),
    offset: int = Query(default=0, ge=0, le=100_000),
    limit: int = Query(default=80, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[AgentRunOut]:
    await _require_session(db, session_id)
    stmt = select(AgentRun).where(AgentRun.session_id == session_id)
    if turn_id is not None:
        stmt = stmt.where(AgentRun.turn_no == turn_id)
    if agent is not None:
        stmt = stmt.where(AgentRun.agent == agent)
    if status is not None:
        stmt = stmt.where(AgentRun.status == status)
    stmt = stmt.order_by(AgentRun.started_at.desc(), AgentRun.created_at.desc()).offset(offset).limit(limit)
    rows = (await db.scalars(stmt)).all()
    return [_out(row) for row in rows]


@router.get("/agent-runs/{run_id}", response_model=AgentRunOut, summary="查询单个 AgentRun")
async def get_agent_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> AgentRunOut:
    row = await db.get(AgentRun, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="AgentRun 不存在")
    return _out(row)
