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


# ── 转移途中／首次落地一律略写 ──────────────────────────────────

def _plan_scene(end_phase, narration="scene", conflict="", pressure=1):
    import json
    return json.dumps({
        "premise": "x", "threads": [],
        "current_scene": {"id": "s", "title": "跨入阈限", "situation": "白光里",
                          "purpose": "跨过去", "causal_bridge": "c",
                          "narration": narration, "premise_phase": end_phase,
                          "conflict": conflict, "pressure_budget": pressure},
    }, ensure_ascii=False)


def _ps(phase):
    return {"kind": "transmigration", "phase": phase, "startedAt": 10**6, "fast": True}


def test_transit_without_a_declared_conflict_falls_back_to_summary() -> None:
    """
    默认：转移途中是纯过程，略写。

    实测一局 VR 路线：规划器把阶段 3 的「跨入阈限」规划成详写，占掉回合
    5 和 6，回合 7 才略写，回合 8 被强制接管。玩家原话是「戴个 VR 头显
    还在虚空里走半天」。规则 8b 早就写着「只有过程中真的发生冲突时才详写」，
    规划器照样无视——所以改成举证：说不出冲突就按纯过程处理。
    """
    from app.services.story_planner import parse_story_runtime
    for end_phase in (3, 4):
        runtime, warnings = parse_story_runtime(
            _plan_scene(end_phase), {}, turn=5, reason="horizon",
            premise_state=_ps(end_phase - 1), pace="long")
        scene = runtime.current_scene
        assert scene.narration == "summary", f"phase={end_phase}"
        assert scene.summary_target, "强制略写必须同时给出终点，否则写手无从下手"
        assert any("未声明冲突" in w for w in warnings)
        # 略写幕只占一个回合，两条规则要串起来才有意义
        assert scene.refresh_after_turn == 6


def test_transit_with_a_real_conflict_stays_detailed() -> None:
    """
    例外：过程中真的出事就不再是纯过程，该详写。

    「穿越途中发生冲突」是玩家明确点出的合法情形——有人中途拦截、机制
    故障、途中必须当场做选择。程序不替规划器判断有没有冲突，只要求它
    把冲突说出来。
    """
    from app.services.story_planner import parse_story_runtime
    runtime, warnings = parse_story_runtime(
        _plan_scene(3, conflict="守门的旧程序拦下玩家，要求他交出通行凭证才放行", pressure=3),
        {}, turn=5, reason="horizon", premise_state=_ps(2), pace="long")
    scene = runtime.current_scene
    assert scene.narration == "scene"
    assert "旧程序拦下玩家" in scene.conflict
    assert any("声明了冲突" in w for w in warnings)
    # 详写幕不受「略写只占一回合」约束
    assert scene.refresh_after_turn > 6


def test_vacuous_conflict_does_not_buy_detail() -> None:
    """
    举证得是具体的。「有阻力」这种空话不算，否则这道闸等于没有——
    规划器只要反射性填一个字段就能拿回详写。
    """
    from app.services.story_planner import parse_story_runtime
    runtime, _ = parse_story_runtime(
        _plan_scene(3, conflict="有阻力", pressure=3),
        {}, turn=5, reason="horizon", premise_state=_ps(2), pace="long")
    assert runtime.current_scene.narration == "summary"


def test_conflict_without_pressure_does_not_buy_detail() -> None:
    """
    真正的冲突必然带压力。要求 pressure_budget≥2 是第二道独立信号，
    让「随手填个 conflict 换详写」有代价——压力预算受硬规则 8 约束，
    不能凭空抬高。
    """
    from app.services.story_planner import parse_story_runtime
    runtime, _ = parse_story_runtime(
        _plan_scene(3, conflict="守门的旧程序拦下玩家，要求他交出通行凭证", pressure=1),
        {}, turn=5, reason="horizon", premise_state=_ps(2), pace="long")
    assert runtime.current_scene.narration == "summary"


def test_writer_is_told_what_the_conflict_is() -> None:
    """
    详写的理由要传给写手。不告诉它冲突是什么，它只能靠加细节把篇幅填满
    ——那正是「越描越细但没推进」的来路。
    """
    from app.schemas.turn import TurnContext
    from app.services.prompt_builder import build_system_prompt
    sp = build_system_prompt(TurnContext(
        world_id="wuxia", pace="long", turns=5, game_state={"revealed": True},
        story_runtime={"current_scene": {
            "id": "s", "title": "跨入阈限", "situation": "白光里", "purpose": "跨过去",
            "narration": "scene", "pressure_budget": 3,
            "conflict": "守门的旧程序拦下玩家，要求他交出通行凭证才放行"}},
    ))
    assert "本幕的冲突" in sp and "守门的旧程序拦下玩家" in sp


