"""
数据层 · 表结构
===============
SQLAlchemy 2.0 声明式模型。

三张核心表：
    sessions  一局游戏
    entities  这局里出现过的人/地/物/组织/事件/概念
    facts     关于这些实体的、已确立的事实

设计要点：
    1. 事实不删除，只标记「被取代」（superseded_by）——
       这样能追溯「设定什么时候变的、为什么变」，也支持回滚。
    2. 别名单独存表——AI 说「吴婶」时能解析到「吴四娘」这个实体。
    3. 所有表都带 session_id——不同存档互不干扰。
"""
from datetime import datetime, timezone

from sqlalchemy import (
    ForeignKey, Index, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Session(Base):
    """一局游戏。"""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    title: Mapped[str] = mapped_column(String(120), default="")
    world_id: Mapped[str] = mapped_column(String(40), default="")
    preset_id: Mapped[str] = mapped_column(String(40), default="")
    pace: Mapped[str] = mapped_column(String(20), default="long")

    turn_no: Mapped[int] = mapped_column(Integer, default=0)

    # 大块的运行时状态先整体存 JSON 文本。
    # 它们是「一整坨一起读写」的，拆表没有收益。
    # 而 entities/facts 需要按条查询和比对，所以才单独建表。
    game_state_json: Mapped[str] = mapped_column(Text, default="{}")
    blueprint_json: Mapped[str] = mapped_column(Text, default="{}")
    outline: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    entities: Mapped[list["Entity"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    narrative_events: Mapped[list["NarrativeEvent"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    commitments: Mapped[list["Commitment"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    npc_beliefs: Mapped[list["NpcBelief"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    character_states: Mapped[list["CharacterState"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Entity(Base):
    """
    一个叙事实体。

    canonical_name 是规范名——所有别名最终都指向它。
    有了实体 ID，「同一个人」才成为程序能理解的概念。
    """

    __tablename__ = "entities"
    __table_args__ = (
        UniqueConstraint("session_id", "canonical_name", "kind", name="uq_entity_name"),
        Index("ix_entity_session_kind", "session_id", "kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))

    kind: Mapped[str] = mapped_column(String(20))          # EntityKind
    canonical_name: Mapped[str] = mapped_column(String(80))

    # 重要度 0-3：注入提示词时优先带上高分实体，低分的等被提到再说
    importance: Mapped[int] = mapped_column(Integer, default=1)

    first_turn: Mapped[int] = mapped_column(Integer, default=0)
    last_seen_turn: Mapped[int] = mapped_column(Integer, default=0)

    session: Mapped[Session] = relationship(back_populates="entities")
    aliases: Mapped[list["EntityAlias"]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )
    facts: Mapped[list["Fact"]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )


class EntityAlias(Base):
    """
    实体的别名。

    「吴四娘」「吴婶」「隔壁那个洗衣的」都可能指同一个人。
    没有这张表，AI 换个说法就会被当成新角色。
    """

    __tablename__ = "entity_aliases"
    __table_args__ = (
        UniqueConstraint("session_id", "alias", name="uq_alias"),
        Index("ix_alias_lookup", "session_id", "alias"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(String(80))

    entity: Mapped[Entity] = relationship(back_populates="aliases")


class Save(Base):
    """
    一个存档槽。

    原本存在浏览器的 IndexedDB 里——那意味着存档跟设备绑死：
    电脑上玩到一半，手机打开就是一片空白。搬到服务端后，
    同一个后端下所有设备看到的是同一批存档。

    payload 是整个运行时快照（历史、状态、事实库会话 id……），
    它永远是「一整坨一起读写」的，所以不拆表。
    但摘要字段单独存了一份：渲染存档列表时只需要这几个字段，
    没必要为了显示一行字把几 MB 的正文全捞出来解析。
    """

    __tablename__ = "saves"

    # 槽位名就是主键：'auto'、'sv_0'、'sv_1'……存档天然是覆盖语义
    slot: Mapped[str] = mapped_column(String(20), primary_key=True)

    desc: Mapped[str] = mapped_column(String(200), default="")
    world_id: Mapped[str] = mapped_column(String(40), default="")
    world_name: Mapped[str] = mapped_column(String(60), default="")
    turns: Mapped[int] = mapped_column(Integer, default=0)
    # 客户端本地时间的展示字符串。服务端时间见 updated_at，两者用途不同
    client_time: Mapped[str] = mapped_column(String(40), default="")

    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    # 正文的结构版本。存下来是为了不必解析几 MB 的 JSON 就知道该不该迁移。
    schema_version: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Fact(Base):
    """
    一条已确立的事实。

    「王铁匠的儿子在府城当学徒」拆成：
        entity=王铁匠, key=秘密/现状..., value=儿子在府城当学徒

    superseded_by 不为空表示这条已被后来的事实取代。
    保留而不删除，是为了能回答「这个设定是什么时候、因为什么改的」。
    """

    __tablename__ = "facts"
    __table_args__ = (
        Index("ix_fact_entity_key", "entity_id", "key"),
        Index("ix_fact_session_turn", "session_id", "turn"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"))

    key: Mapped[str] = mapped_column(String(40))       # 来自 ontology 的属性词表
    value: Mapped[str] = mapped_column(Text)
    stability: Mapped[str] = mapped_column(String(10), default="mutable")

    turn: Mapped[int] = mapped_column(Integer, default=0)
    # narrative=从叙事抽取 / player=玩家明确声明 / system=程序结算
    # 玩家声明的优先级最高，冲突时以它为准
    source: Mapped[str] = mapped_column(String(20), default="narrative")

    superseded_by: Mapped[int | None] = mapped_column(Integer, default=None)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    entity: Mapped[Entity] = relationship(back_populates="facts")

    @property
    def active(self) -> bool:
        return self.superseded_by is None


class NarrativeEvent(Base):
    """按回合保存的可追溯事件节点，而不是会被摘要吞掉的散文片段。"""

    __tablename__ = "narrative_events"
    __table_args__ = (
        Index("ix_event_session_turn", "session_id", "turn"),
        Index("ix_event_session_kind", "session_id", "kind"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    turn: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(32), default="scene")
    actor: Mapped[str] = mapped_column(String(80), default="")
    action: Mapped[str] = mapped_column(Text, default="")
    outcome: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(120), default="")
    participants_json: Mapped[str] = mapped_column(Text, default="[]")
    cause_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    # public=所有在场者可知 / participants=仅参与者 / private=后台正史
    visibility: Mapped[str] = mapped_column(String(20), default="public")
    source: Mapped[str] = mapped_column(String(20), default="narrative")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    session: Mapped[Session] = relationship(back_populates="narrative_events")


class Commitment(Base):
    """承诺、拒绝与任务接受等持续约束；避免钩子被换皮重塞。"""

    __tablename__ = "commitments"
    __table_args__ = (
        Index("ix_commitment_session_status", "session_id", "status"),
        Index("ix_commitment_session_turn", "session_id", "updated_turn"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(24), default="promise")
    owner_name: Mapped[str] = mapped_column(String(80), default="")
    counterparty_name: Mapped[str] = mapped_column(String(80), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="active")
    hard: Mapped[int] = mapped_column(Integer, default=0)
    created_turn: Mapped[int] = mapped_column(Integer, default=0)
    updated_turn: Mapped[int] = mapped_column(Integer, default=0)
    due_turn: Mapped[int | None] = mapped_column(Integer, default=None)
    forbids_json: Mapped[str] = mapped_column(Text, default="[]")
    source_event_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    session: Mapped[Session] = relationship(back_populates="commitments")


class NpcBelief(Base):
    """某个 NPC 自己知道/相信/误解的内容，不等同于世界真相。"""

    __tablename__ = "npc_beliefs"
    __table_args__ = (
        UniqueConstraint("session_id", "npc_name", "statement", name="uq_npc_belief"),
        Index("ix_belief_session_npc", "session_id", "npc_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    npc_name: Mapped[str] = mapped_column(String(80))
    statement: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(20), default="knows")
    confidence: Mapped[int] = mapped_column(Integer, default=100)
    source_name: Mapped[str] = mapped_column(String(100), default="")
    learned_turn: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    session: Mapped[Session] = relationship(back_populates="npc_beliefs")


class CharacterState(Base):
    """人物的身份、中期目标、短期状态和关系分层快照。"""

    __tablename__ = "character_states"
    __table_args__ = (
        UniqueConstraint("session_id", "entity_name", name="uq_character_state"),
        Index("ix_character_session_turn", "session_id", "updated_turn"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    entity_name: Mapped[str] = mapped_column(String(80))
    identity_json: Mapped[str] = mapped_column(Text, default="{}")
    mid_term_json: Mapped[str] = mapped_column(Text, default="{}")
    short_term_json: Mapped[str] = mapped_column(Text, default="{}")
    relationships_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_turn: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    session: Mapped[Session] = relationship(back_populates="character_states")
