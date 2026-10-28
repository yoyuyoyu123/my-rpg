"""
路由层 · 会话与记忆
===================
把事实库暴露成 HTTP 接口，让前端能：
    开局 → 每回合写入事实 → 下回合检索注入 → 查看设定档案

设计取舍：为什么是「前端驱动」而不是后端全接管回合？
    现在的回合编排（三次 LLM 调用）还在前端，运转正常。
    与其一次性搬完导致长时间不可玩，不如先让后端提供记忆能力，
    前端逐步把逻辑交出来 —— 每一步都能玩，风险可控。
"""
import uuid
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import Entity, EntityAlias, Fact, Session
from app.db.session import get_db
from app.domain.worlds import WORLDS
from app.schemas.session import (
    ContextOut, ConflictOut, EntityOut, ExtractPromptOut, ExtractRequest,
    ExtractResult, MemoryWrite, MemoryWriteResult, SessionCreate, SessionInfo, RollbackIn, RollbackOut,
)
from app.schemas.narrative import NarrativeLedgerOut, NarrativeLedgerResult, NarrativeLedgerWrite
from app.services.turn_rollback import rollback_to_turn
from app.services.extractor import (
    EXTRACT_MAX_TOKENS, build_prompt, extract_bundle, parse_bundle,
)
from app.services.memory import (
    active_facts, record_fact, resolve_entity, retrieve_context,
    retrieve_context_bundle, upsert_entity,
)
from app.services.narrative_memory import ledger_snapshot, write_ledger

router = APIRouter(prefix="/api", tags=["会话与记忆"])


async def _get_session(db: AsyncSession, sid: str) -> Session:
    s = await db.get(Session, sid)
    if s is None:
        raise HTTPException(404, detail={"code": "session_not_found", "message": "存档不存在"})
    return s


async def _counts(db: AsyncSession, sid: str) -> tuple[int, int]:
    ents = await db.scalar(select(func.count(Entity.id)).where(Entity.session_id == sid))
    facts = await db.scalar(
        select(func.count(Fact.id)).where(Fact.session_id == sid, Fact.superseded_by.is_(None))
    )
    return int(ents or 0), int(facts or 0)


def _to_info(s: Session, ents: int, facts: int) -> SessionInfo:
    world = WORLDS.get(s.world_id)
    return SessionInfo(
        id=s.id, title=s.title, world_id=s.world_id,
        world_name=world.name if world else "",
        preset_id=s.preset_id, pace=s.pace, turn_no=s.turn_no,
        entity_count=ents, fact_count=facts,
        updated_at=s.updated_at.replace(tzinfo=timezone.utc).isoformat() if s.updated_at else "",
    )


# ── 会话 ────────────────────────────────────────────────────────

@router.post("/sessions", response_model=SessionInfo, summary="开一局新游戏")
async def create_session(req: SessionCreate, db: AsyncSession = Depends(get_db)) -> SessionInfo:
    if req.world_id not in WORLDS and req.world_id != "__custom__":
        raise HTTPException(400, detail={"code": "unknown_world", "message": f"没有这个世界观：{req.world_id}"})

    world = WORLDS.get(req.world_id)
    sid = uuid.uuid4().hex[:16]
    s = Session(
        id=sid,
        title=req.title or (f"{world.name}·新局" if world else "新局"),
        world_id=req.world_id, preset_id=req.preset_id, pace=req.pace,
    )
    db.add(s)
    await db.commit()
    return _to_info(s, 0, 0)


@router.get("/sessions", response_model=list[SessionInfo], summary="列出所有存档")
async def list_sessions(db: AsyncSession = Depends(get_db)) -> list[SessionInfo]:
    rows = (await db.execute(select(Session).order_by(Session.updated_at.desc()))).scalars()
    out = []
    for s in rows:
        e, f = await _counts(db, s.id)
        out.append(_to_info(s, e, f))
    return out


@router.get("/sessions/{sid}", response_model=SessionInfo, summary="读取一个存档")
async def get_session(sid: str, db: AsyncSession = Depends(get_db)) -> SessionInfo:
    s = await _get_session(db, sid)
    e, f = await _counts(db, sid)
    return _to_info(s, e, f)


@router.delete("/sessions/{sid}", summary="删除存档")
async def delete_session(sid: str, db: AsyncSession = Depends(get_db)) -> dict:
    s = await _get_session(db, sid)
    await db.delete(s)
    await db.commit()
    return {"deleted": sid}


# ── 记忆写入与检索 ──────────────────────────────────────────────


