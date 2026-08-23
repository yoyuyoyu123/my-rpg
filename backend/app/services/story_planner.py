"""剧情规划 Agent：把长篇意图压成短期可执行的场景卡。

这里采用三个能直接改善项目体验的方法：
1. 事件节点部分有序：只声明前置条件，不锁死玩家路线；
2. 规划与文案分离：规划器决定因果，写手只写当前场景；
3. 结构化校验：模型的 JSON 先清洗、限额、校验，再进入存档。
"""
from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from app.domain.worlds import WORLDS
from app.schemas.story import StoryPlanContext, StoryRuntime
from app.services.prompt_builder import premise_stall_note


# 两段 purpose 的字符二元组重合度超过这个比例就算「实质相同」。
#
# 阈值照 2026-08-22 那局的真实卡片标定：
#   原样重写的两幕      1.000
#   换皮但同目标的两幕  0.567   ← 必须抓到，是最常见的形态
#   真正换了目标        0.139 / 0.011
# 阳性最低 0.567、阴性最高 0.139，中间是空的。取 0.45 让两侧都有余量——
# 贴着 0.55 设只剩 0.017 的间隙，换个说法就漏了。
#
# 局限：这是词面重合，抓不到「为穿越逼近留下因果桥」和「将迁移推进到逼近」
# 这种换了说法的同一目标（实测只有 0.139）。语义重复靠提示词里回显上一幕
# 目标原文来兜——那条是无条件生效的，不依赖这个检测器。
PURPOSE_REPEAT_RATIO = 0.45
# 连续几次目标重复就升级措辞。
PURPOSE_REPEAT_ESCALATE = 2


def _bigrams(text: str) -> set[str]:
    # 中文没有空格分词，按字符二元组比对足够稳，也不必引入分词依赖。
    s = re.sub(r"[\s，。、；：,.;:「」【】()（）]", "", str(text or ""))
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _text_overlap(a: str, b: str) -> float:
    """两段文字的 Jaccard 重合度，0-1。"""
    ga, gb = _bigrams(a), _bigrams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def scene_repeat_note(count: int) -> str:
    """把「场景原地打转」回灌进下一次规划提示词。

    和迁移停滞一样，光在规则里写「不要重复」是不够的——模型看不到自己
    上一幕做了什么判断。必须把观测到的事实摆到它面前。
    """
    if count <= 0:
        return ""
    if count >= PURPOSE_REPEAT_ESCALATE:
        return (
            f"【场景原地打转·严重】最近 {count} 幕的 purpose 实质相同，故事没有前进。"
            "这不是节奏慢，是同一件事被反复重写。本幕**必须**把那个目标当作**已经完成的既成事实**"
            "写进 situation 与 causal_bridge，purpose 换成它之后的下一件事，"
            "并把停止点放在新目标兑现之后。禁止再用「让玩家对X做出反应」当作本幕的作用。\n\n"
        )
    return (
        "【场景原地打转】本幕 purpose 与上一幕实质相同，说明上一幕的停止点设在了目标兑现之前。"
        "这一幕请让那个目标真正落地，或者直接把它当既成事实、换成下一个目标。\n\n"
    )


