"""迁移契约：程序对「必须发生的事」行使执行权。

背景见 app/services/migration_contract.py 的模块注释：四轮实测里，只要
「穿越是否发生」还取决于模型配合，模型就会用新的方式不配合。这一层把
保证从提示词搬进程序。

这组测试最重要的一条是 test_forced_scene_moves_the_story_not_just_the_ledger
——它锁的正是第一轮失败的教训。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.migration_contract import (  # noqa: E402
    LANDED_PHASE, budget_note, budget_total, forced_scene, should_force, turns_left,
)
from app.services.story_planner import parse_story_runtime  # noqa: E402


def ps(phase: int, started_at: int = 0, **kw) -> dict:
    base = {"kind": "transmigration", "phase": phase, "startedAt": started_at,
            "phaseTurns": 0, "fast": True}
    base.update(kw)
    return base


def _plan(phase: int) -> str:
    """规划器又一次只安排了铺垫——这正是四轮里反复出现的输出。"""
    return json.dumps({
        "premise": "x", "threads": [],
        "current_scene": {
            "id": "s", "title": "窗边的异响", "situation": "玩家还在原世界的茶楼里",
            "purpose": "让征兆抵达玩家面前，为穿越逼近留下因果桥",
            "causal_bridge": "c", "premise_phase": phase,
        },
    }, ensure_ascii=False)


# ── 预算本身 ────────────────────────────────────────────────────

def test_budget_scales_with_pace() -> None:
    assert budget_total(ps(0), "short") < budget_total(ps(0), "medium") < budget_total(ps(0), "long")


def test_slow_route_gets_more_room() -> None:
    """显式关掉快速迁移的存档给双倍——玩家选的就是慢链。"""
    assert budget_total(ps(0, fast=False), "medium") == 2 * budget_total(ps(0), "medium")


def test_budget_counts_from_when_the_premise_started() -> None:
    """不是从第 0 回合算，是从穿越前提确立那一刻算（旧存档中途升级时会差很多）。"""
    assert turns_left(ps(0, started_at=20), turn=22, pace="medium") == budget_total(ps(0), "medium") - 2


def test_non_migration_games_are_untouched() -> None:
    assert should_force({"kind": "none"}, turn=99, pace="short") is False
    assert budget_note({"kind": "none"}, turn=99, pace="short") == ""


def test_landing_stops_the_contract() -> None:
    """已经落地就不该再接管——否则会把玩家反复送进新世界。"""
    assert should_force(ps(LANDED_PHASE, started_at=0), turn=99, pace="short") is False
    assert should_force(ps(5, started_at=0), turn=99, pace="short") is False
    assert budget_note(ps(5, started_at=0), turn=99, pace="short") == ""


# ── 软提示：常态路径 ────────────────────────────────────────────

def test_budget_note_is_forward_looking() -> None:
    """
    停滞加压说的是「你已经卡了 N 回合」（回顾），预算说的是「你还剩 N 回合」
    （前瞻）。只有后者能让模型排出计划——这是加这一层的次要动机。
    """
    note = budget_note(ps(0, started_at=0), turn=1, pace="long")
    assert "还有" in note and "回合完成穿越" in note


def test_budget_note_sharpens_near_the_deadline() -> None:
    total = budget_total(ps(0), "medium")
    note = budget_note(ps(0, started_at=0), turn=total - 1, pace="medium")
    assert "只剩 1 个回合" in note
    assert "不要再规划新的铺垫" in note


def test_budget_note_warns_before_the_program_takes_over() -> None:
    """预告接管，给模型最后一次自己完成的机会。"""
    note = budget_note(ps(1, started_at=0), turn=99, pace="medium")
    assert "迁移预算已用尽" in note
    assert "程序会直接接管本幕" in note


# ── 硬接管 ──────────────────────────────────────────────────────

def test_program_takes_over_when_budget_runs_out() -> None:
    total = budget_total(ps(0), "medium")
    runtime, warnings = parse_story_runtime(
        _plan(0), {}, turn=total, reason="horizon",
        premise_state=ps(0, started_at=0), pace="medium")
    scene = runtime.current_scene
    assert scene.premise_phase == 5
    assert scene.premise_phase_forced is True
    assert any("由程序接管" in w for w in warnings)


def test_no_takeover_while_within_budget() -> None:
    """预算之内一切照旧，规划器的卡原样保留——接管必须是兜底，不是常态。"""
    runtime, warnings = parse_story_runtime(
        _plan(0), {}, turn=1, reason="horizon",
        premise_state=ps(0, started_at=0), pace="medium")
    assert runtime.current_scene.title == "窗边的异响"
    assert runtime.current_scene.premise_phase_forced is False
    assert not any("由程序接管" in w for w in warnings)


def test_forced_scene_moves_the_story_not_just_the_ledger() -> None:
    """
    这一条锁的是第一轮失败的教训。

    当年那个计时器直接把 phase 改成 5，故事原地不动，于是写手同时收到
    「已经抵达新世界」和「玩家正在阳台上撸猫」两条矛盾指令，它跟了具体
    的那条——账本说已抵达，玩家还在原世界，而阶段一到 5 所有推进压力
    全部停摆，「选了穿越却永远不穿越」就此稳定复现。

    所以程序接管时下发的必须是**一幕真正要被写出来的戏**：它得有目的、
    有落点、有禁止事项，写手照着写，叙事和阶段才会一起走。
    """
    scene = forced_scene(ps(1, started_at=0), turn=7, previous_scene={"situation": "茶楼靠窗的位置"})

    # 是一幕戏，不是一个数字
    assert "完成穿越" in scene["purpose"] and "落在新世界站稳并睁开眼" in scene["purpose"]
    assert scene["stop_points"] and scene["summary_target"]
    # 承接上一幕的处境，不是凭空另起
    assert "茶楼靠窗的位置" in scene["causal_bridge"]
    # 转移过程本身是纯过程，交给略写
    assert scene["narration"] == "summary"
    # 明确堵死四轮里出现过的每一种「没穿越」
    forbidden = "".join(scene["forbidden"])
    assert "又一次征兆" in forbidden
    assert "仍然留在原世界" in forbidden
    assert "逐步描写转移过程" in forbidden


def test_forced_scene_compresses_transit_but_leaves_arrival_to_next_scene() -> None:
    """
    小说的常规分寸：转移过程压缩，抵达单独成幕。

    实测过反面——一张略写卡把转移和抵达一起包了，第二个回合用「略写」
    写了 597 字的新世界环境，最该详写的第一眼被压扁了。

    落点填 5（已抵达）而不是 4（首次落地）：填 4 会让下一幕再规划一次
    「落地」，玩家看到的就是穿越隔了一回合才完成。
    """
    scene = forced_scene(ps(0, started_at=0), turn=5, previous_scene=None)
    assert scene["premise_phase"] == 5
    assert "睁开眼" in scene["summary_target"]
    assert "新世界的样子留给下一幕" in scene["summary_target"]
    assert any("第一眼留给下一幕详写" in x for x in scene["forbidden"])
    # 接管的判据仍是 4：已经跨过去就不再接管。
    assert should_force(ps(LANDED_PHASE, started_at=0), turn=99, pace="short") is False


def test_forced_scene_hands_control_back_next_turn() -> None:
    """接管只负责这一幕。下一回合就重新规划，程序不接管剧情走向。"""
    scene = forced_scene(ps(1, started_at=0), turn=7, previous_scene=None)
    assert scene["refresh_after_turn"] == 8


def test_takeover_survives_a_planner_that_refuses_to_advance() -> None:
    """
    端到端：规划器坚持填阶段 0（四轮里最常见的行为），预算已用尽。
    程序必须仍然把玩家送到新世界——这正是这一层存在的全部理由。
    """
    runtime, _ = parse_story_runtime(
        _plan(0), {}, turn=30, reason="horizon",
        premise_state=ps(0, started_at=0), pace="long")
    assert runtime.current_scene.premise_phase == 5
    assert "完成穿越" in runtime.current_scene.purpose


# ── 强制令：压过每回合指令 ──────────────────────────────────────

def _ctx(scene: dict | None):
    from app.schemas.turn import TurnContext
    return TurnContext(
        world_id="wuxia", pace="medium", turns=6, game_state={"revealed": True},
        story_runtime=({"current_scene": scene} if scene else {}),
    )


def test_no_mandate_on_ordinary_turns() -> None:
    from app.services.prompt_builder import turn_mandate
    assert turn_mandate(_ctx(None)) == ""
    assert turn_mandate(_ctx({"id": "s", "purpose": "普通一幕"})) == ""


def test_mandate_overrides_the_stop_at_decision_boundary_rule() -> None:
    """
    实测的失败：写手拿到了程序的「穿过去」卡，玩家输入是「拿起那枚铜钱，
    看颤动是否还在」，写手就只拿起了铜钱——因为前端在整份系统提示词之后
    还追加了一句「只完成玩家明确行动、在下一个决策边界前停下」，它更靠后
    也更具体。穿越因此推迟了一回合。

    强制令必须明写它压过那一条，否则同样的冲突会再发生一次。
    """
    from app.services.prompt_builder import turn_mandate
    note = turn_mandate(_ctx(forced_scene(ps(1, started_at=0), turn=6, previous_scene=None)))
    assert "优先级高于" in note and "在决策边界前停下" in note
    assert "必须在这一回合内发生并走完" in note
    assert "不得推迟到下一回合" in note
    assert "完成穿越" in note


# ── 略写幕只占一个回合 ──────────────────────────────────────────

def test_summary_scene_lasts_exactly_one_turn() -> None:
    """
    略写=「一到两段带过整段过程并抵达终点」，挂两个回合就自相矛盾。
    实测：落地那张略写卡挂了回合 7 和 8，第 8 回合用「略写」写了 597 字的
    新世界环境——最该详写的第一眼被压扁了。
    """
    raw = json.dumps({
        "premise": "x", "threads": [],
        "current_scene": {"id": "s", "title": "赶路", "situation": "官道上",
                          "purpose": "跨过三天的路程", "causal_bridge": "c",
                          "narration": "summary", "summary_target": "抵达县城",
                          "refresh_after_turn": 99},
    }, ensure_ascii=False)
    runtime, _ = parse_story_runtime(raw, {}, turn=10, reason="horizon")
    assert runtime.current_scene.refresh_after_turn == 11


def test_scene_narration_keeps_the_normal_horizon() -> None:
    """详写幕不受影响，仍按正常下限走——只有略写是一回合。"""
    raw = json.dumps({
        "premise": "x", "threads": [],
        "current_scene": {"id": "s", "title": "谈判", "situation": "堂上",
                          "purpose": "谈成或谈崩", "causal_bridge": "c",
                          "narration": "scene", "refresh_after_turn": 0},
    }, ensure_ascii=False)
    runtime, _ = parse_story_runtime(raw, {}, turn=10, reason="horizon")
    assert runtime.current_scene.refresh_after_turn > 11
