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

from app.services.writer_output import normalize_writer_output

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

# 这些是可解释的诊断信号，不是“文风评分”。命中一次只说明正文使用了
# 高风险的回避表达，最终仍要结合玩家是否主动追问来判断。
MYSTERY_EVASION_PHRASES = (
    "你不该知道", "现在还不是时候", "别问", "他们已经来了",
    "你会后悔的", "这座城市不简单", "不能告诉你", "不方便说",
)


def _run_turn(run: dict[str, Any]) -> int:
    """兼容旧导出、当前前端导出和后端 AgentRun 的回合字段。"""
    for key in ("turn", "turnId", "turn_id"):
        value = run.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
    meta = run.get("meta")
    if isinstance(meta, dict):
        value = meta.get("turn", meta.get("turnId", meta.get("turn_id")))
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
    return 0


def _extract_option_count(text: str) -> int:
    """从正文末尾提取可见行动选项数量，不把普通编号正文误算进去。"""
    raw = str(text or "")
    structured = normalize_writer_output(raw)
    if structured is not None:
        return min(len(structured.options), 4)
    matches = list(re.finditer(r"(?:^|\n)[ \t]*(?:\*\*)?(?:选项|行动选项)[ \t]*[:：]?[ \t]*(?:\*\*)?[ \t]*\n", raw))
    if not matches:
        return 0
    tail = raw[matches[-1].end():]
    count = 0
    for line in tail.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.match(r"^(?:[1-4](?:[\.)、][ \t]*|[ \t]+)|\([1-4]\)[ \t]*)\S+", line):
            count += 1
            continue
        if re.match(r"^(?:或输入|自由输入)", line):
            break
        # 选项块之后出现普通正文，避免把后面的编号列表算进去。
        if count:
            break
    return min(count, 4)


def _strip_protocol(text: str) -> str:
    """去掉 STATE/大纲/选项这类协议块，只留玩家真正读到的正文。"""
    t = str(text or "")
    structured = normalize_writer_output(t)
    if structured is not None:
        t = structured.narrative
    t = re.sub(r"【(?:STATE|SHEET_INIT|大纲|命名表|裁定|检定)】[\s\S]*?(?:【/(?:STATE|SHEET_INIT|大纲|命名表|裁定|检定)】|$)", "", t)
    t = re.sub(r"\n选项：[\s\S]*$", "", t)
    return t.strip()


def _state_patch_signature(text: str) -> str:
    """取回合中程序可见的状态候选，供分叉比较使用。"""
    raw = str(text or "")
    structured = normalize_writer_output(raw)
    if structured is not None:
        return json.dumps(structured.state_patch, ensure_ascii=False, sort_keys=True)
    patches: list[Any] = []
    for match in re.finditer(r"【STATE】([\s\S]*?)【/STATE】", raw):
        try:
            value = json.loads(match.group(1).strip().strip("`").replace("json\n", "", 1))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            patches.append(value)
    return json.dumps(patches, ensure_ascii=False, sort_keys=True)


