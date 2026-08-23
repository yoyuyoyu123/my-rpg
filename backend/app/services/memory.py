"""
服务层 · 事实库
===============
职责：把叙事里的设定变成可查询、可校验的数据，并在写入时拦截矛盾。

这一层解决的具体问题：
    「上文说吴四娘是洗衣妇，下文变成了茶馆老板娘」
    「上文说主角来了三年，下文变成七年」

解决方式不是「更用力地提醒 AI」，而是：
    1. 事实存进数据库，不随历史压缩丢失
    2. 稳定属性被改写时，程序拦截并报告冲突
    3. 组装提示词时按相关性检索注入，而不是全量堆砌
"""
from dataclasses import dataclass
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Entity, EntityAlias, Fact
from app.domain.ontology import (
    EntityKind, Stability, conflict_guarded, stability_of,
)
from app.services.narrative_memory import retrieve_narrative_context


@dataclass
class Conflict:
    """一次矛盾：同一实体的同一稳定属性，被写入了不同的值。"""

    entity_name: str
    key: str
    old_value: str
    new_value: str
    old_turn: int

    def describe(self) -> str:
        return (
            f"「{self.entity_name}」的{self.key}："
            f"第{self.old_turn}回合确立为「{self.old_value}」，"
            f"现在却是「{self.new_value}」"
        )


async def resolve_entity(
    db: AsyncSession, session_id: str, name: str
) -> Entity | None:
    """
    按名字找实体——先查规范名，再查别名。

    这是「同一个人」这个概念的技术实现：
    不管 AI 这次叫「吴四娘」还是「吴婶」，都能落到同一条记录上。
    """
    name = (name or "").strip()
    if not name:
        return None

    stmt = select(Entity).where(
        Entity.session_id == session_id, Entity.canonical_name == name
    )
    found = (await db.execute(stmt)).scalar_one_or_none()
    if found:
        return found

    alias_stmt = (
        select(Entity)
        .join(EntityAlias, EntityAlias.entity_id == Entity.id)
        .where(EntityAlias.session_id == session_id, EntityAlias.alias == name)
    )
    return (await db.execute(alias_stmt)).scalar_one_or_none()


async def upsert_entity(
    db: AsyncSession,
    session_id: str,
    *,
    name: str,
    kind: EntityKind | str,
    turn: int,
    aliases: list[str] | None = None,
    importance: int = 1,
) -> Entity:
    """找到或创建实体，并登记别名。"""
    entity = await resolve_entity(db, session_id, name)

    if entity is None:
        entity = Entity(
            session_id=session_id,
            kind=EntityKind(kind).value if not isinstance(kind, str) else kind,
            canonical_name=name.strip(),
            importance=max(0, min(3, importance)),
            first_turn=turn,
            last_seen_turn=turn,
        )
        db.add(entity)
        await db.flush()  # 拿到自增 id
    else:
        entity.last_seen_turn = turn
        if importance > entity.importance:
            entity.importance = importance

    for alias in aliases or []:
        alias = alias.strip()
        if not alias or alias == entity.canonical_name:
            continue
        exists = await db.execute(
            select(EntityAlias).where(
                EntityAlias.session_id == session_id, EntityAlias.alias == alias
            )
        )
        if exists.scalar_one_or_none() is None:
            db.add(EntityAlias(session_id=session_id, entity_id=entity.id, alias=alias))

    return entity


async def active_facts(
    db: AsyncSession, entity_id: int, key: str | None = None
) -> list[Fact]:
    """取某实体当前生效的事实（未被取代的）。"""
    stmt = select(Fact).where(Fact.entity_id == entity_id, Fact.superseded_by.is_(None))
    if key:
        stmt = stmt.where(Fact.key == key)
    return list((await db.execute(stmt)).scalars())


async def record_fact(
    db: AsyncSession,
    session_id: str,
    entity: Entity,
    *,
    key: str,
    value: str,
    turn: int,
    source: str = "narrative",
) -> tuple[Fact | None, Conflict | None]:
    """
    写入一条事实，并做矛盾检测。

    返回 (新事实, 冲突)：
      - 值没变        → (None, None)，什么都不做
      - 可变属性变了   → (新事实, None)，旧的标记为被取代，这是正常剧情推进
      - 稳定属性变了   → (None, 冲突)，【不写入】，交由上层决定怎么处理

    最后一种是关键：程序在这里挡住了穿帮，而不是等玩家自己发现。
    """
    key = key.strip()
    value = (value or "").strip()
    if not key or not value:
        return None, None

    stability = stability_of(entity.kind, key)
    existing = await active_facts(db, entity.id, key)

    def normalized(v: str) -> str:
        return re.sub(r"[\s，。；：、,.!?！？'\"“”‘’（）()【】\[\]·—-]+", "", v).casefold()

    def compatible(a: str, b: str) -> bool:
        """字面相同或一方只是更详细时，不把它误报成矛盾。"""
        na, nb = normalized(a), normalized(b)
        if not na or not nb:
            return False
        if na == nb:
            return True
        neg = ("不", "非", "无", "没有", "不是", "并非")
        if any(x in na for x in neg) != any(x in nb for x in neg):
            return False
        return min(len(na), len(nb)) >= 2 and (na in nb or nb in na)

    for old in existing:
        if compatible(old.value, value):
            return None, None  # 完全一样，不重复记

        if (stability is Stability.STABLE
                and conflict_guarded(entity.kind, key)
                and old.source != "system"):
            # 玩家亲口说的可以覆盖 AI 之前编的；AI 改 AI 自己的稳定设定则拦截
            if source == "player":
                break
            return None, Conflict(
                entity_name=entity.canonical_name,
                key=key,
                old_value=old.value,
                new_value=value,
                old_turn=old.turn,
            )

    fact = Fact(
        session_id=session_id,
        entity_id=entity.id,
        key=key,
        value=value,
        stability=stability.value,
        turn=turn,
        source=source,
    )
    db.add(fact)
    await db.flush()

    # 旧值标记为被这条取代（保留历史，可追溯）
    for old in existing:
        old.superseded_by = fact.id

    return fact, None