def test_threshold_scene_stays_detailed() -> None:
    """阶段 2（阈限）是玩家最后一次真正的选择，必须留给详写。"""
    from app.services.story_planner import parse_story_runtime
    runtime, _ = parse_story_runtime(
        _plan_scene(2), {}, turn=5, reason="horizon",
        premise_state=_ps(1), pace="long")
    assert runtime.current_scene.narration == "scene"


def test_ordinary_scenes_are_untouched() -> None:
    """非穿越局 premise_phase 是 None，不能被这条规则误伤。"""
    from app.services.story_planner import parse_story_runtime
    runtime, _ = parse_story_runtime(
        _plan_scene(None), {}, turn=5, reason="horizon")
    assert runtime.current_scene.narration == "scene"


# ── 命名 ────────────────────────────────────────────────────────

def test_name_table_is_derived_from_authoritative_facts() -> None:
    """
    命名表本来是死代码：没有任何提示词要求模型输出【命名表】块，
    翻遍全部历史导出一次都没产出过，ctx.names 恒为空。
    改成从 game_state 里已有的地点和 NPC 推导，零成本且不会和状态栏对不上。
    """
    from app.schemas.turn import TurnContext
    from app.services.prompt_builder import build_system_prompt, derived_name_table
    ctx = TurnContext(
        world_id="wuxia", pace="medium", turns=3,
        game_state={"revealed": True, "loc": "陈家渡渡口",
                    "npcs": {"吴四娘": {"rel": "邻居"}, "王掌柜": {"rel": "债主"}}},
    )
    table = derived_name_table(ctx)
    assert "陈家渡渡口" in table and "吴四娘" in table and "王掌柜" in table
    assert "【命名表" in build_system_prompt(ctx)


def test_explicit_name_table_wins_over_derived() -> None:
    from app.schemas.turn import TurnContext
    from app.services.prompt_builder import build_system_prompt
    ctx = TurnContext(
        world_id="wuxia", pace="medium", turns=3, names="地点：黑水峪",
        game_state={"revealed": True, "loc": "陈家渡渡口", "npcs": {}},
    )
    sp = build_system_prompt(ctx)
    assert "黑水峪" in sp


def test_naming_rule_demands_a_local_reason() -> None:
    """
    旧规则只说「避免跨题材模板名和夸张堆砌」——「青石镇」两样都不沾，
    正好从缝里漏过去。两局完全不同的游戏都落到了这个名字。
    """
    from app.domain.rules import CORE_RULES
    assert "名字必须从那件具体的事里长出来" in CORE_RULES
    assert "通用形容词／颜色／材质＋镇村城" in CORE_RULES
    assert "换个世界也一样贴切" in CORE_RULES


# ── 热奈特的时距与频率 ──────────────────────────────────────────
#
# 时距(duration)=故事时长 vs 叙述篇幅；频率(frequency)=发生几次 vs 叙述几次。
# 见 docs/RESEARCH_MAP.md 第四节。
#
# 记一笔教训：最早那个「同一件事换角度写 11 回合」其实是**频率**问题，
# 当时当成时距问题修，方向偏了。两个维度分开就是为了不再混淆。

def _card(**kw) -> str:
    import json
    scene = {"id": "s", "title": "t", "situation": "官道上", "purpose": "跨过三天",
             "causal_bridge": "c"}
    scene.update(kw)
    return json.dumps({"premise": "x", "threads": [], "current_scene": scene},
                      ensure_ascii=False)


def _sp(**scene):
    from app.schemas.turn import TurnContext
    from app.services.prompt_builder import build_system_prompt
    base = {"id": "s", "title": "t", "situation": "官道上", "purpose": "p"}
    base.update(scene)
    return build_system_prompt(TurnContext(
        world_id="wuxia", pace="long", turns=5, game_state={"revealed": True},
        story_runtime={"current_scene": base}))


