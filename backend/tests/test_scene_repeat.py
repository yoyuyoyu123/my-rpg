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


# ── 已演记账（storylet 的「可重复性」维度）──────────────────────
#
# Kreminski & Wardrip-Fruin 的分类法把「这个 storylet 用过了没有」列为
# 设计时就要回答的一维（docs/RESEARCH_MAP.md 第二节）。我们此前的答案是
# 最弱的一档：拿新 purpose 和**上一幕**比字符重合度。

def _card(purpose: str, sid: str, repeatable: bool = False) -> str:
    return json.dumps({
        "premise": "x", "threads": [],
        "current_scene": {"id": sid, "title": f"幕{sid}", "situation": "s",
                          "purpose": purpose, "causal_bridge": "c",
                          "repeatable": repeatable},
    }, ensure_ascii=False)


def test_non_adjacent_repeat_is_caught() -> None:
    """
    这条是加已演记账的全部理由。

    改之前实测：A→B→A 的第三幕完全检测不到——只比上一幕的话，中间隔一幕
    就绕过去了。规划器完全可能这么写，而玩家感受到的就是原地打转。
    """
    r1, _ = parse_story_runtime(_card(PURPOSE_T7, "s1"), {}, 0, "opening")
    r2, _ = parse_story_runtime(_card(PURPOSE_DIFF, "s2"), r1.model_dump(), 4, "horizon")
    r3, warnings = parse_story_runtime(_card(PURPOSE_T7, "s3"), r2.model_dump(), 8, "horizon")
    assert r3.scene_repeat_count == 1
    assert any("已演过的「幕s1」" in w for w in warnings)


def test_spent_list_records_finished_scenes_only() -> None:
    """换了 id 才算演完。同一个 id 是这一幕的延续，不该记账。"""
    r1, _ = parse_story_runtime(_card(PURPOSE_T7, "s1"), {}, 0, "opening")
    assert r1.spent_scenes == []          # 第一幕之前什么都没演过

    r2, _ = parse_story_runtime(_card(PURPOSE_DIFF, "s2"), r1.model_dump(), 4, "horizon")
    assert [s.id for s in r2.spent_scenes] == ["s1"]

    # 同 id 续演：不新增记账
    r2b, _ = parse_story_runtime(_card(PURPOSE_DIFF, "s2"), r2.model_dump(), 6, "horizon")
    assert [s.id for s in r2b.spent_scenes] == ["s1"]


def test_repeatable_scenes_are_allowed_through() -> None:
    """
    有些幕本来就该复现：固定的出摊、每周的例会、反复去同一个铺子打听。
    判断权归规划器，程序只要求它把「这是可复现的日常」说出来。
    """
    r1, _ = parse_story_runtime(_card(PURPOSE_T7, "s1"), {}, 0, "opening")
    r2, _ = parse_story_runtime(_card(PURPOSE_DIFF, "s2"), r1.model_dump(), 4, "horizon")
    r3, warnings = parse_story_runtime(
        _card(PURPOSE_T7, "s3", repeatable=True), r2.model_dump(), 8, "horizon")
    assert r3.scene_repeat_count == 0
    # 放行也要留痕，免得「万物皆可复现」变成绕过检测的后门
    assert any("已声明为可复现的日常模式，放行" in w for w in warnings)


def test_spent_list_is_capped() -> None:
    """
    这个列表要进提示词。无限增长会把世界设定和已检索事实挤出窗口——
    账本挤掉 loc/npcs 那次就是这么发生的。
    """
    from app.services.story_planner import SPENT_SCENE_LIMIT
    runtime, prev = None, {}
    for i in range(SPENT_SCENE_LIMIT + 6):
        runtime, _ = parse_story_runtime(
            _card(f"第 {i} 件完全不同的事，与其他各幕毫无关联{i}", f"s{i}"),
            prev, i, "horizon")
        prev = runtime.model_dump()
    assert len(runtime.spent_scenes) == SPENT_SCENE_LIMIT
    # 留的是最近的
    assert runtime.spent_scenes[-1].id == f"s{SPENT_SCENE_LIMIT + 4}"


def test_planner_sees_what_has_been_played() -> None:
    """
    程序检测是兜底。让规划器一开始就看见「这些演过了」才是正路——
    它此前只看得到上一幕。
    """
    from app.schemas.story import StoryPlanContext
    from app.services.story_planner import build_story_plan_prompt
    p = build_story_plan_prompt(StoryPlanContext(
        world_id="wuxia", pace="medium", turn=9, reason="horizon",
        story_runtime={
            "current_scene": {"id": "s3", "purpose": "眼下这一幕"},
            "spent_scenes": [{"id": "s1", "title": "码头的争执",
                              "purpose": "让玩家看清谁在收保护费", "turn": 0}],
        },
    ))
    assert "【已经演过的幕——不要再规划一次】" in p
    assert "码头的争执" in p and "让玩家看清谁在收保护费" in p
    assert "本幕的 purpose 必须是它们之后的**下一件**事" in p
    # 例外路径也要写明，否则合理的日常复现会被堵死
    assert "repeatable 设为 true" in p
