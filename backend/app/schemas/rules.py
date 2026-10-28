"""纯程序规则结算契约。"""
from typing import Any, Literal

from pydantic import BaseModel, Field


class RuleCheckIn(BaseModel):
    action: str = Field("行动检定", max_length=40)
    attr: str = Field("行动", max_length=20)
    attr_value: float = 1
    skill: str = Field("", max_length=60)
    skill_bonus: float = 0
    talent_bonus: float = 0
    dc: int = Field(55, ge=1, le=100)
    die: int | None = Field(None, ge=1, le=100, description="回放时可注入骰面")


class RuleCheckOut(BaseModel):
    action: str
    attr: str
    attr_value: float
    skill: str = ""
    die: int
    total: float
    dc: int
    outcome: str
    success: bool


class RuleActionIn(BaseModel):
    """移动、交易和任务生命周期的程序动作契约。"""

    kind: Literal["move", "trade", "quest"]
    state: dict[str, Any] = Field(default_factory=dict, description="当前权威状态")
    quests: dict[str, list[dict[str, Any]]] = Field(
        default_factory=lambda: {"main": [], "side": []},
        description="当前任务列表，任务动作使用",
    )
    payload: dict[str, Any] = Field(default_factory=dict, description="动作参数")
    known_locations: list[str] = Field(default_factory=list, description="已解锁地点；为空表示不做地点表限制")
    world_id: str = Field("", max_length=40)
    turn: int = Field(0, ge=0)


class RuleActionOut(BaseModel):
    accepted: bool
    kind: Literal["move", "trade", "quest"]
    message: str
    errors: list[str] = Field(default_factory=list)
    patch: dict[str, Any] = Field(default_factory=dict, description="可交给 state/apply 的状态补丁")
    quest_patch: dict[str, list[dict[str, Any]]] = Field(
        default_factory=lambda: {"add": [], "complete": [], "abandon": []},
    )
    effects: dict[str, Any] = Field(default_factory=dict, description="时钟等非 GameState 效果")
