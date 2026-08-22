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
    scene["stop_points"] = _clean_list(scene.get("stop_points"), 6)
    requested_horizon = int(scene.get("refresh_after_turn") or turn + 3)
    scene["refresh_after_turn"] = max(turn + 2, min(turn + 6, requested_horizon))

    # 迁移阶段：规划器可以自由下调，但一次最多上调一级。
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
    ps = premise_state if isinstance(premise_state, dict) else {}
    if ps.get("kind") == "transmigration":
        try:
            current_phase = max(0, min(5, int(ps.get("phase", 0))))
        except (TypeError, ValueError):
            current_phase = 0
        proposed = scene.get("premise_phase")
        try:
            proposed_phase = None if proposed is None else max(0, min(5, int(proposed)))
        except (TypeError, ValueError):
            proposed_phase = None

        if proposed_phase is None:
            scene["premise_phase"] = current_phase
        elif proposed_phase > current_phase + 1:
            # 一次跳好几级基本是模型在赶进度，玩家还在原世界就被宣布已抵达
            warnings.append(
                f"规划器想从阶段 {current_phase} 直接跳到 {proposed_phase}，"
                "已限制为只前进一级"
            )
            scene["premise_phase"] = current_phase + 1
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
本局穿越是已经确定的故事前提，不是可有可无的支线。程序当前迁移阶段={phase}（{stage_names[phase]}），current_scene.premise_phase 必须填写这个数值；不得自行改成别的阶段。
规划器必须围绕当前迁移阶段规划一张可执行场景卡：给出从当前场景到下一步迁移进展的可见因果桥、玩家可回应的具体入口，以及停下的位置。可以保留当前生活线作为桥，但不能让无关日常、职业任务或邻里琐事连续占用迁移阶段。
阶段 0 只安排一项眼前刺激并为逼近留下可观察的因果桥；阶段 1 安排触发征兆或回应后的逼近；阶段 2 安排阈限过程；阶段 3 安排转移中的可感知过程；阶段 4 安排首次落地的第一感知。阶段 5 才恢复普通异世界主线。
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
5. current_scene 是严格的 SceneContract：写明参与者各自想做什么、现在能公开的信息、玩家可用 affordances、禁止事项、以及必须在哪些玩家可反应处停下。不得要求写手透露 private_cause。
6. 身份、身体种族、职业、阵营、关系与穿越落点保持开放；没有玩家设定或已确立事实时不要替玩家锁死。
7. 非穿越场景的 premise_phase 必须为 null。穿越场景请**根据最近叙事判断故事实际处在哪个阶段**并如实填写 0-5：0原生活、1逼近、2阈限、3转移途中、4首次落地、5已抵达。【迁移状态】里的程序阶段仅供参考——若它与叙事明显不符（例如程序说已抵达新世界，而叙事仍在原世界的公寓里），以叙事为准如实下调，程序会采纳你的判断。若叙事确实推进了，就如实上调一级——同一个征兆连着几个回合只是被反复加深细化（越描越细但没进入下一步），那本身就说明卡住了，应当在本场景让当前阶段结束并把 premise_phase 上调一级。但一次最多上调一级，不得为了赶进度直接跳到已抵达。
8. pressure_budget 与 mystery_budget 各为 0-4。普通生活/社交默认 pressure 0-1、mystery 0；只有已发生事件和玩家主动选择支持时才能提高。预算不是必须花完，禁止用辞藻假装强度。
9. causal_event_ids 与 soft_commitment_ids 只能引用【已检索事实】里真实出现的 evt_/com_ id；没有就留空。forbidden 至少包含当前场景最容易犯的一项错误。
10. 输出纯 JSON，不要 Markdown，不要解释。

输出结构：
{{"version":1,"revision":1,"premise":"本局当前可验证前提", "threads":[{{"id":"稳定id","title":"","kind":"生活/关系/职业/冒险/调查等","public_goal":"玩家能理解的目标","private_cause":"幕后真实因果；没有就空","why_now":"为什么此刻会动","player_connection":"为何与玩家当前生活有关","established_clues":[],"open_questions":[],"beats":[{{"id":"稳定id","label":"","purpose":"","prerequisites":[],"setup":[],"activation_condition":"","status":"dormant|available|active|resolved|abandoned"}}],"status":"dormant|active|paused|resolved|abandoned"}}],"current_scene":{{"id":"稳定id","title":"","situation":"玩家此刻可观察的处境","purpose":"本场景唯一主要作用","causal_bridge":"从上一幕到这一幕的可见因果桥","causal_event_ids":[],"active_thread_ids":[],"participant_intents":{{"人物":"眼前具体意图"}},"available_information":[],"affordances":[],"allowed_developments":[],"forbidden":[],"soft_commitment_ids":[],"pressure_budget":1,"mystery_budget":0,"stop_points":[],"refresh_after_turn":{ctx.turn + 3},"premise_phase":null,"status":"active"}}}}

{stall_note}【规划原因】{ctx.reason}；当前玩家回合={ctx.turn}；篇幅={ctx.pace}；预设={ctx.preset_id or '无'}
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
