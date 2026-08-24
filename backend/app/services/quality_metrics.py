"""叙事质量度量：把「玩起来怎么样」变成可复算的数字。

为什么需要
----------
到 2026-08-24 为止，这个项目有 388 个单元测试，全部在检查提示词的**结构**
（某句话在不在里面），没有一个在测叙事的**质量**。后果是每一轮都靠玩家
充当测试环境：他玩、他报告、我读日志、我改、他再玩。

代价很具体：详略那一版通过了全部测试、HTTP 也实测过，玩家玩下来第一句话
是「非常之无聊」。「实测过了」只证明字符串拼对了，不证明玩起来变好。

设计取舍
--------
玩家抱怨过的问题，大部分**不需要模型当裁判**——结构化数据里就有：
穿越用了几回合、连着几幕没冲突、同一个目标写了几遍、一张卡挂了几个回合。
这些是确定性的，可复算、无成本、不受裁判模型波动影响。

只有少数确实需要判断（这段正文好不好看），那部分留给后续的裁判层，
不放在这里。先把能确定算的算准。

**指标必须独立于提示词书写。**如果拿世界包原文当关键词去匹配正文，
测的只是「模型有没有复读提示词」，不是「世界有没有立起来」。所以下面
WORLD_MARKERS 是另写的一套判据，故意不引用 domain.worlds 的 flavor 字段。

验证方式
--------
指标可不可信，看它能不能把玩家**已经骂过**的那几局标出来。
tools/score_session.py 会跑历史导出做这件事，见 docs/QUALITY_METRICS.md。
"""
from __future__ import annotations

import json
import re
from typing import Any

# 一个世界「立起来了」的独立判据。
#
# 刻意不复用 worlds.py 的 flavor 字段：那是写给模型看的提示词，拿它来当
# 检测词表等于自己考自己。这里是从「玩家怎么判断这局像不像这个题材」
# 反推的，用词也不一样。
WORLD_MARKERS: dict[str, list[str]] = {
    "fantasy": ["公会", "魔法", "咒文", "精灵", "矮人", "兽人", "剑", "法杖",
                "金币", "酒馆", "冒险者", "魔物", "魔王", "骑士", "祭司"],
    "wuxia": ["内力", "招式", "门派", "客栈", "镖", "江湖", "掌门", "轻功", "剑法", "银两"],
    "xianxia": ["灵气", "境界", "筑基", "金丹", "丹药", "灵石", "宗门", "法器", "洞府", "修士"],
    "history": ["铜钱", "两银", "掌柜", "衙门", "赋税", "集市", "作坊", "行当", "户籍"],
    "modernlife": ["手机", "微信", "地铁", "外卖", "便利店", "房租", "工资", "加班", "电脑"],
    "occult": ["异常", "怪谈", "regulation", "规则", "组织", "收容", "异能"],
    "cyber": ["义体", "企业", "霓虹", "网络", "植入", "黑市", "信用点", "数据", "改装"],
    "space": ["飞船", "跃迁", "星系", "轨道", "殖民", "舱", "星港", "联盟"],
    "apocalypse": ["废土", "据点", "物资", "弹药", "感染", "辐射", "幸存者", "配给"],
    "horror": ["异常", "低语", "腐", "阴影", "失踪", "血", "不对劲", "寂静"],
}

# 专名从**事实库**里取，不从正文正则里取。
#
# 试过正则（中式地名尾字 + 前缀 2-3 字），在真实正文上精度惨不忍睹：
# 匹配出「半天到镇」「地址在城」「是榆树村」「她榆树村」——中文没有词边界，
# 词干必然切错；加频次门槛后又全军覆没（每个表面形式都不一样）。
# 它在剑与魔法那一局给出了正确结论，但**理由是错的**，那种指标比缺失更危险。
#
# 事实库里的条目是模型带上下文抽取并分好类的（[place]/[person]/[faction]），
# 精确得多。代价是**滞后一到两个回合**：刚在正文里出现的名字要下一回合
# 才进事实库，所以很短的对局可能一个都取不到。这是已知局限，不掩盖。
FACT_ENTITY = re.compile(r"\[(place|person|faction)\]\s*([^：:\n]{1,20})[：:]")
# 全中文、且以中式地名尾字结尾——在期望西式译名的世界里算违规。
CN_PLACE_NAME = re.compile(r"^[一-龥]{2,6}(村|镇|城|州|府|县|渡|关|坞|庄|铺|巷|坊)$")
# 期望使用西式译名的世界。
WESTERN_NAMING_WORLDS = {"fantasy", "space"}

