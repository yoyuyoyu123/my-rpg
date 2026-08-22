"""
服务层 · GM 裁定
================
出一道题让模型做后台判定：玩家这一步授权到哪儿、要不要检定、本回合在哪停下。

它和写手的分工是刻意的：
    裁判只判定，不写一个字剧情，玩家永远看不到它的输出；
    写手只按判定叙事，不得改判。
合在一起做的话，模型会一边编故事一边为故事的需要放宽判定——
「为了戏剧性」是最常见的失控来源。

复用 prompt_builder 里的迁移状态与身份档案格式化：同一份事实在两处
用不同措辞描述，模型会当成两件事。
"""
import json
from typing import Any

from app.services.prompt_builder import _canon_summary, _premise_directive

DIRECTOR_MAX_TOKENS = 350

# 裁定要冷静稳定，不要发挥
DIRECTOR_TEMPERATURE = 0.3

_AUTHORITY_RULES = (
    "先划定行动授权边界：只把玩家明确说出的动作及完成该动作不可分割的连续过程视为已授权；"
    "任何新的购买、追问、移动、承诺、攻击、使用、关系决定或时间跨越都不在授权内。"
    "玩家只提问、评价、抱怨或表达疑惑时，不授权点击、发送消息、说话、调查或作出决定。"
    "scene_note必须写明本回合在哪里停下。NPC不得使用其“已知”列表之外的主角秘密；"
    "陌生言行不能直接推导穿越身份。\n"
)

_BEAT_RULES = (
    "节拍参考：发育（纯日常，让玩家安心积累）/互动（完整回应对话或当前事务）/"
    "推进（只推进玩家主动追求的现有目标）/收获（结算实打实的结果）。"
    "不要自动循环，不要为了节奏强行制造冲突或钩子；连续日常完全正常。"
    "裁定只授权回应玩家明确做出的这一步，不授权叙事者代替玩家继续下一步；"
    "若即将出现选择、转场、承诺、点击、接受或拒绝，scene_note必须要求在该节点前停下。"
    "玩家忽略钩子或拒绝任务时，应尊重该方向并继续模拟世界，"
    "禁止设计换皮事件把玩家强拉回原路线。\n"
)

# 检定门槛写得这么死，是因为模型天然倾向于「为了戏剧性」而掷骰。
# 每一次不必要的检定都在把日常变成闯关。
_CHECK_RULES = (
    "检定门槛必须严格：角色卡未揭示时risky必须为false。角色卡已揭示后，"
    "只有同时满足①结果确实不确定；②存在正在抵抗的对手、危险环境或技术难题；"
    "③失败会立即产生与成功不同的实质后果，risky才为true。"
    "普通走路、观察可见物、正常交谈、查阅已掌握资料、吃饭休息、无压力的本职工作一律false。"
    "不要为了制造戏剧而检定。\n"
    "若玩家输入是【时间跳跃】请求：risky填false，beat填发育，"
    'scene_note写"用蒙太奇概括跳过的时间并结算收获"。\n'
)

_OUTPUT_SHAPE = (
    '只输出一个JSON对象，不要任何其他文字:{"spoken":布尔值,"risky":布尔值,'
    '"action":"若检定，用八字内概括受检行动",'
    '"attr":"若risky，从现有属性中原样选择一个，否则空字符串",'
    '"skill":"若某项现有技能直接适用则原样填写，否则空字符串",'
    '"talent":"若某项现有天赋直接适用则原样填写，否则空字符串",'
    '"dc":难度数字(简单40,普通55,困难70,极难85),'
    '"npc":"直接互动NPC态度或空字符串","focus":"直接回应或结果",'
    '"beat":"发育|互动|推进|收获","scene_note":"本回合回答范围和停止点",'
    '"mainline":"仅玩家主动处理现有目标时填写，否则空字符串",'
    '"fail_cost":"失败的直接代价"}'
)


def build_director_prompt(
    *,
    player_input: str,
    game_state: dict[str, Any],
    story_tone: str = "",
    story_dna: str = "",
    outline: str = "",
    player_canon: dict[str, str] | None = None,
    premise_state: dict[str, Any] | None = None,
    prefs: dict[str, Any] | None = None,
    recent_messages: list[dict[str, Any]] | None = None,
) -> str:
    gs = game_state if isinstance(game_state, dict) else {}

    attrs = gs.get("attrs") or {}
    attr_text = (",".join(f"{k}={v}" for k, v in attrs.items())
                 if attrs else "未知（可自定合理属性名）")

    skills = gs.get("skills") or []
    skill_text = "、".join(
        f"{s.get('name')}({s.get('realm')},熟练{s.get('proficiency')}%,"
        f"系数{s.get('coefficient')}{',运转中' if s.get('active') else ''})"
        for s in skills if isinstance(s, dict)
    ) or "无"

    talents = gs.get("talents") or []
    talent_text = "、".join(str(x) for x in talents) or "无"

    npcs = gs.get("npcs") or {}
    npc_text = "；".join(
        f"{n}({(npcs[n] or {}).get('rel') or '?'},"
        f"态度{int((npcs[n] or {}).get('att') or 0)},"
        f"已知={'／'.join((npcs[n] or {}).get('knows') or []) or '无额外秘密'})"
        for n in list(npcs.keys())[-10:]
    ) or "无"

    recent = "\n".join(
        f"{'玩家' if m.get('role') == 'user' else '叙事'}: "
        + strip_blocks(str(m.get("content") or ""))[:400]
        for m in (recent_messages or [])[-4:]
    )

    return (
        "你是文字RPG的后台GM裁判。你不写剧情，只做冷静判定，玩家永远看不到你的输出。\n"
        f"本局基调:{story_tone or '未定'}——节拍判断与裁定的松紧要符合基调\n"
        f"本局最终有效设定（高于历史摘要与旧大纲）:{story_dna or '尚未建立'}\n"
        f"当前跨世界迁移状态:{_premise_directive(premise_state or {}, prefs or {}) or '非穿越路线'}\n"
        f"当前隐藏大纲:{outline or '无'}\n"
        f"角色属性:{attr_text}\n"
        f"角色技能:{skill_text}\n"
        f"角色天赋:{talent_text}\n"
        f"主角身份档案:{_canon_summary(player_canon or {}) or '尚无锁定字段'}\n"
        f"人物关系与各自知情:{npc_text}\n"
        f"最近剧情:\n{recent}\n\n"
        f"玩家本回合输入:{player_input}\n\n"
        + _AUTHORITY_RULES + _BEAT_RULES + _CHECK_RULES + _OUTPUT_SHAPE
    )


def strip_blocks(text: str) -> str:
    """去掉隐藏协议块——裁判要看的是剧情，不是模型的申报。"""
    import re
    out = str(text or "")
    for tag in ("大纲", "STATE", "SHEET_INIT"):
        out = re.sub(rf"【{tag}】[\s\S]*?【/{tag}】", "", out)
    return out


def parse_ruling(raw: str) -> dict | None:
    """
    从模型输出里挖出裁定 JSON。

    只做解析，不收紧取值——取值收紧目前在前端的回合编排里，
    而且规则和「直觉上该怎么收紧」不一样（比如属性名无效时回退到第一个属性，
    不是丢弃）。这次是提示词迁移，顺手改行为会让「搬完行为没变」这句话
    失去意义，也就没法用对拍验证。收紧要做，另起一次看得见的改动。

    返回 None 表示裁定没能完成，调用方按「本回合不做额外裁定」处理——
    那只是少一层约束，不会让状态出错。
    """
    import re

    match = re.search(r"\{[\s\S]*\}", str(raw or ""))
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
