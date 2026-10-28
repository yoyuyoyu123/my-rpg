"""存档持久化用例的无提交版本。

路由和 TurnService 共用这里；函数只校验并修改当前 AsyncSession，不自行 commit，
由最外层用例决定事务边界。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Save
from app.schemas.save import SAVE_SCHEMA_VERSION, SaveSummary, SaveWrite
from app.services.save_migration import SaveFormatError, migrate_payload, stamp


SLOT_RE = re.compile(r"^(auto|sv_\d{1,2})$")
MAX_SAVE_BYTES = 16 * 1024 * 1024


@dataclass
class SaveStoreError(Exception):
    status_code: int
    code: str
    message: str
    extra: dict = field(default_factory=dict)

    def detail(self) -> dict:
        return {"code": self.code, "message": self.message, **self.extra}


def validate_slot(slot: str) -> str:
    if not SLOT_RE.match(slot):
        raise SaveStoreError(400, "bad_slot", f"槽位名不合法：{slot}")
    return slot


def to_summary(save: Save) -> SaveSummary:
    return SaveSummary(
        slot=save.slot,
        desc=save.desc,
        world_id=save.world_id,
        world_name=save.world_name,
        turns=save.turns,
        client_time=save.client_time,
        size_bytes=save.size_bytes,
        updated_at=(
            save.updated_at.replace(tzinfo=timezone.utc).isoformat()
            if save.updated_at else ""
        ),
        schema_version=save.schema_version or 1,
        revision=save.revision or 0,
    )


async def prepare_save_write(
    db: AsyncSession, slot: str, req: SaveWrite,
) -> tuple[Save, list[str]]:
    """校验并暂存一次写入，不提交事务。"""
    validate_slot(slot)
    try:
        payload, notes = migrate_payload(req.payload)
    except SaveFormatError as exc:
        raise SaveStoreError(422, "save_invalid", str(exc)) from exc

    blob = json.dumps(stamp(payload), ensure_ascii=False)
    size = len(blob.encode("utf-8"))
    if size > MAX_SAVE_BYTES:
        raise SaveStoreError(
            413,
            "save_too_large",
            f"存档过大（{size // 1024} KB），超过上限",
        )

    save = await db.get(Save, slot)
    if req.base_revision is not None:
        current = (save.revision or 0) if save is not None else 0
        if req.base_revision != current:
            raise SaveStoreError(
                409,
                "save_conflict",
                (
                    f"服务端的存档已经更新到第 {save.turns if save else 0} 回合"
                    f"（版本 {current}），你这边是基于版本 {req.base_revision} 的进度。"
                    "直接覆盖会丢掉另一台设备上的进度"
                ),
                {
                    "current_revision": current,
                    "current_turns": save.turns if save is not None else 0,
                },
            )

    if save is None:
        save = Save(slot=slot)
        db.add(save)
    save.payload_json = blob
    save.schema_version = SAVE_SCHEMA_VERSION
    save.revision = (save.revision or 0) + 1
    save.size_bytes = size
    save.desc = req.desc
    save.world_id = req.world_id
    save.world_name = req.world_name
    save.turns = req.turns
    save.client_time = req.client_time
    return save, notes
