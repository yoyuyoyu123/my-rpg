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
