"""已完成回合的服务端提交契约。"""
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.narrative import NarrativeLedgerResult, NarrativeLedgerWrite
from app.schemas.save import SaveSummary, SaveWrite


class TurnCommitRequest(BaseModel):
    commit_id: str = Field(..., min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    ledger: NarrativeLedgerWrite
    save_slot: Literal["auto"] = "auto"
    save: SaveWrite


class TurnCommitResult(BaseModel):
    commit_id: str
    turn: int
    replayed: bool = False
    ledger: NarrativeLedgerResult
    save: SaveSummary
