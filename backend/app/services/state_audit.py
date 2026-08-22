"""
服务层 · 状态审计
=================
出一道题让模型核对「叙事里真正发生了什么状态变化」，再把它的回答清洗成补丁。

为什么这段提示词该和结算规则住在一起：
    它俩描述的是同一套约束。game_state.py 说「属性单回合最多 ±1」，
    这里就得告诉模型「没有明确进展就不要改」。分居两地的话，
    改了一边忘了另一边——模型照旧申报，程序照旧拦下，谁也不知道
    为什么每回合都有一半的申报被丢掉。

三步分工和事实抽取一样：后端出题 → 前端跑模型 → 后端阅卷。
直连模式下 API key 在浏览器手里，后端调不动模型；这样拆开后
提示词和清洗规则始终只有后端这一份。
"""
import json
import re
from typing import Any

from app.services.game_state import normalize_inventory, normalize_skills

# 审计只需要判断「有没有发生」，不需要长篇大论
AUDIT_MAX_TOKENS = 400
AUDIT_TEMPERATURE = 0.1

# 模型可以申报的字段。和 game_state.apply_patch 认识的字段保持一致——
# 这里多写一个，那边不认识，就是白花 token 让模型填一个必然被丢弃的坑。
_ALLOWED_KEYS = (
    "attr_delta", "res_delta", "inv_delta", "inv_upsert", "equip_set",
    "skill_upsert", "skill_progress", "active_skill", "npc_set", "npc_rm",
    "loc", "talent_add", "talent_rm",
)

AUDIT_RULES = (
    "你是文字RPG的确定性状态结算器，不写剧情。根据“回合前权威状态、玩家行动、"
    "已经发生的可见结果、叙事模型申报”输出一份相对于回合前状态的完整且最小状态补丁。\n"
    "原则：只有可见结果明确完成的变化才结算；意图、准备、尝试、报价、查看、询问不算完成。"
    "普通对话、查看背包、整理记忆不消耗饱腹、体力或其他生理资源。"
    "不得创造结果里没有的物品、技能、金额或数量；同名物品必须使用原id或原名。"
    "进食/消耗用负数inv_delta；获得用正数，只有全新物品才用inv_upsert。"
    "技能训练仅在结果明确完成训练时增加熟练度，通常1-5；没有明确进展就不改。"
    "地点确实改变才写loc。NPC独立知识只能通过npc_set中的knows_add/knows_rm改变；"
    "只有玩家当面对该NPC说出口、该NPC直接观察并可靠确认、或剧情明确发生信息传递时才能knows_add。"
    "旁白、隐藏蓝图、玩家内心、异常猜测以及别的NPC知道的事均不得写入。"
    "叙事模型申报只是候选，若与可见结果冲突则忽略。\n"
    "只输出一个JSON对象，可用字段：attr_delta,res_delta,inv_delta:[{id或name,delta}],"
    "inv_upsert:[完整物品],equip_set:{id或name:true/false},skill_upsert:[完整技能],"
    "skill_progress:[{id或name,delta,realm可选}],active_skill,"
    "npc_set:{NPC名:{rel,att,note,knows_add:[],knows_rm:[]}},npc_rm,loc,talent_add,talent_rm。"
    "无变化输出{}。"
)


def compact_state(state: dict[str, Any]) -> dict[str, Any]:
    """
    审计只需要「现在有什么」，不需要账本、上限、装备槽这些。

    尤其是账本——它最多 300 条、占状态 JSON 的八成，塞进提示词纯属烧钱，
    而且会把真正有用的字段挤出上下文（规划器那边踩过一模一样的坑）。
    """
    s = state if isinstance(state, dict) else {}
    return {
        "revealed": bool(s.get("revealed")),
        "attrs": s.get("attrs") or {},
        "res": s.get("res") or {},
        "inv": [
            {k: x[k] for k in ("id", "name", "category", "quantity", "equipped")}
            for x in normalize_inventory(s.get("inv"))
        ],
        "skills": [
            {k: x[k] for k in ("id", "name", "category", "realm", "coefficient",
                               "proficiency", "attribute", "active")}
            for x in normalize_skills(s.get("skills"), "")
        ],
        "talents": s.get("talents") or [],
        "loc": s.get("loc") or "",
        "npcs": s.get("npcs") or {},
    }


def strip_protocol_blocks(reply: str) -> str:
    """
    去掉隐藏协议块，只留玩家真正看见的正文。

    审计要判断的是「叙事里明确发生了什么」，而 STATE 块是模型的*申报*——
    把申报当成证据，等于让它自己给自己作证。申报另外走 declared 字段。
    """
    text = str(reply or "")
    for tag in ("大纲", "STATE", "SHEET_INIT"):
        text = re.sub(rf"【{tag}】[\s\S]*?【/{tag}】", "", text)
    return text[:2500]


def build_audit_prompt(
    *,
    before: dict[str, Any],
    player_input: str,
    reply: str,
    declared: list[dict[str, Any]] | None = None,
) -> str:
    return (
        AUDIT_RULES
        + "\n回合前：" + _dump(compact_state(before))
        + "\n玩家行动：" + str(player_input or "")[:1600]
        + "\n可见结果：" + strip_protocol_blocks(reply)
        + "\n候选申报：" + _dump(declared or [])
    )


def _dump(value: Any) -> str:
    """
    序列化必须和 JS 的 JSON.stringify 对齐：它不带空格，
    而 Python 默认带（"a": 1 而不是 "a":1）。差这一点提示词就不是同一份了。
    """
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def parse_audit_result(raw: str) -> dict[str, Any] | None:
    """
    把模型输出解析成补丁。

    返回 None 表示「审计没能完成」——调用方必须据此**不结算**，
    而不是退回去用叙事模型自己的申报。那份申报正是审计要核对的对象，
    审计失败就用它，等于审计从来没存在过。

    返回 {} 表示「审计确认这一回合没有状态变化」，是有效结论。
    """
    text = str(raw or "")
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    # 词表外的字段丢掉：apply_patch 不认识它们，留着只会让调试记录里
    # 出现一堆「申报了但没生效」的噪音
    return {k: v for k, v in data.items() if k in _ALLOWED_KEYS}