# 连续多少幕没冲突算「走马观花」。和 story_planner.STAKES_QUIET_LIMIT 同源，
# 但这里刻意写死：指标不该跟着被测代码一起变，否则调宽阈值就能让指标变绿。
QUIET_STREAK_BAD = 3
# 从阈限开始到落地，占掉几个回合算「转移拖沓」。
#
# 测的是**转移本身**，不是从开局到落地的总长——玩家抱怨的是过程：
# 「戴个 VR 头显还在虚空里走半天」。那一局第 7 回合就落地了（总长不算长），
# 但阈限之后占了 4 个回合；他评价温和的那局只占了 3 个。
#
# ⚠️ 这个阈值只由两局标定（n=2），是全部指标里最弱的一条。手上只有两局
# 真正落了地的穿越，3 和 4 之间那条线基本就是照着这两个点画的。
# 攒够更多对局后重新标定；在那之前，它的判定要当线索而不是结论。
TRANSIT_SLOW_TURNS = 3
# 从来没落地的局，总回合数超过这个就算「永远不穿越」。
CROSSING_NEVER_TURNS = 8


def _strip_protocol(text: str) -> str:
    """去掉 STATE/大纲/选项这类协议块，只留玩家真正读到的正文。"""
    t = str(text or "")
    t = re.sub(r"【(?:STATE|SHEET_INIT|大纲|命名表|裁定|检定)】[\s\S]*?(?:【/(?:STATE|SHEET_INIT|大纲|命名表|裁定|检定)】|$)", "", t)
    t = re.sub(r"\n选项：[\s\S]*$", "", t)
    return t.strip()


def _scene_of(run: dict) -> dict:
    """从一次规划调用的输出里取场景卡。"""
    raw = run.get("output") or ""
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}
    scene = data.get("current_scene")
    return scene if isinstance(scene, dict) else {}