def _same_text(left: str, right: str) -> bool:
    """比较可见正文，忽略协议块和多余空白。"""
    def compact(value: str) -> str:
        return re.sub(r"\s+", "", _strip_protocol(value))
    return compact(left) == compact(right)


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
        key=_run_turn,
    )
    planners = sorted(
        [r for r in runs if r.get("agent") == "planner"],
        key=_run_turn,
    )
    scenes = [(_run_turn(r), _scene_of(r)) for r in planners]
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
        scored = [r for r in narratives if _run_turn(r) >= landed_turn]
    else:
        scored = narratives
    body = "\n".join(_strip_protocol(r.get("output") or "") for r in scored)
    full_body = "\n".join(_strip_protocol(r.get("output") or "") for r in narratives)

    option_counts = [_extract_option_count(r.get("output") or "") for r in narratives]
    valid_option_counts = [n for n in option_counts if n > 0]
    option_complete_rate = (
        sum(1 for n in option_counts if 2 <= n <= 4) / len(option_counts)
        if option_counts else None
    )
    mystery_turns = sum(
        1 for r in narratives
        if any(phrase in _strip_protocol(r.get("output") or "") for phrase in MYSTERY_EVASION_PHRASES)
    )

    # 因果连续的确定性下限：除开局幕外，每张卡都应给出可见因果桥；
    # 相邻场景不应重复同一个 purpose。它们不是剧情好坏评分，只是抓住
    # “突然开始”和“同一件事反复演”的低成本信号。
    causal_rows = scenes[1:]
    causal_missing = sum(
        1 for _, scene in causal_rows
        if not str(scene.get("causal_bridge") or "").strip()
    )
    repeated_purpose_turns = 0
    previous_purpose = ""
    for turn, scene in scenes:
        purpose = re.sub(r"\s+", "", str(scene.get("purpose") or ""))
        if purpose and purpose == previous_purpose:
            repeated_purpose_turns += 1
        if purpose:
            previous_purpose = purpose

    # 记忆可解释性：pipeline 元数据里的 trace 必须能回答“为什么把这条
    # 记忆放进上下文”。没有 trace 的旧导出返回 None，不冒充失败。
    memory_trace_rows = 0
    memory_trace_included = 0
    memory_trace_turns = 0
    for run in runs:
        meta = run.get("meta")
        context = meta.get("memoryContext") if isinstance(meta, dict) else None
        trace = context.get("trace") if isinstance(context, dict) else None
        if not isinstance(trace, list):
            continue
        memory_trace_turns += 1
        for item in trace:
            if not isinstance(item, dict):
                continue
            memory_trace_rows += 1
            if item.get("included") is True and str(item.get("reason") or "").strip():
                memory_trace_included += 1
    memory_trace_coverage = (
        memory_trace_included / memory_trace_rows if memory_trace_rows else None
    )

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
        "option_counts": option_counts,
        "option_count_min": min(valid_option_counts) if valid_option_counts else 0,
        "option_complete_rate": round(option_complete_rate, 3) if option_complete_rate is not None else None,
        "option_missing_turns": sum(1 for n in option_counts if n < 2),
        "mystery_evasion_turns": mystery_turns,
        "mystery_evasion_rate": round(mystery_turns / turns, 3) if turns else None,
        "causal_bridge_missing_turns": causal_missing,
        "causal_bridge_missing_rate": round(causal_missing / len(causal_rows), 3) if causal_rows else None,
        "repeated_purpose_turns": repeated_purpose_turns,
        "memory_trace_turns": memory_trace_turns,
        "memory_trace_rows": memory_trace_rows,
        "memory_trace_included": memory_trace_included,
        "memory_trace_coverage": round(memory_trace_coverage, 3) if memory_trace_coverage is not None else None,
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


def _option_signature(text: str) -> tuple[str, ...]:
    """取选项内容而不把正文/协议带进分叉比较。"""
    structured = normalize_writer_output(str(text or ""))
    if structured is not None:
        return tuple(structured.options)
    raw = str(text or "")
    matches = list(re.finditer(r"(?:^|\n)[ \t]*(?:\*\*)?(?:选项|行动选项)[ \t]*[:：]?[ \t]*(?:\*\*)?[ \t]*\n", raw))
    if not matches:
        return ()
    values: list[str] = []
    for line in raw[matches[-1].end():].splitlines():
        line = line.strip()
        if not line:
            continue
        option = re.match(r"^(?:[1-4](?:[.)、][ \t]*|[ \t]+)|\([1-4]\)[ \t]*)(.+)$", line)
        if option:
            values.append(re.sub(r"\s+", " ", option.group(1)).strip())
            continue
        if re.match(r"^(?:或输入|自由输入)", line) or values:
            break
    return tuple(values[:4])


