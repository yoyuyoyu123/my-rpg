"""
领域层 · 通用叙事本体
=====================
这个文件回答一个问题：**任何世界观里的"设定"，怎么用同一套结构表示？**

设计出发点：
    武侠的「丐帮」、赛博的「军用科技公司」、克苏鲁的「秘密教团」——
    表面完全不同，但结构上都是「有立场、有成员、有势力范围的组织」。
    只要抽象层次选对，一套 schema 就能覆盖所有世界观。

为什么要结构化：
    叙事文本里的事实是「一次性」的——说过就埋进聊天记录，
    压缩历史时就永久丢失。变成结构化数据后，它才能被查询、被校验、被长期保存。

两个关键设计：
    1. 实体分六类（够用且不重叠），属性名用统一词表 → 可查询、可比对
    2. 属性分「稳定」与「可变」→ 只有稳定属性变化才算矛盾
       （NPC 的位置天天变很正常，但出生地变了就是穿帮）
"""
from enum import Enum


class EntityKind(str, Enum):
    """
    实体类型。

    这六类是刻意选的：粒度够粗，能覆盖任何世界观；又够细，能支撑不同的属性集。
    继承 str 是为了能直接存进数据库和 JSON。
    """

    PERSON = "person"      # 人物：NPC、同伴、敌人。任何有意识的个体
    PLACE = "place"        # 地点：城镇、建筑、房间、区域
    FACTION = "faction"    # 组织：门派、公司、帮派、政权、教团
    OBJECT = "object"      # 器物：世界中的物件（背包里的由 GAME_STATE 管）
    EVENT = "event"        # 事件：已发生的事，带时间与因果
    CONCEPT = "concept"    # 概念：功法、技术、习俗、规则、传说


class Stability(str, Enum):
    """
    属性的稳定性——这是矛盾检测的基础。

    STABLE   一旦确立就不该变。变了就是穿帮，要拦截。
             例：某人的出生地、某组织的创立者
    MUTABLE  本来就会随剧情变化。变了是正常推进，不报警。
             例：某人此刻在哪、对主角的态度、健康状况
    """

    STABLE = "stable"
    MUTABLE = "mutable"


# ── 通用属性词表 ────────────────────────────────────────────────
# 为什么要固定词表：
#   如果 AI 这次写「职业」下次写「身份」再下次写「工作」，
#   数据库里就是三条互不相干的记录，既查不到也比不出矛盾。
#   统一词表让「同一件事」永远落在同一个 key 上。
#
# 每项含义：属性名 → (稳定性, 给 AI 看的说明)
# 说明会拼进抽取提示词，所以要写得让模型一看就懂。

PERSON_ATTRS: dict[str, tuple[Stability, str]] = {
    "称呼": (Stability.STABLE, "旁人怎么称呼他，如「吴四娘」「老陈」"),
    "性别": (Stability.STABLE, "如果叙事中明确了"),
    "年龄段": (Stability.STABLE, "幼童/少年/青年/中年/老年"),
    "出身": (Stability.STABLE, "籍贯、家世、来历"),
    "职业": (Stability.MUTABLE, "以什么为生。会变（转行、升迁）但不频繁"),
    "所属": (Stability.MUTABLE, "属于哪个组织"),
    "居所": (Stability.MUTABLE, "常住在哪"),
    "外貌": (Stability.STABLE, "长相、身形、显著特征"),
    "性格": (Stability.STABLE, "稳定的行为倾向"),
    "能力": (Stability.MUTABLE, "会什么、擅长什么"),
    "目标": (Stability.MUTABLE, "当前想达成什么"),
    "秘密": (Stability.STABLE, "隐瞒着什么（玩家未必知道）"),
    "与主角关系": (Stability.MUTABLE, "如「邻居」「师父」「债主」"),
    "现状": (Stability.MUTABLE, "此刻在做什么、身在何处、状态如何"),
}