def score_session(monitor: dict[str, Any], world_id: str = "") -> dict[str, Any]:
    """给一次导出的 Agent 监控记录打分。

    monitor 是前端「导出 Agent 监控」得到的 JSON。
    """
    runs = [r for r in (monitor.get("runs") or []) if isinstance(r, dict)]
    narratives = sorted(
        [r for r in runs if r.get("agent") == "narrative"],
        key=lambda r: (r.get("turn") if isinstance(r.get("turn"), int) else 0),
    )
    planners = sorted(
        [r for r in runs if r.get("agent") == "planner"],
        key=lambda r: (r.get("turn") if isinstance(r.get("turn"), int) else 0),
    )
    scenes = [(r.get("turn") or 0, _scene_of(r)) for r in planners]
    scenes = [(t, s) for t, s in scenes if s]

    turns = len(narratives)
    wid = world_id or str(monitor.get("world_id") or "")

    # 迁移阶段轨迹。落地回合决定了下面几个指标该从哪里开始算。
    phases = [(t, s.get("premise_phase")) for t, s in scenes]
    phases = [(t, p) for t, p in phases if isinstance(p, int)]
    is_migration = bool(phases)
    landed_turn = next((t for t, p in phases if p >= 4), None)
    threshold_turn = next((t for t, p in phases if p >= 2), None)

    # 转移拖了几个回合：从阈限到落地。
    #
    # 玩家抱怨的是过程本身（「戴个 VR 头显还在虚空里走半天」），不是总长——
    # 那一局第 8 回合就落地了，总长不算长，但阈限之后拖了 5 个回合。
    transit_turns = None
    if threshold_turn is not None and landed_turn is not None:
        transit_turns = max(0, landed_turn - threshold_turn + 1)

    # 世界是否立起来：只看**该世界的戏**。
    #
    # 穿越局前期在原世界，本来就不该出现内力门派。此前不分段落地算，
    # 结果五局武侠全部报「0%」——一个永远报警的指标等于没有指标。
    if is_migration and landed_turn is None:
        scored = []          # 还没到那个世界，无从评判
    elif is_migration:
        scored = [r for r in narratives if (r.get("turn") or 0) >= landed_turn]
    else:
        scored = narratives
    body = "\n".join(_strip_protocol(r.get("output") or "") for r in scored)
    full_body = "\n".join(_strip_protocol(r.get("output") or "") for r in narratives)

    markers = WORLD_MARKERS.get(wid, [])
    hit = sorted({m for m in markers if m in body}) if body else []
    flavor_rate = (len(hit) / len(markers)) if (markers and body) else None

    # 专名取自事实库的结构化条目，不用正则切正文（理由见 FACT_ENTITY 注释）。
    entities: dict[str, set[str]] = {"place": set(), "person": set(), "faction": set()}
    for r in narratives:
        text = r.get("input") or ""
        k = text.find("【已确立的设定")
        if k < 0:
            continue
        for m in FACT_ENTITY.finditer(text[k:k + 20000]):
            entities[m.group(1)].add(m.group(2).strip())
    cn_names: list[str] = []
    if wid in WESTERN_NAMING_WORLDS:
        cn_names = sorted(n for n in entities["place"] if CN_PLACE_NAME.match(n))

    # 连续无冲突的最长段
    quiet = cur = 0
    for _, s in scenes:
        if str(s.get("conflict") or "").strip():
            cur = 0
        else:
            cur += 1
            quiet = max(quiet, cur)

    # 一张卡挂了几个回合
    spans: list[int] = []
    ids = [(t, str(s.get("id") or "")) for t, s in scenes]
    for i, (t, _sid) in enumerate(ids):
        nxt = ids[i + 1][0] if i + 1 < len(ids) else turns
        spans.append(max(0, nxt - t))

    narration = {}
    for _, s in scenes:
        k = str(s.get("narration") or "scene")
        narration[k] = narration.get(k, 0) + 1

    forced = sum(1 for _, s in scenes if s.get("premise_phase_forced") is True)

    lengths = [len(_strip_protocol(r.get("output") or "")) for r in narratives]

    return {
        "turns": turns,
        "scenes": len(scenes),
        "world_id": wid,
        "body_chars": len(full_body),
        # 世界身份（穿越局只统计落地之后的回合）
        "flavor_hit_rate": round(flavor_rate, 3) if flavor_rate is not None else None,
        "flavor_hits": hit,
        "flavor_scored_turns": len(scored),
        "entities": {k: sorted(v) for k, v in entities.items()},
        "cn_place_names_in_western_world": cn_names,
        # 赌注
        "quiet_streak_max": quiet,
        "scenes_without_conflict": sum(1 for _, s in scenes if not str(s.get("conflict") or "").strip()),
        # 迁移
        "is_migration": is_migration,
        "crossing_turn": landed_turn,
        "threshold_turn": threshold_turn,
        "transit_turns": transit_turns,
        "forced_takeovers": forced,
        # 节奏
        "scene_span_max": max(spans) if spans else 0,
        "scene_span_avg": round(sum(spans) / len(spans), 2) if spans else 0,
        "narration_mix": narration,
        "narrative_chars_avg": round(sum(lengths) / len(lengths)) if lengths else 0,
    }


def verdicts(m: dict[str, Any]) -> list[str]:
    """把数字翻成「这局哪里不对」。空列表表示没有已知问题被触发。"""
    out: list[str] = []
    if m["quiet_streak_max"] >= QUIET_STREAK_BAD:
        out.append(f"走马观花：连续 {m['quiet_streak_max']} 幕没有冲突")
    if m["is_migration"]:
        if m["crossing_turn"] is None:
            if m["turns"] > CROSSING_NEVER_TURNS:
                out.append(f"穿越从未发生（已进行 {m['turns']} 回合）")
        elif (m["transit_turns"] or 0) > TRANSIT_SLOW_TURNS:
            out.append(
                f"穿越转移拖沓：阈限在第 {m['threshold_turn']} 回合，"
                f"到第 {m['crossing_turn']} 回合才落地，占了 {m['transit_turns']} 个回合"
            )
    if m["cn_place_names_in_western_world"]:
        out.append("西式世界出现中式地名：" + "、".join(m["cn_place_names_in_western_world"][:5]))
    if m["flavor_hit_rate"] is not None and m["flavor_hit_rate"] < 0.2:
        out.append(
            f"世界没立起来：落地后 {m['flavor_scored_turns']} 个回合里，"
            f"题材特征命中率仅 {m['flavor_hit_rate']:.0%}"
        )
    if m["scene_span_max"] >= 8:
        out.append(f"场景拖沓：一张卡挂了 {m['scene_span_max']} 个回合")
    return out
