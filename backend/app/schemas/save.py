"""
契约层 · 存档
=============
存档的读写分成两种形状，这是刻意的：

    SaveSummary  只有摘要，用来渲染存档列表
    SaveDetail   带完整 payload，只在真正要读档时取

存档正文可能有几 MB（几十回合的完整历史）。如果列表接口也把正文带上，
打开一次侧栏就要传十几 MB —— 手机上尤其难受。

关于 payload 为什么不再是 dict[str, Any]：
    以前它是「随便什么都收」。代价是有人把 gstate 改个名，后端照收 200，
    读档时属性、背包、位置全部静默消失，一句报错都没有。
    存档是玩家几十小时的进度，静默丢失是最不能接受的坏法。
    所以这里把「一份存档至少得有什么」写成机器能验的规则。
"""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# 存档结构版本。改动 payload 的必要字段时 +1，并在 services/save_migration.py
# 里补一条迁移；老存档靠它知道自己是哪一代、该怎么升上来。
SAVE_SCHEMA_VERSION = 2


class SavePayload(BaseModel):
    """
    存档正文的**必要**结构。

    只钉住「少了就不成其为存档」的字段，其余三十来个运行时字段用 extra=allow
    原样透传——它们随版本演进，不值得逐个锁死，锁死了每加一个前端字段
    都要改后端。这条线的位置是刻意选的：宁可管得少而准，不要管得多而假。
    """

    model_config = ConfigDict(extra="allow")

    schema_version: int = Field(
        1, ge=1,
        description="存档结构版本。缺失表示是冻结契约之前写的老存档（视为 1）",
    )
    # history 是游戏本身。没有它就不是存档，只是一坨设置。
    history: list[dict[str, Any]] = Field(..., description="完整对话历史")
    # gstate 是权威角色卡。v2 起必填——正是它被改名时静默丢失过。
    gstate: dict[str, Any] = Field(..., description="权威角色状态")

    world: str = Field("", max_length=64)
    pace: str = Field("long", max_length=20)
    turns: int = Field(0, ge=0)


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
    schema_version: int = SAVE_SCHEMA_VERSION
    # 这次读写为了兼容老结构做了哪些补救。写入和读取两条路都会填，
    # 因为老存档既可能是库里的旧行，也可能是本机镜像刚传上来的。
    migrations: list[str] = Field(default_factory=list)


class SaveDetail(SaveSummary):
    """读档用，带完整正文。"""

    payload: dict[str, Any] = Field(default_factory=dict)
