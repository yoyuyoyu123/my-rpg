"""
契约层 · 回合
=============
前端每回合把「运行时状态」交上来，后端编译出 system prompt。

这里划的那条线值得说清楚：
    资产（规则常量、世界包正文、状态协议、篇幅说明）留在后端，请求里没有；
    运行时（角色状态、锁定设定、大纲、命名表、世界书）由前端提供。

所以这个契约里看不到任何提示词正文——它们不该往返于网络。
"""
from typing import Any

from pydantic import BaseModel, Field


class TurnContext(BaseModel):
    """编译一回合提示词所需要的全部运行时状态。"""

    # ── 本局配置 ────────────────────────────────────────────────
    world_id: str = Field(..., description="世界观 id；自定义世界传 __custom__")
    preset_id: str = Field("", description="特色预设 id")
    pace: str = Field("long", description="篇幅：short/medium/long")
    turns: int = Field(0, ge=0, description="已进行的回合数；0 表示开局")

    # 自定义世界的设定正文由玩家自己写，只能随请求带上
    custom_world_prompt: str = Field("", description="仅 world_id=__custom__ 时使用")
    locked_tags: list[str] = Field(default_factory=list)
    inspiration_tags: list[str] = Field(default_factory=list)

    # ── 开局时抽定、之后固定的本局设定 ──────────────────────────
    story_dna: str = Field("", description="本局最终有效设定")
    opening_text: str = Field("", description="开局变体说明，仅第 0 回合使用")

    # ── 随剧情增长的运行时状态 ──────────────────────────────────
    game_state: dict[str, Any] = Field(default_factory=dict, description="权威角色卡")
    player_canon: dict[str, str] = Field(default_factory=dict, description="主角身份档案")
    premise_state: dict[str, Any] = Field(default_factory=dict, description="跨世界迁移阶段")
    story_runtime: dict[str, Any] = Field(default_factory=dict, description="规划 Agent 的结构化剧情与当前场景")
    prefs: dict[str, Any] = Field(default_factory=dict, description="玩家口味与硬性备注")

    outline: str = Field("", description="隐藏大纲")
    names: str = Field("", description="命名表")
    pins: list[dict[str, Any]] = Field(default_factory=list, description="锁定设定")
    lorebook: list[dict[str, Any]] = Field(default_factory=list, description="世界书条目")

    lore_context: str = Field("", description="事实库检索结果，由 /sessions/{id}/context 得来")
    recent_text: str = Field("", description="本回合相关文本，用于世界书关键词检索")


class TurnPromptOut(BaseModel):
    """编译结果。"""

    system_prompt: str
    # 程序接管本幕时的强制令。前端把它追加到每回合指令的**最后面**，
    # 因为默认那句「只完成玩家明确行动、在决策边界前停下」会把强制事件
    # 吃掉——实测穿越就是这样被推迟一回合的。空串表示本回合无强制。
    turn_mandate: str = ""
    chars: int = 0
    # 前端把它写进调试追踪，用来确认两回合之间提示词是否真的变了
    hash: str = ""

    # 本回合实际挂载了哪几个规则包。前端调试面板要显示这个，
    # 由后端一并回传，省得前端再抄一份映射表——抄了就会漂移。
    rule_packs: list[str] = Field(default_factory=list)
    rules_hash: str = ""
