"""契约层 · 写手后处理与结构化写手输出。"""
from typing import Any

from pydantic import BaseModel, Field, field_validator


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


class StructuredWriterResult(BaseModel):
    """写手可选的结构化信封。

    这不是立即替换旧的纯文本协议：旧模型仍可返回正文加 ``【STATE】``，
    前端会继续兼容。它只是为新写手提供一个稳定的边界，让正文、选项和
    状态候选不必再靠同一段正则猜测。
    """

    narrative: str = Field(default="", description="玩家可见正文")
    options: list[str] = Field(default_factory=list, description="2-4 个眼前行动参考")
    state_patch: dict[str, Any] = Field(default_factory=dict, description="待审计的状态候选")
    memory_writes: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("narrative", mode="before")
    @classmethod
    def normalize_narrative(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("options", mode="before")
    @classmethod
    def normalize_options(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        out: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text and text not in out and len(out) < 4:
                out.append(text[:160])
        return out


class StructuredWriterNormalizeIn(BaseModel):
    raw: str = Field(..., description="模型原始输出")


class StructuredWriterNormalizeOut(StructuredWriterResult):
    structured: bool = Field(default=False, description="是否成功识别结构化信封")
