"""契约层 · 写手后处理。"""
from pydantic import BaseModel, Field


class AgencyGuardIn(BaseModel):
    codes: list[str] = Field(default_factory=list, description="检测到的越权类型")


class AgencyGuardOut(BaseModel):
    guard: str
    max_tokens: int = 4096


class OptionRepairIn(BaseModel):
    draft: str = Field(..., description="写手交的稿；后端自己剥隐藏块")
    player_input: str = Field("", description="玩家上一条输入")


class OptionRepairOut(BaseModel):
    prompt: str
    temperature: float = 0.35
    max_tokens: int = 260
