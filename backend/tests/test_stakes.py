"""赌注：缺失的那一侧。

2026-08-23 的实测：穿越落地之后连着 6 幕 conflict 全空、pressure 全是 1，
purpose 一律是「让玩家抵达 X，看到 Y，并做出下一步选择」——走路加观光。
玩家的原话是「非常之无聊 没有任何冲突」。

成因不是某条规则写错了，是整套规则全朝一个方向：

    核心规则 6   绝大多数人没有秘密，不要用神秘停顿制造戏剧
    核心规则 7   失败、拒绝、平淡与**无事发生都是合法结果**
    核心规则 8   不为写长而新增事件
    规划规则 8   普通生活默认 pressure 0-1
    世界脉冲     禁止新增主线、组织、灾难……否则完全不写

全是刹车，没有油门。没有任何一条规则要求「一幕得有东西可失去」，
平衡点自然落在什么都不发生。这一组测试锁的是补上的那一侧。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.story import StoryPlanContext  # noqa: E402
from app.services.story_planner import (  # noqa: E402
    STAKES_QUIET_ESCALATE, STAKES_QUIET_LIMIT, build_story_plan_prompt,
    parse_story_runtime, stakes_note,
)


def _card(conflict: str = "", sid: str = "s", pressure: int = 1) -> str:
    return json.dumps({
        "premise": "x", "threads": [],
        "current_scene": {"id": sid, "title": "走向石墙", "situation": "土路上",
                          "purpose": "让玩家抵达石墙，发现第一处人烟，并做出下一步选择",
                          "causal_bridge": "c", "conflict": conflict,
                          "pressure_budget": pressure},
    }, ensure_ascii=False)


# ── 安静幕计数 ──────────────────────────────────────────────────

def test_quiet_scenes_accumulate() -> None:
    runtime, prev = None, {}
    for i in range(3):
        runtime, warnings = parse_story_runtime(_card(sid=f"s{i}"), prev, i * 4, "horizon")
        prev = runtime.model_dump()
    assert runtime.quiet_scene_count == 3
    assert any("走马观花" in w for w in warnings)


def test_a_conflict_resets_the_count() -> None:
    runtime, prev = None, {}
    for i in range(3):
        runtime, _ = parse_story_runtime(_card(sid=f"s{i}"), prev, i * 4, "horizon")
        prev = runtime.model_dump()
    assert runtime.quiet_scene_count == 3
    runtime, _ = parse_story_runtime(
        _card(conflict="客栈老板要押金，玩家身上不够", sid="s9", pressure=2),
        prev, 20, "horizon")
    assert runtime.quiet_scene_count == 0


def test_one_quiet_scene_is_not_flagged() -> None:
    """
    大事之后喘口气是正常的。阈值不设成 1——把「每一幕都必须有冲突」写死，
    等于回到玩家最早抱怨的那种强推。
    """
    runtime, warnings = parse_story_runtime(_card(), {}, 4, "horizon")
    assert runtime.quiet_scene_count == 1
    assert not any("走马观花" in w for w in warnings)


# ── 施压文案 ────────────────────────────────────────────────────

def test_note_is_silent_below_the_limit() -> None:
    assert stakes_note(0) == ""
    assert stakes_note(STAKES_QUIET_LIMIT - 1) == ""


def test_note_teaches_what_a_legal_conflict_is() -> None:
    """
    这是关键：反强推规则禁的是**凭空塞入**，不是冲突本身。不说清楚这一点，
    规划器会以为「加冲突」等于「加阴谋」，于是继续什么都不加。
    """
    note = stakes_note(STAKES_QUIET_LIMIT)
    assert "冲突不等于阴谋" in note
    assert "从已经建立的人和事里找" in note
    # 给的是具体例子，不是抽象要求
    assert "客栈老板要的钱" in note and "公会不收没有担保人的外乡人" in note
    assert "不违反任何一条反强推规则" in note


def test_note_escalates() -> None:
    hard = stakes_note(STAKES_QUIET_ESCALATE)
    assert "严重" in hard
    # 升级版要给可执行动作，而不是重复「要有冲突」
    assert "pressure_budget 提到 2 以上" in hard
    assert "空着 conflict 交上来就是又一幕观光" in hard


def test_note_reaches_the_planner() -> None:
    p = build_story_plan_prompt(StoryPlanContext(
        world_id="wuxia", pace="long", turn=20, reason="horizon",
        story_runtime={"quiet_scene_count": STAKES_QUIET_ESCALATE},
    ))
    assert "没有冲突·严重" in p


# ── 剧情线退化成状态报告 ────────────────────────────────────────

def test_thread_whose_private_cause_restates_the_goal_is_flagged() -> None:
    """
    实测那一局唯一的活跃线：
      公开目标 = 确认自身处境，找到有人烟的聚落，开始新生活
      幕后原因 = 穿越已经完成，玩家已抵达新世界，需要建立新的生活起点
    两句在说同一件事，而且都只是陈述现状。这样的线只能产出「走到下一个地方」。
    """
    raw = json.dumps({
        "premise": "x",
        "threads": [{
            "id": "t1", "title": "穿越完成与初抵新世界",
            "public_goal": "确认自身处境，找到有人烟的聚落，开始新生活",
            "private_cause": "确认自身处境，找到有人烟的聚落，开始新的生活起点",
            "status": "active",
        }],
        "current_scene": {"id": "s", "title": "t", "situation": "x",
                          "purpose": "p", "causal_bridge": "c"},
    }, ensure_ascii=False)
    _, warnings = parse_story_runtime(raw, {}, 0, "opening")
    assert any("只是在复述公开目标" in w for w in warnings)


def test_a_thread_with_a_real_hidden_cause_passes() -> None:
    raw = json.dumps({
        "premise": "x",
        "threads": [{
            "id": "t1", "title": "货棚的欠账",
            "public_goal": "在老槐村找到过冬的落脚处",
            "private_cause": "老韩替前任货主担保过一笔货款，债主下月就来收，他急着找个能顶事的外乡人",
            "status": "active",
        }],
        "current_scene": {"id": "s", "title": "t", "situation": "x",
                          "purpose": "p", "causal_bridge": "c"},
    }, ensure_ascii=False)
    _, warnings = parse_story_runtime(raw, {}, 0, "opening")
    assert not any("只是在复述公开目标" in w for w in warnings)


# ── 规则本身 ────────────────────────────────────────────────────

def test_planner_is_taught_the_missing_half() -> None:
    p = build_story_plan_prompt(StoryPlanContext(world_id="wuxia"))
    assert "4b." in p and "某个人想要某样东西，而有什么挡着" in p
    assert "4c." in p and "这一幕里，玩家可能失去什么" in p
    # 必须点明它与反强推规则是配套的，不是对立的
    assert "它们**不反对冲突本身**" in p
    # 允许过渡幕，但不许连着空
    assert "不能连着几幕都空" in p


def test_pressure_is_tied_to_conflict_not_genre() -> None:
    """
    原文是「普通生活/社交默认 pressure 0-1」——按题材定档，于是日常局的
    压力永远升不上去。改成按有没有冲突定档。
    """
    p = build_story_plan_prompt(StoryPlanContext(world_id="wuxia"))
    assert "压力跟着冲突走，不跟着题材走" in p
    assert "填了 conflict 就说明有东西处在不确定中，pressure 至少 2" in p
