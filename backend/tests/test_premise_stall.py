"""
迁移停滞测试
============
真实局面里复现过的问题：玩家选了穿越前提，玩了七个回合全是原世界日常
（闹钟、邻居、橘猫、下楼），而系统从第四回合起就认为「已经抵达」。

因果链是这样的：
    1. 快速迁移的计时器在毫无叙事依据时也每回合推进一格，四回合刷到阶段 5；
    2. 阶段一到 5，所有推进压力停摆——系统以为事情办完了；
    3. 写手同时收到「已经抵达」和「送猫下楼」两条矛盾指令，它跟了具体的那条；
    4. 规划器读真实叙事、如实报了阶段 0，却被「只许往前」的钳制覆盖回 5。

所以修法是三条一起：计时器不再推进账本、压力改加在提示词上、
规划器的向下修正要采纳。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.prompt_builder import (  # noqa: E402
    PREMISE_STALL_TURNS, _agent_premise_directive, premise_stall_note,
)
from app.services.story_planner import parse_story_runtime  # noqa: E402


def ps(phase: int, held: int, **kw) -> dict:
    base = {"kind": "transmigration", "phase": phase, "phaseTurns": held,
            "mechanism": "游戏弹窗", "trigger": "深夜加班", "fast": True}
    base.update(kw)
    return base


# ── 停滞加压 ────────────────────────────────────────────────────

def test_no_pressure_before_the_threshold() -> None:
    """刚进入一个阶段不该催——玩家需要空间自己反应。"""
    assert premise_stall_note(ps(0, 0)) == ""
    assert premise_stall_note(ps(0, PREMISE_STALL_TURNS - 1)) == ""


def test_pressure_after_stalling() -> None:
    note = premise_stall_note(ps(0, PREMISE_STALL_TURNS))
    assert "迁移已停滞" in note
    assert "原世界生活" in note
    assert "必须让第一项可回应的迁移征兆真正抵达" in note


def test_pressure_does_not_take_the_decision_from_the_player() -> None:
    """
    加压是让外部事件发生，不是替玩家做决定——
    「玩家被推着走」正是这个项目最早要解决的问题。
    """
    note = premise_stall_note(ps(1, 5))
    assert "这不是替玩家做决定" in note
    assert "玩家仍然自由选择如何应对" in note


@pytest.mark.parametrize("phase", [0, 1, 2, 3, 4])
def test_every_unfinished_phase_has_its_own_nudge(phase: int) -> None:
    """每个阶段该推进的东西不同，催的话也得说清催什么。"""
    assert premise_stall_note(ps(phase, 9)) != ""


def test_arrived_phase_is_never_pressured() -> None:
    """已经抵达就没有下一阶段可推了。"""
    assert premise_stall_note(ps(5, 99)) == ""


def test_non_transmigration_is_never_pressured() -> None:
    assert premise_stall_note({"kind": "none", "phaseTurns": 99}) == ""


def test_directive_carries_the_pressure() -> None:
    """加压要真的出现在写手看到的指令里，不能只存在于函数返回值。"""
    calm = _agent_premise_directive(ps(0, 0))
    stuck = _agent_premise_directive(ps(0, PREMISE_STALL_TURNS))
    hard = _agent_premise_directive(ps(0, PREMISE_STALL_TURNS * 2))
    assert "停滞" not in calm
    assert "迁移已停滞" in stuck
    assert "严重停滞" in hard
    assert "原世界生活" in stuck and "原世界生活" in hard   # 原有信息不能丢


# ── 规划器的阶段修正 ────────────────────────────────────────────

def _runtime(phase) -> str:
    import json
    return json.dumps({
        "premise": "x", "threads": [],
        "current_scene": {"id": "s", "title": "t", "situation": "在阳台上撸猫",
                          "purpose": "p", "causal_bridge": "c",
                          "premise_phase": phase},
    }, ensure_ascii=False)


def test_planner_may_roll_the_phase_back() -> None:
    """
    这条是整组测试的核心。程序阶段因为计时器空转虚高到 5，规划器读了真实叙事
    报 0——它是对的。旧实现「只许往前」把这个正确修正丢掉了，
    于是错误的阶段永远修不回来，而阶段一到 5 所有推进压力都停摆。
    """
    runtime, warnings = parse_story_runtime(
        _runtime(0), {}, turn=6, reason="horizon", premise_state=ps(5, 3))
    assert runtime.current_scene.premise_phase == 0
    assert any("按叙事回退" in w for w in warnings)


def test_planner_advance_is_capped_at_one_step() -> None:
    """
    上调不再一概拒绝，但一次只许一级——「凭猜测宣布已经穿越」和
    「观察到真实推进」要区别对待，而区别在于跨度。
    （完全禁止上调曾经导致召唤路线卡死九回合，见下面的路线覆盖测试。）
    """
    runtime, warnings = parse_story_runtime(
        _runtime(5), {}, turn=6, reason="horizon", premise_state=ps(0, 1))
    assert runtime.current_scene.premise_phase == 1
    assert any("限制为只前进一级" in w for w in warnings)


def test_missing_phase_falls_back_to_program_state() -> None:
    runtime, _ = parse_story_runtime(
        _runtime(None), {}, turn=6, reason="horizon", premise_state=ps(2, 1))
    assert runtime.current_scene.premise_phase == 2


def test_non_transmigration_keeps_planner_value() -> None:
    """非穿越局不受这套钳制影响。"""
    runtime, _ = parse_story_runtime(
        _runtime(None), {}, turn=6, reason="horizon", premise_state={"kind": "none"})
    assert runtime.current_scene.premise_phase is None


# ── 停久了必须换一句话说 ────────────────────────────────────────

def test_long_stall_escalates_the_wording() -> None:
    """
    实测踩过的坑：征兆第 0 回合就出现了，但阶段判定没认出来，于是往后每回合
    都在重复「让第一项征兆抵达」。模型照做——把同一团光越描越细，
    连着八回合「戳它、碰它、捧着它」。指令已经被满足却还在重复，
    模型唯一能做的就是把它做得更彻底。
    """
    mild = premise_stall_note(ps(0, PREMISE_STALL_TURNS))
    hard = premise_stall_note(ps(0, PREMISE_STALL_TURNS * 2))
    assert "迁移已停滞" in mild and "严重停滞" not in mild
    assert "严重停滞" in hard
    assert "不要再把同一个对象或同一种感受反复加深" in hard
    # 升级档不能再重复轻档那句：那件事早就做过了，重复它正是模型
    # 把同一团光越描越细的原因
    assert "让第一项可回应的迁移征兆真正抵达" not in hard
    assert "推向阈限" in hard


def test_escalated_wording_still_leaves_the_player_free() -> None:
    """加压升级不等于替玩家做决定。"""
    hard = premise_stall_note(ps(1, 12))
    assert "玩家仍然自由选择如何应对" in hard


# ── 规划器可以推进一级 ──────────────────────────────────────────

def test_planner_may_advance_one_step() -> None:
    """
    正则证据只认得「游戏弹窗」那一类路线的措辞。召唤路线里第 0 回合就出现的
    「淡蓝色光点」它一个都匹配不上，阶段在 0 停了九回合。
    规划器读真实叙事，是这些路线唯一识别得了推进的东西，必须让它能推。
    """
    runtime, warnings = parse_story_runtime(
        _runtime(1), {}, turn=9, reason="horizon", premise_state=ps(0, 9))
    assert runtime.current_scene.premise_phase == 1
    assert any("已推进到阶段 1" in w for w in warnings)


def test_planner_cannot_leap_several_steps() -> None:
    """一次跳好几级基本是赶进度，玩家还在原世界就被宣布已抵达。"""
    runtime, warnings = parse_story_runtime(
        _runtime(5), {}, turn=9, reason="horizon", premise_state=ps(0, 9))
    assert runtime.current_scene.premise_phase == 1     # 被限制成只前进一级
    assert any("限制为只前进一级" in w for w in warnings)
