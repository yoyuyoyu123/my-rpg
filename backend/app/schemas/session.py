"""
契约层 · 会话与记忆
===================
前端和后端围绕「一局游戏」交换的数据结构。
"""
from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    """开一局新游戏。"""

    title: str = Field("", max_length=120, description="存档名，留空自动生成")
    world_id: str = Field(..., description="世界观 id，见 /api/worlds")
    preset_id: str = Field("", description="特色预设 id，可空")
    pace: str = Field("long", description="篇幅：short/medium/long")


class SessionInfo(BaseModel):
    """一局游戏的概要。"""

    id: str
    title: str
    world_id: str
    world_name: str = ""
    preset_id: str = ""
    pace: str
    turn_no: int
    entity_count: int = 0
    fact_count: int = 0
    updated_at: str = ""


class FactIn(BaseModel):
    """写入一条事实。"""

    key: str = Field(..., max_length=40)
    value: str = Field(..., max_length=400)


class EntityIn(BaseModel):
    """写入一个实体及其事实。"""

    name: str = Field(..., max_length=80)
    kind: str = Field(..., description="person/place/faction/object/event/concept")
    aliases: list[str] = Field(default_factory=list)
    importance: int = Field(1, ge=0, le=3)
    facts: list[FactIn] = Field(default_factory=list)


class MemoryWrite(BaseModel):
    """一次记忆写入请求。"""

    turn: int = Field(..., ge=0)
    entities: list[EntityIn] = Field(default_factory=list)
    source: str = Field("narrative", description="narrative/player/system")


class ConflictOut(BaseModel):
    """一次被拦截的矛盾。"""

    entity: str
    key: str
    old_value: str
    new_value: str
    old_turn: int
    description: str


class MemoryWriteResult(BaseModel):
    """写入结果：记了多少、拦了什么。"""

    entities_touched: int = 0
    facts_written: int = 0
    events_written: int = 0
    commitments_written: int = 0
    beliefs_written: int = 0
    character_states_written: int = 0
    conflicts: list[ConflictOut] = Field(default_factory=list)


class ExtractRequest(BaseModel):
    """让后端从叙事里自动抽取事实。"""

    turn: int = Field(..., ge=0)
    narrative: str = Field(..., description="本回合的叙事正文")
    player_input: str = Field("", description="玩家这回合的输入")
    provider: str = Field("deepseek")
    model: str = Field("")


class ExtractPromptOut(BaseModel):
    """后端出的「抽取题目」，交给前端用自己的凭据去跑模型。"""

    prompt: str
    temperature: float = 0.2
    max_tokens: int = 900


class ExtractResult(BaseModel):
    """前端跑完模型后把原始输出交回来，由后端解析入库。"""

    turn: int = Field(..., ge=0)
    raw: str = Field(..., description="模型原始输出，后端负责挖 JSON 和清洗")


class ContextOut(BaseModel):
    """检索到的、可直接拼进提示词的设定文本。"""

    text: str = Field("", description="没有相关设定时为空串")
    entity_count: int = 0
    fact_count: int = 0
    event_count: int = 0
    commitment_count: int = 0
    belief_count: int = 0
    character_state_count: int = 0
    trace: list[dict] = Field(
        default_factory=list,
        description="每条记忆被纳入或排除的原因，供后台监视器解释检索结果。",
    )
    names: list[str] = Field(
        default_factory=list,
        description="当前全部实体名与别名。前端拿它在下一回合的文本里做匹配，"
                    "从而知道该把哪些名字作为 mentioned 传回来——省一次往返。",
    )


class EntityOut(BaseModel):
    """实体详情，供前端「设定档案」面板展示。"""

    id: int
    kind: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    importance: int = 1
    first_turn: int = 0
    last_seen_turn: int = 0
    facts: list[dict] = Field(default_factory=list)


class RollbackIn(BaseModel):
    """丢弃某一回合及其之后写入的全部叙事记录。"""

    from_turn: int = Field(..., ge=0, description="从这一回合起（含）全部丢弃")
    reason: str = Field("", max_length=40, description="undo / regen / manual")


class RollbackOut(BaseModel):
    """各类记录删了多少条，前端据此如实告诉玩家动了什么。"""

    facts: int = 0
    entities: int = 0
    events: int = 0
    commitments: int = 0
    beliefs: int = 0
    character_states: int = 0