def test_ellipsis_is_accepted_and_compresses_hardest() -> None:
    """
    省略是比略写更狠的一档：略写还写过程，省略连过程都不写。
    玩家说「等三天」时此前只能走略写——写手仍会交代这段时间的见闻和心情，
    几百字下来什么也没发生。
    """
    from app.services.story_planner import parse_story_runtime
    runtime, _ = parse_story_runtime(
        _card(narration="ellipsis", summary_target="跨过三天，停在回到码头的那一刻"),
        {}, turn=10, reason="horizon")
    assert runtime.current_scene.narration == "ellipsis"
    # 压缩类的幕都只占一个回合
    assert runtime.current_scene.refresh_after_turn == 11


def test_ellipsis_without_a_target_falls_back() -> None:
    """没说要跨过什么，写手无从下手，只会又开始逐步描写。"""
    from app.services.story_planner import parse_story_runtime
    runtime, warnings = parse_story_runtime(
        _card(narration="ellipsis"), {}, turn=10, reason="horizon")
    assert runtime.current_scene.narration == "scene"
    assert any("省略场景缺少 summary_target" in w for w in warnings)


def test_ellipsis_rules_reach_the_writer() -> None:
    sp = _sp(narration="ellipsis", summary_target="跨过三天，停在回到码头那一刻")
    assert "【本幕省略" in sp
    assert "用一到两句话跨过去" in sp
    assert "不要写这段时间里的见闻、心情起伏或琐事" in sp
    # 省略挂的是省略规则，不能同时挂略写规则
    assert "【本幕略写" not in sp


def test_summary_still_gets_its_own_rules() -> None:
    sp = _sp(narration="summary", summary_target="带过整段赶路")
    assert "【本幕略写" in sp and "【本幕省略" not in sp


def test_stretch_and_pause_are_not_valid_options() -> None:
    """
    热奈特还有延缓和停顿两档，我们刻意不实现——那两档正是这个引擎反复
    犯的毛病（把一个瞬间铺开写、故事时间停住纯描写）。做成合法选项等于
    把模型最容易滥用的两把刀递过去。非法取值一律退回详写。
    """
    from app.services.story_planner import parse_story_runtime
    for bad in ("stretch", "pause", "延缓", "随便"):
        runtime, _ = parse_story_runtime(
            _card(narration=bad, summary_target="x"), {}, turn=10, reason="horizon")
        assert runtime.current_scene.narration == "scene", bad


def test_iterative_frequency_is_told_to_the_writer() -> None:
    """
    不说明的话写手会把「每天去码头」写成某一个具体的早晨——那就变回单次
    场景了，压缩日常的效果全部失掉。
    """
    sp = _sp(frequency="iterative")
    assert "叙事频率:反复" in sp
    assert "不要写成某一个具体的日子" in sp


def test_once_is_the_default_and_silent() -> None:
    from app.services.story_planner import parse_story_runtime
    runtime, _ = parse_story_runtime(_card(), {}, turn=10, reason="horizon")
    assert runtime.current_scene.frequency == "once"
    assert "叙事频率" not in _sp()


def test_invalid_frequency_falls_back_to_once() -> None:
    from app.services.story_planner import parse_story_runtime
    runtime, _ = parse_story_runtime(
        _card(frequency="repeating"), {}, turn=10, reason="horizon")
    # 「重复叙述」（发生一次却叙述多遍）没有合法取值——那就是我们一直在
    # 打的那个 bug，由 spent_scenes 的重复检测负责拦截。
    assert runtime.current_scene.frequency == "once"


def test_duration_and_frequency_are_independent() -> None:
    """日常修炼通常是 iterative + summary：反复发生，压成一段。"""
    from app.services.story_planner import parse_story_runtime
    runtime, _ = parse_story_runtime(
        _card(narration="summary", summary_target="半个月的早课", frequency="iterative"),
        {}, turn=10, reason="horizon")
    assert runtime.current_scene.narration == "summary"
    assert runtime.current_scene.frequency == "iterative"
    sp = _sp(narration="summary", summary_target="半个月的早课", frequency="iterative")
    assert "叙事频率:反复" in sp and "【本幕略写" in sp


def test_planner_learns_both_dimensions() -> None:
    from app.schemas.story import StoryPlanContext
    from app.services.story_planner import build_story_plan_prompt
    p = build_story_plan_prompt(StoryPlanContext(world_id="wuxia"))
    assert 'narration="ellipsis"' in p
    assert "8c." in p and 'frequency="iterative"' in p
    # 必须点明两者是不同的维度，否则模型会拿一个当另一个用
    assert "它和 narration 是两回事" in p
    assert '"frequency":"once|iterative"' in p
