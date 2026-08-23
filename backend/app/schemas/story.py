"""结构化剧情规划契约。

规划器不写正文，只维护一个短期可执行的故事状态；叙事模型只会看到
``current_scene`` 的公开部分，不能偷看幕后原因，也不能擅自扩写整条主线。
"""
from typing import Any, Literal

from pydantic import BaseModel, Field


class NarrativeBeat(BaseModel):
    id: str = ""
    label: str = ""
    purpose: str = ""
    prerequisites: list[str] = Field(default_factory=list)
    setup: list[str] = Field(default_factory=list)
    activation_condition: str = ""
    status: Literal["dormant", "available", "active", "resolved", "abandoned"] = "dormant"


class StoryThread(BaseModel):
    id: str = ""
    title: str = ""
    kind: str = ""
    public_goal: str = ""
    private_cause: str = ""
    why_now: str = ""
    player_connection: str = ""
    established_clues: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    beats: list[NarrativeBeat] = Field(default_factory=list)
    status: Literal["dormant", "active", "paused", "resolved", "abandoned"] = "active"


class NameProposal(BaseModel):
    """本幕要引入的一个新专名，以及规划器给出的候选。

    模型不直接定名，只给候选和自评概率；程序从分布里挑（避开众数）。
    这是 Verbalized Sampling 的做法，用来绕开模型对「青石镇」这类
    最典型名字的默认偏好。详见 app/services/naming.py。
    """
    slot: str = ""          # 这个名字是给什么的：「落点城镇」「渡口老板」
    kind: str = ""          # place / person / faction / other
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    chosen: str = ""        # 程序挑定的结果；写手必须用这个


class SceneCard(BaseModel):
    id: str = ""
    title: str = ""
    situation: str = ""
    purpose: str = ""
    causal_bridge: str = ""
    active_thread_ids: list[str] = Field(default_factory=list)
    participant_intents: dict[str, str] = Field(default_factory=dict)
    available_information: list[str] = Field(default_factory=list)
    # SceneContract：写手本回合能做什么、不能做什么以及强度预算。
    causal_event_ids: list[str] = Field(default_factory=list)
    affordances: list[str] = Field(default_factory=list)
    allowed_developments: list[str] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)
    soft_commitment_ids: list[str] = Field(default_factory=list)
    pressure_budget: int = Field(1, ge=0, le=4)
    mystery_budget: int = Field(0, ge=0, le=4)

    # 叙事密度：这一幕该详写还是略写。
    #
    # 强度预算管的是「多紧张」，篇幅设置管的是「整局多长」，两者都回答不了
    # 「这一幕值不值得逐步展开」。缺了这个概念的后果实测过：一次穿越的
    # 传送过程写了 11 个回合约 4500 字，每回合换个感官细节重复同一件事
    # ——水雾、嗡鸣、进度条、摸路灯杆、吸一口凉气、再看进度条。
    #
    # 小说的常规做法是：有冲突、有选择、有新信息才详写；纯过程
    # （移动、等待、转换、例行公事）在结果已定时略写带过。
    narration: Literal["scene", "summary"] = "scene"
    # 略写时这一幕要跨过什么、停在哪里。详写时留空。
    summary_target: str = ""
    # 本幕的冲突是什么；没有冲突就留空。
    #
    # 这是「详写」的举证。纯过程的幕（转移途中、赶路、等待）默认略写，
    # 但过程中真的出事时——有人阻拦、机制故障、玩家必须当场做选择——
    # 那就不再是纯过程，理应详写。判断权仍在规划器手里，程序只检查它
    # 有没有把理由说出来：说不出具体冲突，就按纯过程处理。
    conflict: str = ""

    # 本幕要引入的新专名。程序挑定后写进命名表，写手照用。
    new_names: list[NameProposal] = Field(default_factory=list)

    stop_points: list[str] = Field(default_factory=list)
    refresh_after_turn: int = 0
    premise_phase: int | None = Field(default=None, ge=0, le=5)
    # 这张卡的阶段是程序下的令，不是规划器的提案。
    #
    # 前端对 premise_phase > 当前+1 会静默回退（applyStoryPremisePhase），
    # 那个钳制是用来不信任模型「赶进度」的。程序接管迁移时下发的卡不是
    # 模型提案，必须能越过它，否则接管多少次都会被打回原样。
    premise_phase_forced: bool = False
    status: Literal["active", "resolved"] = "active"


class StoryRuntime(BaseModel):
    version: int = 1
    revision: int = 1
    premise: str = ""
    threads: list[StoryThread] = Field(default_factory=list)
    current_scene: SceneCard | None = None
    last_planned_turn: int = 0
    plan_reason: str = "opening"
    # 连续多少幕的 purpose 与上一幕实质相同。
    #
    # 目标重复说明上一幕的停止点设早了：该发生的事没发生，规划器只好把
    # 同一句 purpose 再写一遍。实测一局 17 回合里「推进到逼近」写了 4 幕、
    # 「推进到阈限」写了 3 幕，迁移阶段只从 0 走到 2。
    # 这个计数会回灌进下一次规划提示词，逐级施压。
    scene_repeat_count: int = 0


class StoryPlanContext(BaseModel):
    world_id: str
    preset_id: str = ""
    pace: str = "long"
    turn: int = Field(0, ge=0)
    reason: Literal["opening", "premise", "scene_boundary", "horizon", "manual"] = "opening"
    custom_world_prompt: str = ""
    story_dna: str = ""
    opening_text: str = ""
    locked_tags: list[str] = Field(default_factory=list)
    inspiration_tags: list[str] = Field(default_factory=list)
    game_state: dict[str, Any] = Field(default_factory=dict)
    player_canon: dict[str, str] = Field(default_factory=dict)
    premise_state: dict[str, Any] = Field(default_factory=dict)
    prefs: dict[str, Any] = Field(default_factory=dict)
    lore_context: str = ""
    story_runtime: dict[str, Any] = Field(default_factory=dict)
    recent_messages: list[dict[str, str]] = Field(default_factory=list)


class StoryPlanPromptOut(BaseModel):
    prompt: str
    max_tokens: int = 2400
    temperature: float = 0.55


class StoryPlanResultIn(BaseModel):
    raw: str
    previous_runtime: dict[str, Any] = Field(default_factory=dict)
    # The migration phase is program-owned.  The planner may describe the
    # current phase, but it must never advance it by itself.
    premise_state: dict[str, Any] = Field(default_factory=dict)
    turn: int = Field(0, ge=0)
    reason: str = "opening"
    # 迁移预算按篇幅算，所以校验这一步也要知道篇幅。
    pace: str = "medium"


class StoryPlanResultOut(BaseModel):
    runtime: StoryRuntime
    warnings: list[str] = Field(default_factory=list)