async def _write_memory_uncommitted(
    sid: str, req: MemoryWrite, db: AsyncSession,
) -> MemoryWriteResult:
    """写入事实但不提交；由最外层用例决定整个工作单元何时 commit。"""
    s = await _get_session(db, sid)
    written, conflicts = 0, []

    for ent_in in req.entities:
        entity = await upsert_entity(
            db, sid, name=ent_in.name, kind=ent_in.kind, turn=req.turn,
            aliases=ent_in.aliases, importance=ent_in.importance,
        )
        for fact_in in ent_in.facts:
            fact, conflict = await record_fact(
                db, sid, entity, key=fact_in.key, value=fact_in.value,
                turn=req.turn, source=req.source,
            )
            if fact:
                written += 1
            if conflict:
                conflicts.append(ConflictOut(
                    entity=conflict.entity_name, key=conflict.key,
                    old_value=conflict.old_value, new_value=conflict.new_value,
                    old_turn=conflict.old_turn, description=conflict.describe(),
                ))

    s.turn_no = max(s.turn_no, req.turn)
    return MemoryWriteResult(
        entities_touched=len(req.entities), facts_written=written, conflicts=conflicts,
    )


@router.post("/sessions/{sid}/memory", response_model=MemoryWriteResult,
             summary="写入事实（含矛盾检测）")
async def write_memory(
    sid: str, req: MemoryWrite, db: AsyncSession = Depends(get_db)
) -> MemoryWriteResult:
    """
    写入一批事实。稳定属性被改写时会拦截并返回冲突，**不写入**。

    前端拿到 conflicts 后可以：
      - 展示给玩家，让玩家裁决
      - 或塞进下一回合的提示词，要求 AI 自己纠正
    """
    result = await _write_memory_uncommitted(sid, req, db)
    await db.commit()
    return result


@router.post("/sessions/{sid}/extract", response_model=MemoryWriteResult,
             summary="从叙事自动抽取事实并写入")
async def extract_and_store(
    sid: str, req: ExtractRequest,
    db: AsyncSession = Depends(get_db), settings: Settings = Depends(get_settings),
) -> MemoryWriteResult:
    """
    一步到位：调模型抽取 → 清洗 → 写入 → 返回冲突。

    前端在渲染完叙事之后调这个（不阻塞玩家阅读）。
    抽取失败返回空结果，不报错——记不住东西不该让玩家的回合失败。
    """
    await _get_session(db, sid)
    known, known_facts = await _known_memory(db, sid)

    bundle = await extract_bundle(
        settings=settings, provider_id=req.provider, model=req.model,
        narrative=req.narrative, player_input=req.player_input,
        known_names=known, known_facts=known_facts,
    )
    return await _store_extracted(sid, req.turn, bundle, db)


@router.post("/sessions/{sid}/extract/prompt", response_model=ExtractPromptOut,
             summary="出一道抽取题（前端自带凭据时用）")
async def extract_prompt(
    sid: str, req: ExtractRequest, db: AsyncSession = Depends(get_db)
) -> ExtractPromptOut:
    """
    直连模式下 API key 在浏览器手里，后端调不动模型。
    于是拆成两步：后端出题 → 前端跑模型 → 后端阅卷（/extract/result）。

    词表和清洗规则始终只有后端这一份，前端只是个传话的。
    """
    await _get_session(db, sid)
    known, known_facts = await _known_memory(db, sid)
    return ExtractPromptOut(
        prompt=build_prompt(
            req.narrative, req.player_input, known, known_facts=known_facts,
        ),
        temperature=0.2,
        max_tokens=EXTRACT_MAX_TOKENS,
    )


@router.post("/sessions/{sid}/extract/result", response_model=MemoryWriteResult,
             summary="交卷：把模型原始输出解析入库")
async def extract_result(
    sid: str, req: ExtractResult, db: AsyncSession = Depends(get_db)
) -> MemoryWriteResult:
    await _get_session(db, sid)
    return await _store_extracted(sid, req.turn, parse_bundle(req.raw), db)


async def _known_names(db: AsyncSession, sid: str) -> list[str]:
    """已登记的实体名，喂给抽取模型，让它复用同一个名字而不是造新的。"""
    return list(
        (await db.execute(
            select(Entity.canonical_name)
            .where(Entity.session_id == sid)
            .order_by(Entity.importance.desc(), Entity.last_seen_turn.desc())
            .limit(40)
        )).scalars()
    )


async def _known_memory(db: AsyncSession, sid: str) -> tuple[list[str], str]:
    """把名字和当前事实一起交给抽取器，避免它每回合重抄旧设定。"""
    names = await _known_names(db, sid)
    facts = await retrieve_context(
        db, sid, mentioned=names, max_entities=40, max_facts_each=12,
    )
    return names, facts


async def _store_extracted(
    sid: str, turn: int, bundle: dict[str, list[dict]], db: AsyncSession
) -> MemoryWriteResult:
    try:
        entities = bundle.get("entities") or []
        base = MemoryWriteResult()
        if entities:
            payload = MemoryWrite(
                turn=turn, source="narrative",
                entities=[  # type: ignore[arg-type]
                    {"name": e["name"], "kind": e["kind"], "aliases": e["aliases"],
                     "importance": e["importance"], "facts": e["facts"]}
                    for e in entities
                ],
            )
            base = await _write_memory_uncommitted(sid, payload, db)

        ledger = NarrativeLedgerWrite(
            turn=turn,
            events=bundle.get("events") or [],
            commitments=bundle.get("commitments") or [],
            beliefs=bundle.get("beliefs") or [],
            character_states=bundle.get("character_states") or [],
        )
        counts = await write_ledger(db, sid, ledger)
        s = await _get_session(db, sid)
        s.turn_no = max(s.turn_no, turn)
        await db.commit()
        return MemoryWriteResult(
            entities_touched=base.entities_touched,
            facts_written=base.facts_written,
            conflicts=base.conflicts,
            **counts,
        )
    except Exception:
        # 事实、实体、事件、承诺和人物状态属于同一个抽取批次；任何一步失败
        # 都不能把半个回合留在数据库里。
        await db.rollback()
        raise


