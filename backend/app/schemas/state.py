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


class AuditPromptIn(BaseModel):
    """出一道状态审计题。"""

    before: dict[str, Any] = Field(..., description="回合前的权威状态")
    player_input: str = Field("", description="玩家这一回合做了什么")
    reply: str = Field("", description="本回合叙事正文")
    declared: list[dict[str, Any]] = Field(
        default_factory=list, description="叙事模型自己申报的补丁，只作候选",
    )


class AuditPromptOut(BaseModel):
    prompt: str
    temperature: float = 0.1
    max_tokens: int = 400


class AuditResultIn(BaseModel):
    """交卷：模型原始输出，由后端解析清洗。"""

    raw: str = Field(..., description="模型原始输出")


class AuditResultOut(BaseModel):
    # None 表示审计没能完成——调用方必须据此不结算，
    # 而不是退回去用叙事模型的申报（那正是审计要核对的对象）。
    # {} 表示审计确认没有变化，是有效结论。两者含义不同，不能混。
    patch: dict[str, Any] | None = None
    ok: bool = True