@dataclass
class RetrievedContext:
    text: str
    entity_count: int
    trace: list[dict]
    counts: dict[str, int]


async def retrieve_context_bundle(
    db: AsyncSession,
    session_id: str,
    *,
    mentioned: list[str] | None = None,
    max_entities: int = 12,
    max_facts_each: int = 6,
    current_turn: int = 0,
    speaker: str = "",
) -> RetrievedContext:
    """
    检索式注入：只带回本回合可能用得上的事实。

    为什么不全量注入：
      玩到几十回合后事实会有几百条，全塞进去既超上下文又稀释注意力。
      按「本回合提到的实体 + 高重要度实体 + 最近出现的实体」检索，
      既省 token 又更相关。

    返回可直接拼进 system prompt 的文本；没有事实时返回空串。
    """
    picked: dict[int, Entity] = {}

    # 1. 本回合被提到的实体最优先
    for name in mentioned or []:
        ent = await resolve_entity(db, session_id, name)
        if ent:
            picked[ent.id] = ent

    # 2. 补充高重要度 / 最近出现的实体
    if len(picked) < max_entities:
        stmt = (
            select(Entity)
            .where(Entity.session_id == session_id)
            .order_by(Entity.importance.desc(), Entity.last_seen_turn.desc())
            .limit(max_entities * 2)
        )
        for ent in (await db.execute(stmt)).scalars():
            if len(picked) >= max_entities:
                break
            picked.setdefault(ent.id, ent)

    lines: list[str] = []
    trace: list[dict] = []
    fact_count = 0
    for ent in picked.values():
        stmt = select(Fact).where(
            Fact.entity_id == ent.id, Fact.superseded_by.is_(None),
        )
        if current_turn > 0:
            stmt = stmt.where(Fact.turn <= current_turn)
        facts = list((await db.execute(stmt)).scalars())
        if not facts:
            continue
        # 稳定属性优先——它们是最不该被改错的
        facts.sort(key=lambda f: (f.stability != "stable", -f.turn))
        selected = facts[:max_facts_each]
        fact_count += len(selected)
        parts = [f"{f.key}={f.value}（事实#{f.id}，第{f.turn}回合，来源={f.source}）" for f in selected]
        lines.append(f"[{ent.kind}] {ent.canonical_name}：" + "；".join(parts))
        for fact in selected:
            trace.append({"id": f"fact:{fact.id}", "type": "fact", "included": True,
                          "reason": "提及实体" if ent.canonical_name in (mentioned or []) else "重要度/近期"})

    sections: list[str] = []
    if lines:
        sections.append(
            "【已确立的设定——带时间与来源的权威正史】\n"
            + "\n".join(lines)
            + "\n稳定设定不得直接改写；若叙事明确揭示旧记录只是传闻或误解，先写出证据，再由程序更新。"
        )

    context_names = list(dict.fromkeys([
        *(mentioned or []), *[ent.canonical_name for ent in picked.values()],
    ]))
    narrative_sections, narrative_trace, narrative_counts = await retrieve_narrative_context(
        db, session_id, mentioned=context_names, current_turn=current_turn, speaker=speaker,
    )
    sections.extend(narrative_sections)
    trace.extend(narrative_trace)
    counts = {"fact_count": fact_count}
    counts.update(narrative_counts)
    return RetrievedContext(
        text="\n\n".join(sections), entity_count=len(lines), trace=trace, counts=counts,
    )


async def retrieve_context(
    db: AsyncSession,
    session_id: str,
    *,
    mentioned: list[str] | None = None,
    max_entities: int = 12,
    max_facts_each: int = 6,
    current_turn: int = 0,
    speaker: str = "",
) -> str:
    """兼容旧调用：只返回可直接注入 system prompt 的文本。"""
    bundle = await retrieve_context_bundle(
        db, session_id, mentioned=mentioned, max_entities=max_entities,
        max_facts_each=max_facts_each, current_turn=current_turn, speaker=speaker,
    )
    return bundle.text