@router.post("/sessions/{sid}/ledger", response_model=NarrativeLedgerResult,
             summary="写入事件、承诺、NPC知识与人物动态状态")
async def write_narrative_ledger(
    sid: str, req: NarrativeLedgerWrite, db: AsyncSession = Depends(get_db),
) -> NarrativeLedgerResult:
    s = await _get_session(db, sid)
    counts = await write_ledger(db, sid, req)
    s.turn_no = max(s.turn_no, req.turn)
    await db.commit()
    return NarrativeLedgerResult(**counts)


@router.get("/sessions/{sid}/ledger", response_model=NarrativeLedgerOut,
            summary="读取结构化叙事账本")
async def get_narrative_ledger(
    sid: str, limit: int = 30, db: AsyncSession = Depends(get_db),
) -> NarrativeLedgerOut:
    await _get_session(db, sid)
    return NarrativeLedgerOut(**await ledger_snapshot(db, sid, max(1, min(100, limit))))


@router.get("/sessions/{sid}/context", response_model=ContextOut,
            summary="检索本回合该注入的设定")
async def get_context(
    sid: str, mentioned: str = "", turn: int = 0, speaker: str = "",
    db: AsyncSession = Depends(get_db),
) -> ContextOut:
    """
    前端在组装提示词前调这个，把返回的 text 拼进 system prompt。

    mentioned 传本回合提到的名字（逗号分隔），用于精准检索。
    """
    await _get_session(db, sid)
    names = [n.strip() for n in mentioned.split(",") if n.strip()]
    bundle = await retrieve_context_bundle(
        db, sid, mentioned=names, current_turn=max(0, turn), speaker=speaker.strip(),
    )

    roster = list((await db.execute(
        select(Entity.canonical_name).where(Entity.session_id == sid)
    )).scalars())
    roster += list((await db.execute(
        select(EntityAlias.alias).where(EntityAlias.session_id == sid)
    )).scalars())

    return ContextOut(
        text=bundle.text, entity_count=bundle.entity_count, names=roster,
        trace=bundle.trace, **bundle.counts,
    )


@router.get("/sessions/{sid}/entities", response_model=list[EntityOut],
            summary="查看全部设定档案")
async def list_entities(sid: str, db: AsyncSession = Depends(get_db)) -> list[EntityOut]:
    """给前端做「设定档案」面板用——玩家能看到程序记住了什么。"""
    await _get_session(db, sid)
    rows = (await db.execute(
        select(Entity).where(Entity.session_id == sid)
        .order_by(Entity.importance.desc(), Entity.last_seen_turn.desc())
    )).scalars()

    out = []
    for e in rows:
        aliases = list((await db.execute(
            select(EntityAlias.alias).where(EntityAlias.entity_id == e.id)
        )).scalars())
        facts = await active_facts(db, e.id)
        out.append(EntityOut(
            id=e.id, kind=e.kind, name=e.canonical_name, aliases=aliases,
            importance=e.importance, first_turn=e.first_turn, last_seen_turn=e.last_seen_turn,
            facts=[{"key": f.key, "value": f.value, "stability": f.stability, "turn": f.turn}
                   for f in facts],
        ))
    return out


@router.delete("/sessions/{sid}/entities/{eid}", summary="删除一个实体及其事实")
async def delete_entity(sid: str, eid: int, db: AsyncSession = Depends(get_db)) -> dict:
    """玩家发现程序记错了，可以手动清掉——最终解释权归玩家。"""
    await _get_session(db, sid)
    ent = await db.get(Entity, eid)
    if ent is None or ent.session_id != sid:
        raise HTTPException(404, detail={"code": "entity_not_found", "message": "实体不存在"})
    await db.delete(ent)
    await db.commit()
    return {"deleted": eid}


@router.post("/sessions/{sid}/rollback", response_model=RollbackOut,
             summary="丢弃某回合及其之后的叙事记录")
async def rollback(
    sid: str, req: RollbackIn, db: AsyncSession = Depends(get_db)
) -> RollbackOut:
    """
    玩家撤销或重写回合时调用。

    不这么做的话，被丢弃那版确立的设定会留在库里：既会注入下一回合的
    提示词，还会把重写出来的新版本当成矛盾拦下来——矛盾检测反过来
    强制执行玩家已经否决的内容。
    """
    s = await _get_session(db, sid)
    removed = await rollback_to_turn(db, sid, req.from_turn)
    s.turn_no = min(s.turn_no, max(0, req.from_turn - 1))
    await db.commit()
    return RollbackOut(**removed)
