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


def parse_story_runtime(raw: str, previous: dict[str, Any], turn: int, reason: str) -> tuple[StoryRuntime, list[str]]:
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
    scene["stop_points"] = _clean_list(scene.get("stop_points"), 6)
    requested_horizon = int(scene.get("refresh_after_turn") or turn + 3)
    scene["refresh_after_turn"] = max(turn + 2, min(turn + 6, requested_horizon))
    data["current_scene"] = scene

    try:
        return StoryRuntime.model_validate(data), warnings
    except ValidationError as exc:
        raise ValueError("剧情规划字段不合法：" + str(exc).splitlines()[0]) from exc


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
    state = json.dumps(ctx.game_state or {}, ensure_ascii=False, separators=(",", ":"))
    canon = json.dumps(ctx.player_canon or {}, ensure_ascii=False, separators=(",", ":"))
    premise = json.dumps(ctx.premise_state or {}, ensure_ascii=False, separators=(",", ":"))
    preset_note = ""
    if world and ctx.preset_id:
        preset = next((p for p in world.presets if p.id == ctx.preset_id), None)
        preset_note = preset.note if preset else ""
    return f"""你是互动小说的剧情规划 Agent，不写小说正文。你要把长期方向整理成可执行的部分有序剧情节点，并只为接下来的 2-6 个玩家回合制作一张场景卡。

硬规则：
1. 玩家可做任何行动；剧情节点只能声明前置条件和激活条件，不能预定玩家会接受任务、相信某人、前往某地或作出某种情绪反应。
2. 任何新事件都必须有具体的 causal_bridge：它从哪项已知事实、人物需求或玩家行动自然产生，以及为什么是现在。没有铺垫就不要发生。
3. 保留旧 runtime 中仍成立的线程 id、人物动机与因果。玩家拒绝、忽略或绕开某个钩子后，更新该线为 paused/abandoned；禁止把同一钩子换皮再次强塞。
4. 同时最多 3 条剧情线，每条 2-4 个节点；生活、职业、关系、经营、旅行本身都能成为完整主线，不必加入阴谋、幕后组织或世界危机。
5. current_scene 只约束眼前场景：写明参与者各自想做什么、现在能公开的信息、允许自然发生的变化、以及必须在哪些玩家可反应处停下。不得要求写手透露 private_cause。
6. 身份、身体种族、职业、阵营、关系与穿越落点保持开放；没有玩家设定或已确立事实时不要替玩家锁死。
7. premise_phase 只在确有文本证据时填写 0-5：0原生活、1逼近、2阈限、3转移途中、4首次落地、5已抵达。不要为了赶进度虚报。
8. 输出纯 JSON，不要 Markdown，不要解释。

输出结构：
{{"version":1,"revision":1,"premise":"本局当前可验证前提", "threads":[{{"id":"稳定id","title":"","kind":"生活/关系/职业/冒险/调查等","public_goal":"玩家能理解的目标","private_cause":"幕后真实因果；没有就空","why_now":"为什么此刻会动","player_connection":"为何与玩家当前生活有关","established_clues":[],"open_questions":[],"beats":[{{"id":"稳定id","label":"","purpose":"","prerequisites":[],"setup":[],"activation_condition":"","status":"dormant|available|active|resolved|abandoned"}}],"status":"dormant|active|paused|resolved|abandoned"}}],"current_scene":{{"id":"稳定id","title":"","situation":"玩家此刻可观察的处境","purpose":"本场景唯一主要作用","causal_bridge":"从上一幕到这一幕的可见因果桥","active_thread_ids":[],"participant_intents":{{"人物":"眼前具体意图"}},"available_information":[],"allowed_developments":[],"stop_points":[],"refresh_after_turn":{ctx.turn + 3},"premise_phase":null,"status":"active"}}}}

【规划原因】{ctx.reason}；当前玩家回合={ctx.turn}；篇幅={ctx.pace}；预设={ctx.preset_id or '无'}
【世界设定】\n{str(world_text)[:9000]}
【本局最终设定】\n{ctx.story_dna[:6000]}
【特色预设】{preset_note[:1800]}
【开局变体】{ctx.opening_text[:1800]}
【玩家锁定标签】{'、'.join(ctx.locked_tags[:24])}
【兼容灵感候选——只在自然相容时选用】{'、'.join(ctx.inspiration_tags[:24])}
【权威状态】{state[:5000]}
【主角身份】{canon[:1600]}
【迁移状态】{premise[:1200]}
【已检索事实】\n{ctx.lore_context[:5000]}
【上一版结构化规划】{previous[:9000]}
【最近对话】\n{recent[:12000]}
"""