def _json_object(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
    if fenced:
        text = fenced.group(1).strip()
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            value, _ = decoder.raw_decode(text[match.start():])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue
    raise ValueError("规划模型没有返回可解析的 JSON 对象")


def _clean_list(value: Any, limit: int, chars: int = 180) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        s = str(item or "").strip()[:chars]
        key = s.casefold()
        if s and key not in seen:
            out.append(s)
            seen.add(key)
        if len(out) >= limit:
            break
    return out


def parse_story_runtime(
    raw: str,
    previous: dict[str, Any],
    turn: int,
    reason: str,
    premise_state: dict[str, Any] | None = None,
) -> tuple[StoryRuntime, list[str]]:
    """解析并收紧模型输出，避免规划数据无限膨胀。"""
    try:
        data = _json_object(raw)
    except ValueError as exc:
        raise ValueError(f"剧情规划格式错误：{exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("剧情规划必须是 JSON 对象")

    warnings: list[str] = []
    old_revision = int((previous or {}).get("revision") or 0)
    data["version"] = 1
    data["revision"] = max(old_revision + 1, int(data.get("revision") or 1))
    data["last_planned_turn"] = turn
    data["plan_reason"] = reason
    data["premise"] = str(data.get("premise") or "").strip()[:500]

    threads = data.get("threads") if isinstance(data.get("threads"), list) else []
    if len(threads) > 3:
        warnings.append("规划线超过 3 条，已截断")
    cleaned_threads: list[dict[str, Any]] = []
    ids: set[str] = set()
    for i, raw_thread in enumerate(threads[:3]):
        if not isinstance(raw_thread, dict):
            continue
        item = dict(raw_thread)
        tid = str(item.get("id") or f"thread-{i + 1}").strip()[:48]
        if tid in ids:
            tid = f"{tid}-{i + 1}"
            warnings.append("重复剧情线 id 已改名")
        ids.add(tid)
        item["id"] = tid
        for key in ("title", "kind", "public_goal", "private_cause", "why_now", "player_connection"):
            item[key] = str(item.get(key) or "").strip()[:320]
        item["established_clues"] = _clean_list(item.get("established_clues"), 8)
        item["open_questions"] = _clean_list(item.get("open_questions"), 6)
        beats = item.get("beats") if isinstance(item.get("beats"), list) else []
        if len(beats) > 4:
            warnings.append(f"剧情线 {tid} 的节点超过 4 个，已截断")
        clean_beats: list[dict[str, Any]] = []
        for j, raw_beat in enumerate(beats[:4]):
            if not isinstance(raw_beat, dict):
                continue
            beat = dict(raw_beat)
            beat["id"] = str(beat.get("id") or f"{tid}-beat-{j + 1}").strip()[:64]
            for key in ("label", "purpose", "activation_condition"):
                beat[key] = str(beat.get(key) or "").strip()[:240]
            beat["prerequisites"] = _clean_list(beat.get("prerequisites"), 5, 100)
            beat["setup"] = _clean_list(beat.get("setup"), 5)
            clean_beats.append(beat)
        item["beats"] = clean_beats
        cleaned_threads.append(item)
    data["threads"] = cleaned_threads

    scene = data.get("current_scene")
    if not isinstance(scene, dict):
        # 模型偶尔只回 threads 而漏掉 current_scene。整份丢弃的代价太大：
        # 这一回合会退回兼容模式，场景卡停在上一版，而线程更新也白跑了。
        # 能捡回来就捡：优先复用上一版场景卡（剧情至少不会跳），
        # 实在没有再报错。
        prev_scene = (previous or {}).get("current_scene")
        if isinstance(prev_scene, dict) and prev_scene.get("id"):
            scene = dict(prev_scene)
            warnings.append("规划器没有返回 current_scene，已沿用上一版场景卡")
        else:
            raise ValueError("剧情规划缺少 current_scene")
    scene = dict(scene)
    for key in ("id", "title", "situation", "purpose", "causal_bridge"):
        scene[key] = str(scene.get(key) or "").strip()[:500]
    if not scene["id"]:
        scene["id"] = f"scene-{turn}-{data['revision']}"
    scene["active_thread_ids"] = [x for x in _clean_list(scene.get("active_thread_ids"), 3, 48) if x in ids]
    intents = scene.get("participant_intents") if isinstance(scene.get("participant_intents"), dict) else {}
    scene["participant_intents"] = {
        str(k).strip()[:60]: str(v).strip()[:240]
        for k, v in list(intents.items())[:8] if str(k).strip() and str(v).strip()
    }
    scene["available_information"] = _clean_list(scene.get("available_information"), 10)
    scene["allowed_developments"] = _clean_list(scene.get("allowed_developments"), 8)
    scene["causal_event_ids"] = _clean_list(scene.get("causal_event_ids"), 8, 64)
    scene["affordances"] = _clean_list(scene.get("affordances"), 8)
    # 旧规划器只有 allowed_developments；读旧存档时自动升级成 affordances。
    if not scene["affordances"]:
        scene["affordances"] = list(scene["allowed_developments"])
    if not scene["allowed_developments"]:
        scene["allowed_developments"] = list(scene["affordances"])
    scene["forbidden"] = _clean_list(scene.get("forbidden"), 10)
    scene["soft_commitment_ids"] = _clean_list(scene.get("soft_commitment_ids"), 8, 64)
    for key, default in (("pressure_budget", 1), ("mystery_budget", 0)):
        try:
            scene[key] = max(0, min(4, int(scene.get(key, default))))
        except (TypeError, ValueError):
            scene[key] = default
    narration = str(scene.get("narration") or "").strip().lower()
    scene["narration"] = narration if narration in ("scene", "summary") else "scene"
    scene["summary_target"] = str(scene.get("summary_target") or "").strip()[:300]
    if scene["narration"] == "summary" and not scene["summary_target"]:
        # 略写却没说要跨过什么，写手无从下手，只能又开始逐步描写。
        # 退回详写比给一个空目标安全。
        warnings.append("略写场景缺少 summary_target，已按详写处理")
        scene["narration"] = "scene"

    scene["stop_points"] = _clean_list(scene.get("stop_points"), 6)

    # 目标重复检测：新 purpose 与上一幕实质相同，说明上一幕没落地。
    prev_scene = (previous or {}).get("current_scene")
    prev_purpose = str((prev_scene or {}).get("purpose") or "") if isinstance(prev_scene, dict) else ""
    if prev_purpose and _text_overlap(scene["purpose"], prev_purpose) >= PURPOSE_REPEAT_RATIO:
        data["scene_repeat_count"] = int((previous or {}).get("scene_repeat_count") or 0) + 1
        warnings.append(
            f"本幕 purpose 与上一幕实质相同（已连续 {data['scene_repeat_count']} 次），"
            "多半是上一幕的停止点设在了 purpose 兑现之前"
        )
    else:
        data["scene_repeat_count"] = 0

    ps = premise_state if isinstance(premise_state, dict) else {}
    try:
        _phase_now = max(0, min(5, int(ps.get("phase", 0))))
    except (TypeError, ValueError):
        _phase_now = 0
    # 迁移进行中（已离开原世界日常、尚未落地）的幕要短。
    #
    # 平时视野下限是 turn+4：实测一局 17 回合触发 8 次规划（间隔 3,2,2,2,3,2,2），
    # 回合 3 和回合 5 产出的 purpose 一字不差——模型不管模板给什么都回填很小的值，
    # 每两回合重规划一次既烧钱又在反复固化没兑现的 purpose。
    #
    # 但阶段是按「幕」推进的，所以幕长直接乘进穿越耗时：跨过去要 4 幕，
    # 每幕 4 回合就是 16 回合起步，玩家的抱怨正是这个数。迁移途中的幕本来
    # 就该是决定性的短镜头，给 turn+2；原世界日常和落地之后仍用 turn+4。
    migrating = ps.get("kind") == "transmigration" and 1 <= _phase_now <= 4
    floor_gap = 2 if migrating else 4
    requested_horizon = int(scene.get("refresh_after_turn") or turn + floor_gap)
    scene["refresh_after_turn"] = max(turn + floor_gap, min(turn + 8, requested_horizon))

    # 迁移阶段：规划器可以自由下调；详写一次上调一级，略写可上调两级。
    #
    # 为什么把规划器当主要判据：正则证据检测（premiseEvidence）只认得
    # 「游戏弹窗/停服/VR」那一类路线的措辞。实测一局召唤路线，第 0 回合就
    # 出现了淡蓝色光点这个明确征兆，正则一个都匹配不上，阶段在 0 停了九回合。
    # 规划器读的是真实叙事，对召唤、神明、重生这些路线它是唯一识别得了的。
    #
    # 两个方向的风险不对称，所以规则也不对称：
    #   下调 —— 发现程序阶段虚高（曾被空转的计时器冲坏），采纳。
    #   上调一级 —— 观察到真实推进，采纳。
    #   跳好几级 —— 基本是模型在赶进度，玩家还在原世界就被宣布已抵达，限制。
    if ps.get("kind") == "transmigration":
        current_phase = _phase_now
        proposed = scene.get("premise_phase")
        try:
            proposed_phase = None if proposed is None else max(0, min(5, int(proposed)))
        except (TypeError, ValueError):
            proposed_phase = None

        # 略写的一幕明确覆盖「整段过程」，本来就跨得比详写远：阈限之后的
        # 转移途中与首次落地是同一段过程，硬拆成两幕就是之前那种「每回合
        # 换个感官细节重复同一件事」。所以略写允许一次前进两级。
        # 仍然不给更多：0→5 一张卡搞定就是「玩家在阳台撸猫时被宣布已抵达」，
        # 那个失败模式实测过一次了。
        max_step = 2 if scene.get("narration") == "summary" else 1
        if proposed_phase is None:
            scene["premise_phase"] = current_phase
        elif proposed_phase > current_phase + max_step:
            # 一次跳好几级基本是模型在赶进度，玩家还在原世界就被宣布已抵达
            warnings.append(
                f"规划器想从阶段 {current_phase} 直接跳到 {proposed_phase}，"
                f"已限制为只前进 {max_step} 级"
            )
            scene["premise_phase"] = current_phase + max_step
        elif proposed_phase > current_phase:
            # 允许前进一级：正则证据只认得「游戏弹窗」那一类路线，
            # 召唤、神明、重生等路线的征兆它一个都匹配不上。规划器读的是
            # 真实叙事，是这些路线唯一能识别推进的东西。
            warnings.append(f"规划器判定叙事已推进到阶段 {proposed_phase}")
            scene["premise_phase"] = proposed_phase
        elif proposed_phase < current_phase:
            warnings.append(
                f"规划器判定叙事仍处于阶段 {proposed_phase}，"
                f"低于程序记录的 {current_phase}，已按叙事回退"
            )
            scene["premise_phase"] = proposed_phase
    data["current_scene"] = scene

    try:
        return StoryRuntime.model_validate(data), warnings
    except ValidationError as exc:
        raise ValueError("剧情规划字段不合法：" + str(exc).splitlines()[0]) from exc


def state_digest(game_state: dict[str, Any]) -> str:
    """
    给规划器一份精简状态，而不是整坨 JSON 硬切。

    为什么不能直接 json.dumps 再截断：
        账本 ledger 是审计日志，最多 300 条，占整个状态 JSON 的八成以上，
        而且在 key 顺序里排在 loc 和 npcs 前面。硬切到几千字符的结果是
        规划器读满了「物品21 增加 1」的流水，却不知道玩家此刻在哪、认识谁——
        偏偏这两样正是规划下一幕最需要的。
        这个坑只在玩久了才发作（账本要先攒够几百条），单元测试发现不了。

    所以按用途挑字段，并且逐段限额：任何一段都不能把别的段挤出去。
    """
    gs = game_state if isinstance(game_state, dict) else {}
    parts: list[str] = []

    # 位置和人物关系最优先——它们决定下一幕能发生什么
    if gs.get("loc"):
        parts.append("位置:" + str(gs["loc"])[:80])

    npcs = gs.get("npcs")
    if isinstance(npcs, dict) and npcs:
        rows = []
        for name in list(npcs.keys())[-16:]:
            v = npcs.get(name) or {}
            knows = v.get("knows") if isinstance(v.get("knows"), list) else []
            rows.append(
                f"{str(name)[:40]}({str(v.get('rel') or '?')[:20]},态度{v.get('att', 0)}"
                + (f",{str(v.get('note'))[:40]}" if v.get("note") else "")
                + (f",已知={'／'.join(str(k)[:60] for k in knows[:6])}" if knows else "")
                + ")"
            )
        parts.append("人物关系(各自独立，不得互相共享):" + "；".join(rows))

    if not gs.get("revealed"):
        parts.append("角色卡尚未揭示：没有数值，不要按属性规划难度")
    else:
        attrs = gs.get("attrs")
        if isinstance(attrs, dict) and attrs:
            parts.append("属性:" + "/".join(f"{k}{v}" for k, v in list(attrs.items())[:12]))
        res = gs.get("res")
        if isinstance(res, dict) and res:
            parts.append("资源:" + "/".join(f"{k}{v}" for k, v in list(res.items())[:12]))

    talents = gs.get("talents")
    if isinstance(talents, list) and talents:
        parts.append("天赋:" + "、".join(str(x)[:30] for x in talents[:12]))

    # 物品和技能只要名字：规划器关心「有没有」，不关心熟练度和描述
    skills = gs.get("skills")
    if isinstance(skills, list) and skills:
        parts.append("技能:" + "、".join(
            f"{str(s.get('name'))[:30]}({str(s.get('realm') or '')[:12]})"
            if isinstance(s, dict) else str(s)[:30] for s in skills[:24]))

    inv = gs.get("inv")
    if isinstance(inv, list) and inv:
        parts.append("背包:" + "、".join(
            f"{str(x.get('name'))[:30]}×{x.get('quantity', 1)}"
            if isinstance(x, dict) else str(x)[:30] for x in inv[:30]))

    # ledger 是审计日志，规划器用不上，不进来
    return "｜".join(parts) if parts else "（尚无状态）"


def build_story_plan_prompt(ctx: StoryPlanContext) -> str:
    world = WORLDS.get(ctx.world_id)
    world_text = ctx.custom_world_prompt if world is None else world.prompt
    if not world_text:
        raise ValueError("找不到当前世界设定")
    recent = "\n".join(
        f"{m.get('role', '')}: {str(m.get('content') or '')[:1800]}"
        for m in ctx.recent_messages[-10:]
    )
    previous = json.dumps(ctx.story_runtime or {}, ensure_ascii=False, separators=(",", ":"))
    # 停滞加压：场景卡永远不会自己决定穿越，所以停久了必须由程序提醒规划器
    stall = premise_stall_note(ctx.premise_state or {})
    # 加压要放在紧挨规则区的位置。之前它挂在数据区最底部的【迁移状态】后面，
    # 隔着世界设定、状态、事实、上一版规划、最近对话一大段——一行字对抗
    # 顶部四条结构性的「不要强推」规则，必然输。实测规划器连着四次收到
    # 「严重停滞」仍然规划夜班公交站、回家路上这类纯日常场景。
    stall_note = (stall + "\n\n") if stall else ""

    # 原地打转加压，和停滞加压同理：放在规则区旁边，且必须回显上一幕的
    # purpose 原文——模型看不到自己上次写了什么，只讲抽象规则约束不住它。
    runtime = ctx.story_runtime or {}
    prev_scene = runtime.get("current_scene")
    prev_purpose = str((prev_scene or {}).get("purpose") or "").strip() if isinstance(prev_scene, dict) else ""
    repeat_note = scene_repeat_note(int(runtime.get("scene_repeat_count") or 0))
    if prev_purpose:
        repeat_note += (
            f"【上一幕的目标】{prev_purpose[:300]}\n"
            "它兑现了吗？兑现了就换新目标；没兑现说明上一幕停止点设早了，"
            "把它当既成事实写进 situation，purpose 换成下一件事。两种情况都不许原样重写。\n\n"
        )

    state = state_digest(ctx.game_state or {})
    canon = json.dumps(ctx.player_canon or {}, ensure_ascii=False, separators=(",", ":"))
    premise = json.dumps(ctx.premise_state or {}, ensure_ascii=False, separators=(",", ":"))
    migration_note = ""
    if isinstance(ctx.premise_state, dict) and ctx.premise_state.get("kind") == "transmigration":
        try:
            phase = max(0, min(5, int(ctx.premise_state.get("phase", 0))))
        except (TypeError, ValueError):
            phase = 0
        fast = ctx.premise_state.get("fast") is True
        stage_names = {
            0: "原世界生活/第一项眼前刺激",
            1: "逼近与回应",
            2: "阈限事件",
            3: "转移途中",
            4: "首次落地",
            5: "已抵达",
        }
        migration_note = f"""
【穿越规划专用约束】
本局穿越是已经确定的故事前提，不是可有可无的支线。故事**当前**处在迁移阶段={phase}（{stage_names[phase]}）。
premise_phase 填的是「**本幕结束时**故事所处的阶段」，不是本幕开始时的阶段。本幕让迁移前进了，就填更大的数；没前进就填 {phase}。阶段由你判断，程序采纳。
**每一幕都要让当前阶段结束，而不是为它铺垫。**下面写的是每个阶段该在本幕内**完成**什么：
阶段 0 完成：异常正式打断日常生活，玩家已经无法把它当成错觉——本幕结束时应当进入阶段 1。
阶段 1 完成：征兆产生实际的、不可逆的后果，入口真实出现在玩家面前——本幕结束时应当进入阶段 2。
阶段 2 完成：阈限事件发生，玩家已经跨过去或被卷进去——这是玩家最后一次真正的选择点，值得详写。
阶段 3、4 是纯过程（转移途中、首次落地的第一感知）：默认 narration="summary" 一幕带过，直接把玩家送到新世界站稳。
阶段 5 恢复普通异世界主线。
**禁止把本幕的作用写成「为下一阶段铺垫」「留下因果桥」「让玩家感知到征兆」。**铺垫不是事件。一幕只做铺垫，等于这一幕没有发生。
{('这是快速迁移路线：原世界最多保留一个可回应起点，不能规划数回合的原世界职业生活。' if fast else '')}
不要因为玩家尚未接受入口就把穿越规划成“以后再说”；玩家的选择只改变路径，不取消前提。不要提前替玩家接受、答应、选择身份或能力。
"""
    preset_note = ""
    if world and ctx.preset_id:
        preset = next((p for p in world.presets if p.id == ctx.preset_id), None)
        preset_note = preset.note if preset else ""
    return f"""你是互动小说的剧情规划 Agent，不写小说正文。你要把长期方向整理成可执行的部分有序剧情节点，并只为接下来的 2-6 个玩家回合制作一张场景卡。

硬规则：
0. **玩家在开局选定的前提必须兑现**。跨世界迁移不是可选钩子，是玩家点单的东西。下面第 2/3/4/8 条约束的是「不要凭空塞入玩家没有选择的事件」，它们**不适用于前提本身**。玩家可以自由选择如何应对迁移，但不能选择迁移是否发生；他一直过日常，不代表他放弃了这个前提。收到【迁移已停滞】或【迁移严重停滞】时，本场景**必须**实质推进迁移，并把 pressure_budget 提到足以支撑该阶段事件的程度——这是第 8 条明确允许的例外。把迁移当成普通日常线来「尊重玩家节奏」，结果就是玩家选了穿越却几十回合停在原世界，那是明确的失败。
1. 玩家可做任何行动；剧情节点只能声明前置条件和激活条件，不能预定玩家会接受任务、相信某人、前往某地或作出某种情绪反应。
2. 任何新事件都必须有具体的 causal_bridge：它从哪项已知事实、人物需求或玩家行动自然产生，以及为什么是现在。没有铺垫就不要发生。
3. 保留旧 runtime 中仍成立的线程 id、人物动机与因果。玩家拒绝、忽略或绕开某个钩子后，更新该线为 paused/abandoned；禁止把同一钩子换皮再次强塞。
4. 同时最多 3 条剧情线，每条 2-4 个节点；生活、职业、关系、经营、旅行本身都能成为完整主线，不必加入阴谋、幕后组织或世界危机。
5. current_scene 是严格的 SceneContract：写明参与者各自想做什么、现在能公开的信息、玩家可用 affordances、禁止事项、以及停止点。不得要求写手透露 private_cause。
5a. **停止点必须落在 purpose 兑现之后，不能落在它兑现之前**。stop_points 回答的是「这一幕该做的事做完了，接下来轮到玩家决定」，不是「刚发生了点什么、玩家可以有反应了」。
  错误示范：purpose=「让异常产生实际后果，把阶段推进到逼近」，stop_points=「玩家对异常做出反应后」——玩家一反应就收场，后果根本没发生，这一幕等于没写。
  正确写法：停止点描述 purpose 已经落地后的那个新局面，例如「地面塌出开口、冷光透出之后」。
  一句话自检：**照着你写的停止点收场，purpose 兑现了吗？**没有就把停止点往后挪。
5b. **不要重复上一幕没兑现的 purpose**。如果你发现本幕的 purpose 和上一幕实质相同，那说明上一幕的停止点设早了，不是说明这件事需要再来一次。此时应当：把那件事当作**已经发生的既成事实**写进 situation 和 causal_bridge，purpose 换成**下一件**事。同一个目标连写两幕，玩家看到的就是原地打转。
6. 身份、身体种族、职业、阵营、关系与穿越落点保持开放；没有玩家设定或已确立事实时不要替玩家锁死。
7. 非穿越场景的 premise_phase 必须为 null。穿越场景请**根据最近叙事判断故事实际处在哪个阶段**并如实填写 0-5：0原生活、1逼近、2阈限、3转移途中、4首次落地、5已抵达。【迁移状态】里的程序阶段仅供参考——若它与叙事明显不符（例如程序说已抵达新世界，而叙事仍在原世界的公寓里），以叙事为准如实下调，程序会采纳你的判断。premise_phase 填的是**本幕结束时**的阶段：本幕让当前阶段完成了，就填下一级。同一个征兆连着几个回合只是被反复加深细化（越描越细但没进入下一步），那本身就说明卡住了。详写一次最多上调一级；略写（narration="summary"）因为覆盖整段过程，可以上调两级。不得为了赶进度直接跳到已抵达。
8. pressure_budget 与 mystery_budget 各为 0-4。普通生活/社交默认 pressure 0-1、mystery 0；只有已发生事件和玩家主动选择支持时才能提高。预算不是必须花完，禁止用辞藻假装强度。
8b. **narration 决定这一幕详写还是略写，按小说的常规分寸来判断**：
  narration="scene"（详写）——本幕存在真正的冲突、需要玩家做出的选择、或影响后续的新信息。逐步展开，停在玩家要反应的地方。
  narration="summary"（略写）——纯过程且结果已定：赶路、等待、传送、搬运、排队、例行公事、单纯的时间流逝。这类内容用一两段概括**整段过程**并直接抵达它的终点，不要逐步描写。同时填写 summary_target，写明这一幕要跨过什么、最终停在哪里。
  判断依据只有一条：**如果这一幕出了岔子会怎样？**答案是「不会怎样」，就略写。
  尤其注意：穿越/传送/转移的过程本身默认略写。只有当过程中真的发生冲突（有人阻拦、出了故障、玩家必须做选择）时才详写——那种情况很少见。
  略写不是敷衍，是把回合让给真正有选择的时刻。连续几个回合都在描写同一个过程的不同侧面，说明这里本来就该略写。
9. causal_event_ids 与 soft_commitment_ids 只能引用【已检索事实】里真实出现的 evt_/com_ id；没有就留空。forbidden 至少包含当前场景最容易犯的一项错误。
10. 输出纯 JSON，不要 Markdown，不要解释。

输出结构：
{{"version":1,"revision":1,"premise":"本局当前可验证前提", "threads":[{{"id":"稳定id","title":"","kind":"生活/关系/职业/冒险/调查等","public_goal":"玩家能理解的目标","private_cause":"幕后真实因果；没有就空","why_now":"为什么此刻会动","player_connection":"为何与玩家当前生活有关","established_clues":[],"open_questions":[],"beats":[{{"id":"稳定id","label":"","purpose":"","prerequisites":[],"setup":[],"activation_condition":"","status":"dormant|available|active|resolved|abandoned"}}],"status":"dormant|active|paused|resolved|abandoned"}}],"current_scene":{{"id":"稳定id","title":"","situation":"玩家此刻可观察的处境","purpose":"本场景唯一主要作用；必须与上一幕不同","causal_bridge":"从上一幕到这一幕的可见因果桥","causal_event_ids":[],"active_thread_ids":[],"participant_intents":{{"人物":"眼前具体意图"}},"available_information":[],"affordances":[],"allowed_developments":[],"forbidden":[],"soft_commitment_ids":[],"pressure_budget":1,"mystery_budget":0,"narration":"scene|summary","summary_target":"略写时写明本幕要跨过什么、停在哪里；详写留空","stop_points":["purpose 兑现之后、轮到玩家决定下一步的那一刻"],"refresh_after_turn":{ctx.turn + 4},"premise_phase":null,"status":"active"}}}}

{stall_note}{repeat_note}【规划原因】{ctx.reason}；当前玩家回合={ctx.turn}；篇幅={ctx.pace}；预设={ctx.preset_id or '无'}
【世界设定】\n{str(world_text)[:9000]}
【本局最终设定】\n{ctx.story_dna[:6000]}
【特色预设】{preset_note[:1800]}
【开局变体】{ctx.opening_text[:1800]}
【玩家锁定标签】{'、'.join(ctx.locked_tags[:24])}
【兼容灵感候选——只在自然相容时选用】{'、'.join(ctx.inspiration_tags[:24])}
【权威状态】{state[:4000]}
【主角身份】{canon[:1600]}
【迁移状态】{premise[:1200]}
{migration_note}
【已检索事实】\n{ctx.lore_context[:5000]}
【上一版结构化规划】{previous[:9000]}
【最近对话】\n{recent[:12000]}
"""
