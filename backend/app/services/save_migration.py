"""
服务层 · 存档迁移
=================
「冻结契约」不等于「永远不改」。它的意思是：

    1. 约定写成代码，让机器帮你验，而不是靠人记得；
    2. 要改就走版本，老数据有明确的升级路径；
    3. 不能悄悄改——改坏了必须有人立刻知道。

这个文件管第 2 条和第 3 条。

为什么严格程度分两档：
    没有 schema_version 的存档是冻结契约之前写的，它们的字段本来就没保证，
    该尽力抢救——玩家的几十小时进度不该因为我们后来定了规矩就打不开。
    而声明了版本的存档是新规矩下写的，缺字段就是真出了问题（比如有人
    重构时改了字段名），必须当场报错，绝不能默默补个空值蒙混过去。
"""
from typing import Any

from app.schemas.save import SAVE_SCHEMA_VERSION, SavePayload
from pydantic import ValidationError


class SaveFormatError(Exception):
    """存档结构不合法，且不属于可以自动抢救的情况。"""


def _v1_to_v2(payload: dict[str, Any], notes: list[str]) -> dict[str, Any]:
    """
    v1（无版本号）→ v2。

    v1 本身没有结构保证，所以这一步只做兜底补齐，让老存档能继续打开。
    真实的老存档基本都带着这些字段，补齐分支平时不会触发。
    """
    if not isinstance(payload.get("gstate"), dict):
        payload["gstate"] = {}
        notes.append("老存档缺少角色状态，已补空白角色卡；数值需要手动校准")
    if not isinstance(payload.get("history"), list):
        payload["history"] = []
        notes.append("老存档缺少对话历史，已补空历史")
    return payload


# 版本 N → N+1 的迁移表。加新版本时在这里追加一条，别去改老的。
_MIGRATIONS = {1: _v1_to_v2}


def migrate_payload(raw: Any) -> tuple[dict[str, Any], list[str]]:
    """
    把任意一份存档正文升到当前版本并校验。

    返回 (升级后的正文, 做过哪些补救)。补救记录会回传给前端，
    让玩家知道自己的老存档被动过什么，而不是莫名其妙少了东西。
    """
    if not isinstance(raw, dict):
        raise SaveFormatError("存档正文不是一个对象")

    payload = dict(raw)
    notes: list[str] = []

    try:
        version = int(payload.get("schema_version") or 1)
    except (TypeError, ValueError):
        version = 1
    declared = "schema_version" in raw

    if version > SAVE_SCHEMA_VERSION:
        raise SaveFormatError(
            f"存档版本 {version} 比当前程序（{SAVE_SCHEMA_VERSION}）更新，"
            "请升级后再打开，直接读取可能丢数据"
        )

    while version < SAVE_SCHEMA_VERSION:
        step = _MIGRATIONS.get(version)
        if step is None:
            raise SaveFormatError(f"没有从版本 {version} 升级的路径")
        payload = step(payload, notes)
        version += 1
        payload["schema_version"] = version

    payload["schema_version"] = SAVE_SCHEMA_VERSION

    try:
        SavePayload.model_validate(payload)
    except ValidationError as exc:
        missing = "、".join(
            ".".join(str(x) for x in e["loc"]) for e in exc.errors()[:5]
        )
        if declared:
            # 声明了版本却缺必要字段——多半是有人改了字段名。
            # 这正是以前会静默丢进度的那条路，现在把它变成硬错误。
            raise SaveFormatError(
                f"存档缺少必要字段：{missing}。"
                "若刚改过存档字段名，请同时更新 schema 与迁移"
            ) from exc
        raise SaveFormatError(f"老存档无法修复：缺少 {missing}") from exc

    return payload, notes


def stamp(payload: dict[str, Any]) -> dict[str, Any]:
    """给一份新写入的正文盖上当前版本号。"""
    out = dict(payload)
    out["schema_version"] = SAVE_SCHEMA_VERSION
    return out
