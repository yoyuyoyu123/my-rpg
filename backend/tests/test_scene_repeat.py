"""场景原地打转检测。

样本全部取自 2026-08-22 那局的真实规划输出：17 回合触发 8 次规划，
「推进到逼近」写了 4 幕、「推进到阈限」写了 3 幕，迁移阶段只走到 2。
"""
from __future__ import annotations

import json

from app.services.story_planner import (
    PURPOSE_REPEAT_RATIO,
    _text_overlap,
    parse_story_runtime,
    scene_repeat_note,
)
from tests.test_story_agent import sample_runtime

# 回合 3 与回合 5 的 purpose，一字不差。
PURPOSE_T3 = (
    "让玩家通过敲击管道这一行动，触发第一个明确的异常反应——管道内传来不自然的回响，"
    "同时外部环境出现可见异变，为穿越逼近留下因果桥。"
)
# 回合 7 与回合 9：换了动作名词，目标句式与落点完全一致。
PURPOSE_T7 = (
    "让玩家拨开尘土这一行动直接触发异常的实际后果——痕迹下方出现硬质表面并伴随震动加剧，"
    "同时外部发生可见异变（如远处闪光或地面裂缝），将迁移阶段从观察推进到逼近。"
)
PURPOSE_T9 = (
    "让玩家取工具撬动硬质表面这一行动直接触发异常的实际后果——硬质表面开裂或震动加剧，"
    "同时外部发生可见异变（如地面裂缝、闪光、警报），将迁移阶段从观察推进到逼近。"
)
# 真正换了目标的一幕，用作阴性对照。
PURPOSE_DIFF = "玩家在面包店里与老板确认长期租房的押金和入住时间。"


def test_identical_purpose_is_detected() -> None:
    assert _text_overlap(PURPOSE_T3, PURPOSE_T3) == 1.0


def test_reworded_same_goal_is_detected() -> None:
    # 换皮但目标一致——这是实际最常见的形态，必须抓到。
    assert _text_overlap(PURPOSE_T7, PURPOSE_T9) >= PURPOSE_REPEAT_RATIO


def test_genuinely_new_purpose_is_not_flagged() -> None:
    # 阴性对照：阈值不能低到把正常推进也判成打转。
    assert _text_overlap(PURPOSE_T7, PURPOSE_DIFF) < PURPOSE_REPEAT_RATIO


def _parse(purpose: str, previous: dict) -> tuple:
    raw = sample_runtime()
    raw["current_scene"]["purpose"] = purpose
    return parse_story_runtime(json.dumps(raw, ensure_ascii=False), previous, 10, "horizon")


def test_repeat_count_increments_and_resets() -> None:
    prev = {"revision": 1, "current_scene": {"id": "s", "purpose": PURPOSE_T7}}

    runtime, warnings = _parse(PURPOSE_T9, prev)
    assert runtime.scene_repeat_count == 1
    assert any("实质相同" in w for w in warnings)

    # 计数在连续重复时累加。
    prev2 = {"revision": 2, "current_scene": {"id": "s", "purpose": PURPOSE_T9}, "scene_repeat_count": 1}
    runtime2, _ = _parse(PURPOSE_T9, prev2)
    assert runtime2.scene_repeat_count == 2

    # 换了真正的新目标就归零，不能一直挂着。
    runtime3, warnings3 = _parse(PURPOSE_DIFF, prev2)
    assert runtime3.scene_repeat_count == 0
    assert not any("实质相同" in w for w in warnings3)


def test_no_previous_scene_never_flags() -> None:
    runtime, warnings = _parse(PURPOSE_T7, {"revision": 1})
    assert runtime.scene_repeat_count == 0
    assert not any("实质相同" in w for w in warnings)


def test_note_escalates() -> None:
    assert scene_repeat_note(0) == ""
    first = scene_repeat_note(1)
    assert "停止点设在了目标兑现之前" in first
    hard = scene_repeat_note(2)
    assert "严重" in hard
    # 升级版必须给出可执行的动作，而不是重复「不要打转」。
    assert "既成事实" in hard
    assert "让玩家对X做出反应" in hard
