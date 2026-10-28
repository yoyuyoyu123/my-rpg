"""领域层世界包。

公开元数据只有一个权威来源：仓库根目录 ``data/worlds/catalog.json``。
叙事提示词、世界风味和命名约束保留在服务端 ``world_content.py``，不会经
``/api/worlds`` 下发。这样前端卡片、预设和后端校验不会再各维护一份名单。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.domain.world_content import WORLD_CONTENT


CATALOG_SCHEMA_VERSION = 1
CATALOG_PATH = Path(__file__).resolve().parents[3] / "data" / "worlds" / "catalog.json"


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    note: str = ""


@dataclass(frozen=True)
class World:
    id: str
    name: str
    family: str
    skill_label: str
    color: str
    daily: list[str] = field(default_factory=list)
    presets: list[Preset] = field(default_factory=list)
    card_icon: str = ""
    card_description: str = ""
    card_tag: str = ""
    prompt: str = ""
    flavor: str = ""
    naming: str = ""


def _required_text(raw: dict[str, Any], field_name: str, world_id: str) -> str:
    value = str(raw.get(field_name) or "").strip()
    if not value:
        raise RuntimeError(f"世界目录 {world_id!r} 缺少字段 {field_name!r}")
    return value


def _load_worlds() -> dict[str, World]:
    try:
        payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法读取世界目录 {CATALOG_PATH}: {exc}") from exc

    if payload.get("schema_version") != CATALOG_SCHEMA_VERSION:
        raise RuntimeError(
            f"不支持的世界目录版本：{payload.get('schema_version')!r}，"
            f"当前只支持 {CATALOG_SCHEMA_VERSION}"
        )
    rows = payload.get("worlds")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("世界目录 worlds 必须是非空数组")

    worlds: dict[str, World] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            raise RuntimeError("世界目录中的每一项都必须是对象")
        world_id = _required_text(raw, "id", "<unknown>")
        if world_id in worlds:
            raise RuntimeError(f"世界目录存在重复 id：{world_id}")
        private = WORLD_CONTENT.get(world_id)
        if private is None:
            raise RuntimeError(f"世界 {world_id} 缺少服务端私有叙事资产")
        presets_raw = raw.get("presets")
        if not isinstance(presets_raw, list) or not presets_raw:
            raise RuntimeError(f"世界 {world_id} 必须至少有一个预设")
        presets = [
            Preset(
                id=str(item.get("id") or ""),
                name=_required_text(item, "name", world_id),
                note=str(item.get("note") or ""),
            )
            for item in presets_raw
            if isinstance(item, dict)
        ]
        card = raw.get("card") if isinstance(raw.get("card"), dict) else {}
        daily = raw.get("daily")
        if not isinstance(daily, list) or not daily or not all(isinstance(item, str) and item.strip() for item in daily):
            raise RuntimeError(f"世界 {world_id} 的 daily 必须是非空字符串数组")
        worlds[world_id] = World(
            id=world_id,
            name=_required_text(raw, "name", world_id),
            family=_required_text(raw, "family", world_id),
            skill_label=_required_text(raw, "skill_label", world_id),
            color=_required_text(raw, "color", world_id),
            daily=list(daily),
            presets=presets,
            card_icon=_required_text(card, "icon", world_id),
            card_description=_required_text(card, "description", world_id),
            card_tag=_required_text(card, "tag", world_id),
            prompt=_required_text(private, "prompt", world_id),
            flavor=_required_text(private, "flavor", world_id),
            naming=_required_text(private, "naming", world_id),
        )

    extra_private = set(WORLD_CONTENT) - set(worlds)
    if extra_private:
        raise RuntimeError(f"私有叙事资产存在无目录世界：{sorted(extra_private)}")
    return worlds


WORLDS = _load_worlds()
