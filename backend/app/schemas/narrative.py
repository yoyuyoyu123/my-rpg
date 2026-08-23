"""事件、承诺、NPC 知识边界与动态人物状态的 API 契约。"""
from typing import Any, Literal

from pydantic import BaseModel, Field


class EventWrite(BaseModel):
    id: str = Field("", max_length=64)
    kind: str = Field("scene", max_length=32)
    actor: str = Field("", max_length=80)
    action: str = Field("", max_length=500)
    outcome: str = Field("", max_length=900)
    location: str = Field("", max_length=120)
    participants: list[str] = Field(default_factory=list)
    cause_ids: list[str] = Field(default_factory=list)
    visibility: Literal["public", "participants", "private"] = "public"
    source: str = Field("narrative", max_length=20)


class CommitmentWrite(BaseModel):
    id: str = Field("", max_length=64)
    kind: Literal["promise", "refusal", "agreement", "obligation", "boundary"] = "promise"
    owner: str = Field("", max_length=80)
    counterparty: str = Field("", max_length=80)
    text: str = Field(..., max_length=500)
    status: Literal["active", "fulfilled", "rejected", "cancelled", "expired"] = "active"
    hard: bool = False
    due_turn: int | None = Field(default=None, ge=0)
    forbids: list[str] = Field(default_factory=list)
    source_event_id: str = Field("", max_length=64)


class BeliefWrite(BaseModel):
    npc: str = Field(..., max_length=80)
    statement: str = Field(..., max_length=500)
    mode: Literal["knows", "believes", "suspects", "misinformed"] = "knows"
    confidence: int = Field(100, ge=0, le=100)
    source: str = Field("", max_length=100)
    status: Literal["active", "corrected", "forgotten"] = "active"


class CharacterStateWrite(BaseModel):
    name: str = Field(..., max_length=80)
    identity: dict[str, Any] = Field(default_factory=dict)
    mid_term: dict[str, Any] = Field(default_factory=dict)
    short_term: dict[str, Any] = Field(default_factory=dict)
    relationships: dict[str, Any] = Field(default_factory=dict)


class NarrativeLedgerWrite(BaseModel):
    turn: int = Field(..., ge=0)
    events: list[EventWrite] = Field(default_factory=list)
    commitments: list[CommitmentWrite] = Field(default_factory=list)
    beliefs: list[BeliefWrite] = Field(default_factory=list)
    character_states: list[CharacterStateWrite] = Field(default_factory=list)


class NarrativeLedgerResult(BaseModel):
    events_written: int = 0
    commitments_written: int = 0
    beliefs_written: int = 0
    character_states_written: int = 0


class NarrativeLedgerOut(BaseModel):
    events: list[dict[str, Any]] = Field(default_factory=list)
    commitments: list[dict[str, Any]] = Field(default_factory=list)
    beliefs: list[dict[str, Any]] = Field(default_factory=list)
    character_states: list[dict[str, Any]] = Field(default_factory=list)
