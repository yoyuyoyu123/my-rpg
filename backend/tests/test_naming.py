"""命名：Verbalized Sampling 挑选。

背景见 app/services/naming.py 与 docs/RESEARCH_MAP.md 第五节。
实测两局完全不同的游戏都把新世界落点命名为「青石镇」——模型的默认反应，
不是我们固化了案例。核心不变量：**程序永远不取众数**。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.naming import (  # noqa: E402
    NAME_PROBABILITY_CEILING, NAME_PROBABILITY_FLOOR, NAMING_INSTRUCTION,
    clean_candidates, pick_name,
)
from app.services.story_planner import parse_story_runtime  # noqa: E402


def _c(*pairs) -> list[dict]:
    return [{"name": n, "probability": p} for n, p in pairs]


# ── 挑选规则 ────────────────────────────────────────────────────

def test_never_picks_the_mode() -> None:
    """
    整件事的核心不变量。模型直接输出的那个就是众数，也就是最陈词滥调的
    那个——「青石镇」正是这么来的。
    """
    name, _ = pick_name(_c(("青石镇", 0.55), ("陈家渡", 0.15), ("窑坳", 0.10)))
    assert name != "青石镇"
    assert name == "窑坳"


def test_ignores_the_junk_tail() -> None:
    """概率地板以下多半是模型凑数硬编的，挑中会得到不合世界观的名字。"""
    name, _ = pick_name(_c(("青石镇", 0.60), ("陈家渡", 0.30), ("咕噜噜", 0.01)))
    assert name == "陈家渡"


def test_all_probabilities_zero_falls_back() -> None:
    """
    模型经常懒得填概率（全 0）。这时概率没有信息量，退回第一个即可——
    至少不比直接生成差，不能因此崩掉。
    """
    name, why = pick_name(_c(("陈家渡", 0.0), ("窑坳", 0.0)))
    assert name == "陈家渡"
    assert "无效" in why


def test_narrow_distribution_is_reported() -> None:
    """
    候选全挤在高概率区，说明模型没给出真正不同的选项。仍然取最低的，
    但要在说明里点出来——否则这种失败会静默发生，看不出命名为何还是很土。
    """
    name, why = pick_name(_c(("青石镇", 0.50), ("白石镇", 0.45)))
    assert name == "白石镇"
    assert "分布过窄" in why


def test_empty_candidates_are_safe() -> None:
    assert pick_name([]) == ("", "没有可用候选")
    assert pick_name([{"probability": 0.5}]) == ("", "没有可用候选")


def test_selection_is_deterministic() -> None:
    """
    回放基线要求确定性协议回放每次结果相同（docs/REPLAY_BASELINE.md），
    所以这里不能用随机采样。避开众数就是全部收益，随机性换不到额外多样性，
    只会破坏那条硬门。
    """
    cands = _c(("青石镇", 0.55), ("陈家渡", 0.20), ("窑坳", 0.12), ("鹞子口", 0.08))
    assert len({pick_name(cands)[0] for _ in range(20)}) == 1


# ── 候选清洗 ────────────────────────────────────────────────────

def test_percentages_are_normalised() -> None:
    """模型有时给 35 而不是 0.35。"""
    out = clean_candidates([{"name": "甲", "probability": 55}, {"name": "乙", "probability": 20}])
    assert out[0]["probability"] == 0.55 and out[1]["probability"] == 0.20


def test_alternate_key_names_are_accepted() -> None:
    """模型会写 p、会写中文键——这些都是它真的会输出的形态。"""
    out = clean_candidates([{"name": "甲", "p": 0.3}, {"候选": "乙", "概率": 0.2}])
    assert [c["name"] for c in out] == ["甲", "乙"]
    assert out[1]["probability"] == 0.2


def test_bare_strings_and_duplicates() -> None:
    out = clean_candidates(["甲", "甲", {"name": "乙", "probability": 0.4}, 123, None])
    assert [c["name"] for c in out] == ["甲", "乙"]


def test_garbage_probability_does_not_crash() -> None:
    out = clean_candidates([{"name": "甲", "probability": "很高"},
                            {"name": "乙", "probability": float("nan")},
                            {"name": "丙", "probability": -3}])
    assert all(0.0 <= c["probability"] <= 1.0 for c in out)


# ── 端到端 ──────────────────────────────────────────────────────

def _plan(new_names) -> str:
    return json.dumps({
        "premise": "x", "threads": [],
        "current_scene": {"id": "s", "title": "落点", "situation": "巷子里",
                          "purpose": "看清第一眼", "causal_bridge": "c",
                          "new_names": new_names},
    }, ensure_ascii=False)


def test_planner_output_is_resolved_to_one_name() -> None:
    runtime, warnings = parse_story_runtime(_plan([{
        "slot": "落点城镇", "kind": "place",
        "candidates": _c(("青石镇", 0.52), ("陈家渡", 0.18), ("窑坳", 0.11)),
    }]), {}, turn=0, reason="opening")
    picked = runtime.current_scene.new_names
    assert len(picked) == 1
    assert picked[0].chosen == "窑坳"
    assert picked[0].slot == "落点城镇"
    # 挑选理由要能在调试面板看到，命名出问题时不必猜
    assert any("命名「落点城镇」" in w for w in warnings)


def test_proposals_without_slot_or_candidates_are_dropped() -> None:
    runtime, _ = parse_story_runtime(_plan([
        {"slot": "", "candidates": _c(("甲", 0.3))},
        {"slot": "有名无候选", "candidates": []},
        "不是对象",
    ]), {}, turn=0, reason="opening")
    assert runtime.current_scene.new_names == []


def test_scenes_without_new_names_are_unaffected() -> None:
    runtime, warnings = parse_story_runtime(_plan([]), {}, turn=0, reason="opening")
    assert runtime.current_scene.new_names == []
    assert not any("命名「" in w for w in warnings)


def test_writer_is_given_the_decided_name() -> None:
    """挑定了却不告诉写手，等于没挑。"""
    from app.schemas.turn import TurnContext
    from app.services.prompt_builder import build_system_prompt
    sp = build_system_prompt(TurnContext(
        world_id="wuxia", pace="medium", turns=3, game_state={"revealed": True},
        story_runtime={"current_scene": {
            "id": "s", "title": "落点", "situation": "巷子里", "purpose": "看清第一眼",
            "new_names": [{"slot": "落点城镇", "chosen": "窑坳", "candidates": []}]}},
    ))
    assert "本幕要用的新专名" in sp
    assert "落点城镇=窑坳" in sp
    assert "不要另起别的名字" in sp


def test_planner_prompt_teaches_the_method() -> None:
    from app.schemas.story import StoryPlanContext
    from app.services.story_planner import build_story_plan_prompt
    p = build_story_plan_prompt(StoryPlanContext(world_id="fantasy"))
    assert "【新专名的产生方式】" in p
    assert '"new_names"' in p
    # 候选必须是真正不同的方案，否则分布过窄，挑了也白挑
    assert "不是同一个想法的换字版本" in p


def test_thresholds_are_ordered() -> None:
    assert 0.0 < NAME_PROBABILITY_FLOOR < NAME_PROBABILITY_CEILING < 1.0
    assert "0-1" in NAMING_INSTRUCTION


# ── 世界身份与命名语言 ──────────────────────────────────────────
#
# 实测一局「剑与魔法」：从头到尾没出现过魔法或异种族，村子叫「榆树村」。
# 剥掉旧状态栏之后，一个世界的活体身份只剩约 60 字，而同一份提示词里
# 状态协议 800 字、规则四千多字——60 字撑不住一个世界。

def test_every_world_declares_flavor_and_naming() -> None:
    from app.domain.worlds import WORLDS
    for wid, w in WORLDS.items():
        assert w.flavor.strip(), f"{wid} 没写「必须让玩家看见什么」"
        assert w.naming.strip(), f"{wid} 没写命名规矩"


def test_naming_rules_do_not_seed_copyable_names() -> None:
    """
    命名规矩本身在**固定前缀**里，每回合原样出现。如果给的是完整例名
    （「如陈家渡、黑水关」），等于亲手把陈词滥调播种进去——正是刚用
    Verbalized Sampling 修掉的那个 mode collapse。所以只描述构词法。
    """
    from app.domain.worlds import WORLDS
    seeded = ("陈家渡", "黑水关", "落霞涧", "青芜坊市", "艾尔登", "维恩堡", "青石镇", "榆树村")
    for wid, w in WORLDS.items():
        for name in seeded:
            assert name not in w.naming, f"{wid} 的命名规矩里播种了完整例名 {name}"


def test_fantasy_forbids_chinese_place_names() -> None:
    """玩家的原话：明明是剑与魔法，命名却非常中式。"""
    from app.domain.worlds import WORLDS
    naming = WORLDS["fantasy"].naming
    assert "禁止中式地名" in naming
    assert "榆树" in naming or "译音" in naming


def test_fantasy_demands_visible_fantasy_elements() -> None:
    """「从头到尾没显示出什么剑与魔法」——世界包自己都只说「重心是日常生活」。"""
    from app.domain.worlds import WORLDS
    flavor = WORLDS["fantasy"].flavor
    assert "冒险者公会" in flavor and "魔法" in flavor
    assert "开局就要让玩家看见其中至少两样" in flavor
    assert "不要写成没有魔法的乡村生活" in flavor


def test_world_identity_reaches_the_writer() -> None:
    from app.schemas.turn import TurnContext
    from app.services.prompt_builder import build_system_prompt
    sp = build_system_prompt(TurnContext(
        world_id="fantasy", pace="medium", turns=0, game_state={"revealed": False}))
    assert "【本世界必须让玩家看见的东西】" in sp
    assert "【本世界的命名规矩" in sp
    assert "禁止中式地名" in sp
    # 必须挨着世界包，不能被状态协议隔开——隔开就等于混进协议区
    assert sp.index("【本世界必须让玩家看见的东西】") < sp.index("【角色卡与状态协议")


def test_custom_world_is_not_given_a_builtin_identity() -> None:
    """自定义世界有自己的设定，套内置世界的味道和命名会直接打架。"""
    from app.schemas.turn import TurnContext
    from app.services.prompt_builder import build_system_prompt
    sp = build_system_prompt(TurnContext(
        world_id="fantasy", pace="medium", turns=0, game_state={"revealed": False},
        custom_world_prompt="一个由玩家自定义的世界"))
    assert "【本世界必须让玩家看见的东西】" not in sp
