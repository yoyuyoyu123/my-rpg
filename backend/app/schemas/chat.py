"""
契约层 · 对话代理
=================
职责：定义前端和后端之间「说什么话」。

这一层是整个前后端分离的核心。写清楚了，前端不用猜后端要什么，
后端也不用防着前端乱传——Pydantic 会在数据进门时就挡住不合法的请求。

命名遵循 OpenAI 的约定（role/content/messages），
因为前端现在就是这么组织数据的，迁移成本最低。
"""
from typing import Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    """一条对话消息。"""

    role: Literal["system", "user", "assistant"] = Field(
        ..., description="谁说的：system=规则，user=玩家，assistant=AI"
    )
    content: str = Field(..., description="消息正文")


class ChatRequest(BaseModel):
    """
    前端发起一次 LLM 调用的请求。

    注意这里【没有】api_key 字段——这正是重点：
    key 由服务端从环境变量读取，前端根本不经手。
    """

    messages: list[Message] = Field(..., min_length=1, description="对话消息列表")
    provider: str = Field("deepseek", description="用哪个后端，见 /api/providers")
    model: str = Field("", description="模型 ID。留空则用该后端的默认模型")

    # 生成参数。给上下限是为了防止前端传出离谱的值把账单打爆。
    temperature: float = Field(0.85, ge=0.0, le=2.0, description="随机性")
    max_tokens: int = Field(4096, ge=1, le=32000, description="最大输出长度")
    stream: bool = Field(False, description="是否流式返回")


class Usage(BaseModel):
    """本次调用的 token 消耗。用于前端显示和成本统计。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    """一次非流式调用的结果。"""

    content: str = Field(..., description="模型输出的正文")
    provider: str = Field(..., description="实际使用的后端")
    model: str = Field(..., description="实际使用的模型")
    usage: Usage = Field(default_factory=Usage)
    retries: int = Field(0, description="本次调用重试了几次（0 表示一次成功）")


class ProviderInfo(BaseModel):
    """一个可用后端的信息，供前端渲染选择列表。"""

    id: str
    label: str
    default_model: str
    configured: bool = Field(..., description="服务端是否已配置该后端的 key")
    note: str = ""


class ErrorDetail(BaseModel):
    """
    统一的错误响应体。

    为什么要统一：前端只需要写一套错误处理逻辑，
    而不是对每个接口猜返回格式。
    """

    code: str = Field(..., description="机器可读的错误码，如 provider_not_configured")
    message: str = Field(..., description="给人看的说明")
    retryable: bool = Field(False, description="前端要不要提示用户稍后再试")