def compare_branch_sessions(
    left: dict[str, Any], right: dict[str, Any], world_id: str = "",
) -> dict[str, Any]:
    """比较同一初始局面的两条玩家输入分支。

    这是确定性“玩家影响”下限：它不判断哪条写得更好，只回答玩家输入不同后，
    正文、选项或状态候选是否真的产生了差异。没有共同回合或没有可识别的输入时，
    返回 ``effective=None``，不把缺数据误报成分支失败。
    """
    def by_agent(monitor: dict[str, Any], agent: str) -> dict[int, dict[str, Any]]:
        out: dict[int, dict[str, Any]] = {}
        for run in monitor.get("runs") or []:
            if not isinstance(run, dict) or run.get("agent") != agent:
                continue
            turn = _run_turn(run)
            out[turn] = run
        return out

    left_n = by_agent(left, "narrative")
    right_n = by_agent(right, "narrative")
    common = sorted(set(left_n) & set(right_n))
    left_pipeline = by_agent(left, "pipeline")
    right_pipeline = by_agent(right, "pipeline")
    input_diffs = [
        turn for turn in common
        if str((left_pipeline.get(turn) or {}).get("input") or "")
        != str((right_pipeline.get(turn) or {}).get("input") or "")
    ]
    branch_turn = min(input_diffs) if input_diffs else None
    compared = [turn for turn in common if branch_turn is None or turn >= branch_turn]
    narrative_diffs = [
        turn for turn in compared
        if not _same_text(left_n[turn].get("output") or "", right_n[turn].get("output") or "")
    ]
    option_diffs = [
        turn for turn in compared
        if _option_signature(left_n[turn].get("output") or "")
        != _option_signature(right_n[turn].get("output") or "")
    ]
    state_diffs = [
        turn for turn in compared
        if _state_patch_signature(left_n[turn].get("output") or "")
        != _state_patch_signature(right_n[turn].get("output") or "")
    ]
    all_diffs = sorted(set(narrative_diffs) | set(option_diffs) | set(state_diffs))
    result: dict[str, Any] = {
        "world_id": world_id or str(left.get("world_id") or right.get("world_id") or ""),
        "shared_turns": common,
        "branch_turn": branch_turn,
        "different_input_turns": input_diffs,
        "compared_turns": compared,
        "narrative_divergent_turns": narrative_diffs,
        "option_divergent_turns": option_diffs,
        "state_divergent_turns": state_diffs,
        "first_divergence_turn": min(all_diffs) if all_diffs else None,
        "effective": bool(all_diffs) if branch_turn is not None and compared else None,
        "left": score_session(left, world_id),
        "right": score_session(right, world_id),
    }
    verdict: list[str] = []
    if branch_turn is not None and compared and not all_diffs:
        verdict.append("玩家分支未产生可检测差异：正文、选项和状态候选均相同")
    if branch_turn is None and common:
        verdict.append("未识别到两条分支的不同玩家输入，无法判断玩家影响")
    if not common:
        verdict.append("两条记录没有共同回合，无法比较分支")
    result["verdicts"] = verdict
    return result


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
    if m.get("option_complete_rate") is not None and m["turns"] >= 3 and m["option_complete_rate"] < 0.7:
        out.append(f"行动选项不完整：仅 {m['option_complete_rate']:.0%} 的回合提供 2-4 个有效选项")
    if m.get("mystery_evasion_rate") is not None and m["turns"] >= 3 and m["mystery_evasion_rate"] >= 0.25:
        out.append(f"谜语人信号偏高：{m['mystery_evasion_rate']:.0%} 的回合出现回避表达")
    if m.get("causal_bridge_missing_rate") is not None and m["causal_bridge_missing_rate"] > 0.4:
        out.append(f"因果桥缺失：{m['causal_bridge_missing_rate']:.0%} 的后续场景没有说明为何现在发生")
    if m.get("repeated_purpose_turns", 0) >= 2:
        out.append(f"场景目的重复：连续规划中有 {m['repeated_purpose_turns']} 次重复上一幕目的")
    if m.get("memory_trace_coverage") is not None and m["memory_trace_coverage"] < 0.8:
        out.append(f"记忆召回不可解释：仅 {m['memory_trace_coverage']:.0%} 的召回条目带有纳入理由")
    return out
