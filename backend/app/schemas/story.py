"""结构化剧情规划契约。

规划器不写正文，只维护一个短期可执行的故事状态；叙事模型只会看到
``current_scene`` 的公开部分，不能偷看幕后原因，也不能擅自扩写整条主线。
"""
from typing import Any, Literal

from pydantic import BaseModel, Field


class NarrativeBeat(BaseModel):
    id: str = ""
    label: str = ""
    purpose: str = ""
    prerequisites: list[str] = Field(default_factory=list)
    setup: list[str] = Field(default_factory=list)
    activation_condition: str = ""
    status: Literal["dormant", "available", "active", "resolved", "abandoned"] = "dormant"


class StoryThread(BaseModel):
    id: str = ""
    title: str = ""
    kind: str = ""
    public_goal: str = ""
    private_cause: str = ""
    why_now: str = ""
    player_connection: str = ""
    established_clues: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    beats: list[NarrativeBeat] = Field(default_factory=list)
    status: Literal["dormant", "active", "paused", "resolved", "abandoned"] = "active"


class SceneCard(BaseModel):
    id: str = ""
    title: str = ""
    situation: str = ""
    purpose: str = ""
    causal_bridge: str = ""
    active_thread_ids: list[str] = Field(default_factory=list)
    participant_intents: dict[str, str] = Field(default_factory=dict)
    available_information: list[str] = Field(default_factory=list)
    allowed_developments: list[str] = Field(default_factory=list)
    stop_points: list[str] = Field(default_factory=list)
    refresh_after_turn: int = 0
    premise_phase: int | None = Field(default=None, ge=0, le=5)
    status: Literal["active", "resolved"] = "active"


class StoryRuntime(BaseModel):
    version: int = 1
    revision: int = 1
    premise: str = ""
    threads: list[StoryThread] = Field(default_factory=list)
    current_scene: SceneCard | None = None
    last_planned_turn: int = 0
    plan_reason: str = "opening"


class StoryPlanContext(BaseModel):
    world_id: str
    preset_id: str = ""
    pace: str = "long"
    turn: int = Field(0, ge=0)
    reason: Literal["opening", "scene_boundary", "horizon", "manual"] = "opening"
    custom_world_prompt: str = ""
    story_dna: str = ""
    opening_text: str = ""
    locked_tags: list[str] = Field(default_factory=list)
    inspiration_tags: list[str] = Field(default_factory=list)
    game_state: dict[str, Any] = Field(default_factory=dict)
    player_canon: dict[str, str] = Field(default_factory=dict)
    premise_state: dict[str, Any] = Field(default_factory=dict)
    prefs: dict[str, Any] = Field(default_factory=dict)
    lore_context: str = ""
    story_runtime: dict[str, Any] = Field(default_factory=dict)
    recent_messages: list[dict[str, str]] = Field(default_factory=list)


class StoryPlanPromptOut(BaseModel):
    prompt: str
    max_tokens: int = 2400
    temperature: float = 0.55


class StoryPlanResultIn(BaseModel):
    raw: str
    previous_runtime: dict[str, Any] = Field(default_factory=dict)
    turn: int = Field(0, ge=0)
    reason: str = "opening"


class StoryPlanResultOut(BaseModel):
    runtime: StoryRuntime
    warnings: list[str] = Field(default_factory=list)
