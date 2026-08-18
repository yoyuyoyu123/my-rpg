"""
路由层 · 世界观目录
===================
前端渲染「选择世界」页需要的数据。

关键：**只返回展示用的字段，不返回 prompt**。
提示词是核心资产，留在服务端。这是「最小暴露原则」的直接体现。
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.domain.worlds import WORLDS

router = APIRouter(prefix="/api", tags=["世界观"])


class PresetOut(BaseModel):
    id: str
    name: str


class WorldOut(BaseModel):
    id: str
    name: str
    family: str
    skill_label: str
    daily: list[str] = Field(default_factory=list)
    presets: list[PresetOut] = Field(default_factory=list)
    # 注意这里没有 prompt 字段——它不下发


@router.get("/worlds", response_model=list[WorldOut], summary="列出世界观")
def list_worlds() -> list[WorldOut]:
    return [
        WorldOut(
            id=w.id, name=w.name, family=w.family, skill_label=w.skill_label,
            daily=list(w.daily),
            presets=[PresetOut(id=p.id, name=p.name) for p in w.presets],
        )
        for w in WORLDS.values()
    ]
