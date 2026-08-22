"""契约层 · GM 裁定。"""
from typing import Any

from pydantic import BaseModel, Field


class DirectorPromptIn(BaseModel):
    """出一道裁定题所需要的运行时状态。"""

    player_input: str = Field(..., description="玩家这一回合的输入")
    game_state: dict[str, Any] = Field(default_factory=dict)
    story_tone: str = Field("", description="本局基调")
    story_dna: str = Field("", description="本局最终有效设定")
    outline: str = Field("", description="隐藏大纲")
    player_canon: dict[str, str] = Field(default_factory=dict)
    premise_state: dict[str, Any] = Field(default_factory=dict)
    prefs: dict[str, Any] = Field(default_factory=dict)
    recent_messages: list[dict[str, Any]] = Field(
        default_factory=list, description="最近几条对话，后端自己截取与剥离协议块",
    )


class DirectorPromptOut(BaseModel):
    prompt: str
    temperature: float = 0.3
    max_tokens: int = 350


class DirectorResultIn(BaseModel):
    raw: str = Field(..., description="模型原始输出")


class DirectorResultOut(BaseModel):
    # None 表示裁定没能完成，调用方按「本回合不做额外裁定」处理
    ruling: dict[str, Any] | None = None
    ok: bool = True
