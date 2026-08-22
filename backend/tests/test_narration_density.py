"""
详写／略写测试
==============
引擎原本没有「叙事密度」这个概念：pressure_budget 管的是多紧张，
篇幅设置管的是整局多长，两者都回答不了「这一幕值不值得逐步展开」。

缺了它的代价实测过：一次穿越的传送过程写了 11 个回合、约 4500 字，
每回合只是换个感官细节重复同一件事——水雾、嗡鸣、进度条、摸路灯杆、
吸一口凉气、再看进度条。

小说的常规分寸是：有冲突、有选择、有新信息才详写；纯过程在结果已定时略写。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.story import StoryPlanContext  # noqa: E402
from app.schemas.turn import TurnContext  # noqa: E402
from app.services.prompt_builder import (  # noqa: E402
    active_rule_packs, build_system_prompt,
)
from app.services.story_planner import build_story_plan_prompt, parse_story_runtime  # noqa: E402


def scene(**kw) -> dict:
    base = {"id": "s1", "title": "穿过传送门", "situation": "光包裹住你",
            "purpose": "抵达新世界", "causal_bridge": "你迈过门槛"}
    base.update(kw)
    return base


def runtime(**kw) -> dict:
    return {"current_scene": scene(**kw), "threads": []}


def turn_ctx(**kw) -> TurnContext:
    return TurnContext(world_id="wuxia", pace="long", turns=20,
                       game_state={"revealed": True}, **kw)


# ── 规划器要会判断 ──────────────────────────────────────────────

def test_planner_is_taught_the_craft_rule() -> None:
    p = build_story_plan_prompt(StoryPlanContext(
        world_id="wuxia", pace="long", turn=5, reason="horizon",
        story_dna="x", game_state={}, recent_messages=[]))
    assert "narration" in p and "summary_target" in p
    # 判断依据要具体到能执行，不能只说「合理安排详略」
    assert "如果这一幕出了岔子会怎样" in p
    # 穿越过程是最典型的该略写场景，要点名
    assert "穿越/传送/转移的过程本身默认略写" in p


def test_repeated_process_scenes_are_named_as_the_symptom() -> None:
    """连着几回合描写同一过程的不同侧面，本身就是该略写的信号。"""
    p = build_story_plan_prompt(StoryPlanContext(
        world_id="wuxia", pace="long", turn=5, reason="horizon",
        story_dna="x", game_state={}, recent_messages=[]))
    assert "连续几个回合都在描写同一个过程的不同侧面" in p


# ── 解析与兜底 ──────────────────────────────────────────────────

def _parse(**scene_kw):
    raw = json.dumps({"premise": "x", "threads": [],
                      "current_scene": scene(**scene_kw)}, ensure_ascii=False)
    return parse_story_runtime(raw, {}, 5, "horizon")


def test_summary_mode_is_accepted() -> None:
    rt, _ = _parse(narration="summary", summary_target="抵达新世界的落点")
    assert rt.current_scene.narration == "summary"
    assert rt.current_scene.summary_target == "抵达新世界的落点"


def test_summary_without_a_target_falls_back_to_scene() -> None:
    """
    略写却没说要跨过什么，写手无从下手，只会又开始逐步描写。
    退回详写比给一个空目标安全。
    """
    rt, warnings = _parse(narration="summary")
    assert rt.current_scene.narration == "scene"
    assert any("缺少 summary_target" in w for w in warnings)


def test_unknown_value_defaults_to_scene() -> None:
    rt, _ = _parse(narration="随便写的")
    assert rt.current_scene.narration == "scene"


def test_default_is_detailed() -> None:
    """不填就详写——略写是需要理由的那一边。"""
    rt, _ = _parse()
    assert rt.current_scene.narration == "scene"


# ── 写手要收到明确指令 ──────────────────────────────────────────

def test_summary_rules_only_attach_in_summary_mode() -> None:
    """详写场景挂上略写规则是纯噪音，还会诱导模型压缩不该压缩的戏。"""
    detailed = [k for k, _, _ in active_rule_packs(turn_ctx(story_runtime=runtime()))]
    summarized = [k for k, _, _ in active_rule_packs(turn_ctx(
        story_runtime=runtime(narration="summary", summary_target="抵达落点")))]
    assert "summary-mode" not in detailed
    assert "summary-mode" in summarized


def test_scene_card_states_the_density_and_target() -> None:
    sp = build_system_prompt(turn_ctx(
        story_runtime=runtime(narration="summary", summary_target="抵达新世界的落点")))
    assert "叙事密度:略写" in sp
    assert "本幕要跨过并抵达:抵达新世界的落点" in sp


def test_detailed_scene_says_so_too() -> None:
    """详写也要明说，否则写手不知道自己在哪一档。"""
    sp = build_system_prompt(turn_ctx(story_runtime=runtime()))
    assert "叙事密度:详写" in sp
    assert "本幕要跨过并抵达" not in sp


def test_summary_rules_override_the_default_expansion_instinct() -> None:
    """
    模型天然喜欢把每个瞬间都展开。略写指令必须明确压过写手契约第 1 条的
    「完整回应玩家行动」，否则它会用「完整回应」当理由继续逐步描写。
    """
    sp = build_system_prompt(turn_ctx(
        story_runtime=runtime(narration="summary", summary_target="抵达落点")))
    assert "压过上面第 1 条" in sp
    assert "过程本身最多两三句" in sp
    assert "不要为了「有画面感」把同一件事换角度再写一遍" in sp
