"""后端配置接口契约。"""
from typing import Literal

from pydantic import BaseModel, Field


class ConfigProvider(BaseModel):
    id: str
    label: str
    configured: bool
    key_hint: str = ""
    note: str = ""


class ConfigResponse(BaseModel):
    providers: list[ConfigProvider]
    default_provider: str


class ConfigUpdate(BaseModel):
    """
    浏览器提交的新配置。

    key 为 None/空字符串时保持原值，避免用户只改默认 provider 时误清空密钥。
    如需清除密钥，使用 clear_* 字段。
    """

    deepseek_api_key: str | None = Field(None, max_length=500)
    zhipu_api_key: str | None = Field(None, max_length=500)
    siliconflow_api_key: str | None = Field(None, max_length=500)
    openrouter_api_key: str | None = Field(None, max_length=500)
    clear_deepseek: bool = False
    clear_zhipu: bool = False
    clear_siliconflow: bool = False
    clear_openrouter: bool = False
    default_provider: Literal["deepseek", "zhipu", "siliconflow", "openrouter", "ollama"] | None = None
