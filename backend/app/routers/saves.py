"""
路由层 · 存档
=============
存档从浏览器的 IndexedDB 搬到服务端。

搬家的理由很具体：IndexedDB 跟设备绑死，电脑上玩到一半、手机打开是空白。
存档在服务端之后，同一个后端下所有设备看到的是同一批进度。

前端仍然保留 IndexedDB 作为降级路径 —— 后端没开时游戏必须照样能玩。
"""
import json
import re
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Save
from app.db.session import get_db
from app.schemas.save import SAVE_SCHEMA_VERSION, SaveDetail, SaveSummary, SaveWrite
from app.services.save_migration import SaveFormatError, migrate_payload, stamp

router = APIRouter(prefix="/api", tags=["存档"])

# 槽位名限制成已知的几种，避免变成任人写入的键值仓库
SLOT_RE = re.compile(r"^(auto|sv_\d{1,2})$")

# 单个存档的上限。几十回合的完整历史大约几 MB，16MB 留足余量，
# 同时挡住「客户端出 bug 无限往里塞」这种情况。
MAX_SAVE_BYTES = 16 * 1024 * 1024


def _check_slot(slot: str) -> str:
    if not SLOT_RE.match(slot):
        raise HTTPException(
            400, detail={"code": "bad_slot", "message": f"槽位名不合法：{slot}"}
        )
    return slot


def _to_summary(s: Save) -> SaveSummary:
    return SaveSummary(
        slot=s.slot, desc=s.desc, world_id=s.world_id, world_name=s.world_name,
        turns=s.turns, client_time=s.client_time, size_bytes=s.size_bytes,
        updated_at=s.updated_at.replace(tzinfo=timezone.utc).isoformat() if s.updated_at else "",
        schema_version=s.schema_version or 1,
    )


@router.get("/saves", response_model=list[SaveSummary], summary="列出所有存档（不含正文）")
async def list_saves(db: AsyncSession = Depends(get_db)) -> list[SaveSummary]:
    """
    只回摘要。存档正文可能有几 MB，渲染一个列表不该把它们全传一遍。
    """
    rows = (await db.execute(select(Save).order_by(Save.updated_at.desc()))).scalars()
    return [_to_summary(s) for s in rows]


@router.get("/saves/{slot}", response_model=SaveDetail, summary="读取一个存档（含正文）")
async def get_save(slot: str, db: AsyncSession = Depends(get_db)) -> SaveDetail:
    _check_slot(slot)
    s = await db.get(Save, slot)
    if s is None:
        raise HTTPException(404, detail={"code": "save_not_found", "message": "存档为空"})

    try:
        payload = json.loads(s.payload_json)
    except json.JSONDecodeError:
        raise HTTPException(
            500, detail={"code": "save_corrupt", "message": "存档内容已损坏，无法解析"}
        ) from None

    # 读的时候升级到当前版本。老存档（没有版本号）尽力抢救并告知玩家；
    # 声明了版本却缺字段的，直接报错——那多半是字段名被改过。
    try:
        payload, notes = migrate_payload(payload)
    except SaveFormatError as exc:
        raise HTTPException(
            422, detail={"code": "save_incompatible", "message": str(exc)}
        ) from exc

    detail = SaveDetail(**_to_summary(s).model_dump(), payload=payload)
    detail.migrations = notes
    return detail


@router.put("/saves/{slot}", response_model=SaveSummary, summary="写入存档（覆盖）")
async def put_save(
    slot: str, req: SaveWrite, db: AsyncSession = Depends(get_db)
) -> SaveSummary:
    _check_slot(slot)
    # 先验再存。以前这里什么都收，于是「改个字段名」会变成几十小时进度
    # 静默消失；现在结构不对当场 422，坏数据进不了库。
    try:
        payload, notes = migrate_payload(req.payload)
    except SaveFormatError as exc:
        raise HTTPException(
            422, detail={"code": "save_invalid", "message": str(exc)}
        ) from exc

    blob = json.dumps(stamp(payload), ensure_ascii=False)
    size = len(blob.encode("utf-8"))
    if size > MAX_SAVE_BYTES:
        raise HTTPException(
            413,
            detail={"code": "save_too_large",
                    "message": f"存档过大（{size // 1024} KB），超过上限"},
        )

    s = await db.get(Save, slot)
    if s is None:
        s = Save(slot=slot)
        db.add(s)

    s.payload_json = blob
    s.schema_version = SAVE_SCHEMA_VERSION
    s.size_bytes = size
    s.desc = req.desc
    s.world_id = req.world_id
    s.world_name = req.world_name
    s.turns = req.turns
    s.client_time = req.client_time

    await db.commit()
    await db.refresh(s)
    summary = _to_summary(s)
    summary.migrations = notes
    return summary


@router.delete("/saves/{slot}", summary="删除存档")
async def delete_save(slot: str, db: AsyncSession = Depends(get_db)) -> dict:
    _check_slot(slot)
    s = await db.get(Save, slot)
    if s is None:
        raise HTTPException(404, detail={"code": "save_not_found", "message": "存档为空"})
    await db.delete(s)
    await db.commit()
    return {"deleted": slot}
