"""Versioned, bounded contracts for speculative generation; no database writes."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.chat import ChatRequest
from app.schemas.turn import TurnContext

Style = Literal["grounded", "dialogue", "lyrical"]
class Preference(BaseModel):
    likes: int = Field(0, ge=0, le=10000)
    dislikes: int = Field(0, ge=0, le=10000)


class Excerpt(BaseModel):
    turn: int = Field(ge=0)
    text: str = Field(max_length=1200)


class Feedback(BaseModel):
    turn: int = Field(ge=0)
    style: Style
    liked: bool


class NovelRuntime(BaseModel):
    version: Literal[1] = 1
    scene_id: str = Field("", max_length=200)
    scene_age: int = Field(0, ge=0, le=100000)
    preferences: dict[Style, Preference] = Field(default_factory=dict, max_length=3)
    excerpts: list[Excerpt] = Field(default_factory=list, max_length=24)
    feedback: list[Feedback] = Field(default_factory=list, max_length=40)
    last: dict = Field(default_factory=dict)


class NovelRequest(ChatRequest):
    mode: Literal["quality", "balanced"] = "quality"
    context: TurnContext
    runtime: NovelRuntime = Field(default_factory=NovelRuntime)

    @field_validator("runtime", "context")
    @classmethod
    def bound_runtime(cls, value):
        if len(value.model_dump_json()) > 500000:
            raise ValueError("游戏回合资料过大")
        return value

    @field_validator("messages")
    @classmethod
    def bound_context(cls, value):
        if len(value) > 600 or sum(len(m.content) for m in value) > 400000:
            raise ValueError("小说模式上下文过大，请先压缩历史")
        return value


class EventNode(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    parent: str = Field("", max_length=40)
    actor: str = Field("world", max_length=80)
    intent: str = Field("", max_length=240)
    evidence: list[str] = Field(default_factory=list, max_length=4)
    perceived: list[str] = Field(default_factory=list, max_length=4)
    development: str = Field(min_length=1, max_length=500)
    reveal: str = Field("", max_length=240)
    duration: int = Field(1, ge=1, le=4)
    mode: Literal["scene", "summary", "pause"] = "scene"
    causal: float = Field(0.5, ge=0, le=1)
    character: float = Field(0.5, ge=0, le=1)
    openness: float = Field(0.5, ge=0, le=1)

    @field_validator("evidence", "perceived")
    @classmethod
    def bound_quotes(cls, values):
        if any(not 2 <= len(v) <= 300 for v in values):
            raise ValueError("证据必须是 2–300 字原文引用")
        return values


class EventPlan(BaseModel):
    nodes: list[EventNode] = Field(min_length=1, max_length=12)


class DraftReview(BaseModel):
    id: int = Field(ge=0, le=2)
    # No defaults: omission cannot accidentally certify a draft as safe.
    agency_ok: bool
    facts_ok: bool
    knowledge_ok: bool
    causal: float = Field(ge=0, le=1)
    character: float = Field(ge=0, le=1)
    prose: float = Field(ge=0, le=1)
    pacing: float = Field(ge=0, le=1)
    issues: list[str] = Field(default_factory=list, max_length=6)
    edit: str = Field("", max_length=800)

    @field_validator("issues")
    @classmethod
    def bound_issues(cls, values):
        if any(len(v) > 400 for v in values):
            raise ValueError("校读说明过长")
        return values


class ReviewSet(BaseModel):
    reviews: list[DraftReview] = Field(min_length=1, max_length=3)
