"""
契约层 · 状态结算
=================
模型申报的变化不是事实，只是申报。这个接口把它变成经过规则约束的新状态。
"""
from typing import Any

from pydantic import BaseModel, Field


class StateApplyIn(BaseModel):
    state: dict[str, Any] = Field(..., description="当前权威状态")
    patch: dict[str, Any] = Field(default_factory=dict, description="模型申报的变化")
    world_id: str = Field("", description="用于技能分类的默认标签")
    turn: int = Field(0, ge=0, description="记进账本，方便回溯是哪一回合改的")


class StateApplyOut(BaseModel):
    state: dict[str, Any]
    # 本次新增的账本条目，前端可以直接提示玩家「你获得了什么」
    ledger_added: list[dict[str, Any]] = Field(default_factory=list)
