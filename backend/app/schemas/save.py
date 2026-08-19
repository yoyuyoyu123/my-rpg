"""
契约层 · 存档
=============
存档的读写分成两种形状，这是刻意的：

    SaveSummary  只有摘要，用来渲染存档列表
    SaveDetail   带完整 payload，只在真正要读档时取

存档正文可能有几 MB（几十回合的完整历史）。如果列表接口也把正文带上，
打开一次侧栏就要传十几 MB —— 手机上尤其难受。
"""
from typing import Any

from pydantic import BaseModel, Field


class SaveWrite(BaseModel):
    """写入一个存档槽。摘要字段由客户端提供，因为只有它知道怎么描述当前进度。"""

    payload: dict[str, Any] = Field(..., description="完整运行时快照")
    desc: str = Field("", max_length=200)
    world_id: str = Field("", max_length=40)
    world_name: str = Field("", max_length=60)
    turns: int = Field(0, ge=0)
    client_time: str = Field("", max_length=40, description="客户端本地时间的展示字符串")


class SaveSummary(BaseModel):
    """存档列表用的摘要，不含正文。"""

    slot: str
    desc: str = ""
    world_id: str = ""
    world_name: str = ""
    turns: int = 0
    client_time: str = ""
    size_bytes: int = 0
    updated_at: str = ""


class SaveDetail(SaveSummary):
    """读档用，带完整正文。"""

    payload: dict[str, Any] = Field(default_factory=dict)