PLACE_ATTRS: dict[str, tuple[Stability, str]] = {
    "类型": (Stability.STABLE, "城镇/村落/店铺/山野/建筑等"),
    "位置": (Stability.STABLE, "在哪，与其它地点的相对关系"),
    "规模": (Stability.STABLE, "大小、人口量级"),
    "氛围": (Stability.STABLE, "给人的感觉、环境特征"),
    "掌控者": (Stability.MUTABLE, "谁说了算"),
    "特产": (Stability.STABLE, "出产什么、以什么闻名"),
    "现状": (Stability.MUTABLE, "当前发生的事、局势"),
}

FACTION_ATTRS: dict[str, tuple[Stability, str]] = {
    "类型": (Stability.STABLE, "门派/公司/帮派/官府/教团等"),
    "宗旨": (Stability.STABLE, "存在的目的、信奉什么"),
    "势力范围": (Stability.MUTABLE, "控制哪些地方"),
    "领袖": (Stability.MUTABLE, "谁在领导"),
    "与主角关系": (Stability.MUTABLE, "敌对/中立/合作/主角所属"),
    "现状": (Stability.MUTABLE, "当前处境"),
}

OBJECT_ATTRS: dict[str, tuple[Stability, str]] = {
    "类型": (Stability.STABLE, "武器/信物/文书/机械等"),
    "外观": (Stability.STABLE, "长什么样"),
    "来历": (Stability.STABLE, "从哪来、谁造的"),
    "效用": (Stability.STABLE, "有什么用、有什么限制"),
    "持有者": (Stability.MUTABLE, "现在在谁手里"),
    "所在": (Stability.MUTABLE, "现在放在哪"),
}

EVENT_ATTRS: dict[str, tuple[Stability, str]] = {
    "内容": (Stability.STABLE, "发生了什么"),
    "时间": (Stability.STABLE, "何时发生（可以是相对时间，如「三年前」）"),
    "地点": (Stability.STABLE, "在哪发生"),
    "涉及者": (Stability.STABLE, "谁参与了"),
    "后果": (Stability.STABLE, "造成了什么影响"),
}

CONCEPT_ATTRS: dict[str, tuple[Stability, str]] = {
    "类型": (Stability.STABLE, "功法/技术/习俗/规则/传说等"),
    "内容": (Stability.STABLE, "是什么、怎么回事"),
    "限制": (Stability.STABLE, "有什么代价、门槛或副作用"),
    "来源": (Stability.STABLE, "谁创的、从哪传下来"),
    "流传度": (Stability.MUTABLE, "多少人知道"),
}

ATTRS_BY_KIND: dict[EntityKind, dict[str, tuple[Stability, str]]] = {
    EntityKind.PERSON: PERSON_ATTRS,
    EntityKind.PLACE: PLACE_ATTRS,
    EntityKind.FACTION: FACTION_ATTRS,
    EntityKind.OBJECT: OBJECT_ATTRS,
    EntityKind.EVENT: EVENT_ATTRS,
    EntityKind.CONCEPT: CONCEPT_ATTRS,
}


def stability_of(kind: EntityKind | str, key: str) -> Stability:
    """
    查某个属性是稳定还是可变。

    词表之外的自定义属性一律当作 MUTABLE——
    宁可漏报矛盾，也不要因为一个我们没预料到的属性而误拦叙事。
    """
    k = EntityKind(kind) if isinstance(kind, str) else kind
    entry = ATTRS_BY_KIND.get(k, {}).get(key)
    return entry[0] if entry else Stability.MUTABLE


def attr_menu(kind: EntityKind | str) -> str:
    """
    生成给抽取模型看的属性清单。

    直接把词表拼成提示词的一部分，保证模型用的 key 和我们查询的 key 一致。
    """
    k = EntityKind(kind) if isinstance(kind, str) else kind
    items = ATTRS_BY_KIND.get(k, {})
    return "、".join(f"{name}（{desc}）" for name, (_, desc) in items.items())


# 给抽取提示词用的实体类型说明
KIND_MENU = "；".join([
    "person=人物（任何有意识的个体）",
    "place=地点（城镇、建筑、区域）",
    "faction=组织（门派、公司、帮派、政权）",
    "object=器物（世界中的重要物件）",
    "event=事件（已发生的事）",
    "concept=概念（功法、技术、习俗、规则、传说）",
])
