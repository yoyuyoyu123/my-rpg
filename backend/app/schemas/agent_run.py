"""AgentRun 事件的持久化契约。"""

from typing import Any, Literal

from pydantic import BaseModel, Field


AgentRunStatus = Literal["running", "retrying", "done", "error", "skipped"]


class AgentRunWrite(BaseModel):
    run_id: str = Field(..., min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    parent_id: str = Field("", max_length=64)
    session_id: str = Field("", max_length=40)
    turn_id: int = Field(0, ge=0)
    agent: str = Field("utility", min_length=1, max_length=32)
    title: str = Field("", max_length=160)
    status: AgentRunStatus = "running"
    provider: str = Field("", max_length=40)
    model: str = Field("", max_length=120)
    thinking: bool = False
    input: str = Field("", max_length=40000)
    output: str = Field("", max_length=40000)
    reasoning: str = Field("", max_length=40000)
    error: str = Field("", max_length=6000)
    usage: dict[str, Any] = Field(default_factory=dict)
    stages: list[dict[str, Any]] = Field(default_factory=list, max_length=40)
    meta: dict[str, Any] = Field(default_factory=dict)
    retries: int = Field(0, ge=0, le=100)
    started_at: str = Field("", max_length=40)
    duration_ms: int = Field(0, ge=0)


class AgentRunOut(AgentRunWrite):
    created_at: str = ""
    updated_at: str = ""

