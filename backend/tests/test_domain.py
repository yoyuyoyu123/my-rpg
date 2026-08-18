"""
领域数据测试
============
这些数据是从前端迁移过来的核心资产。测试确保迁移完整、结构自洽。

为什么值得测：数据是自动提取生成的，如果哪天提取脚本出错或前端结构变了，
这些断言会立刻发现，而不是等到玩的时候才发现某个世界观没提示词。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain import decks, rules, worlds  # noqa: E402


# ── 规则常量 ────────────────────────────────────────────────────

def test_core_rules_present() -> None:
    assert len(rules.CORE_RULES) > 1000, "核心叙事契约不应为空或过短"
    # 几条关键纪律必须在
    assert "不得替玩家" in rules.CORE_RULES, "行动授权协议丢失"
    assert "青石镇" in rules.CORE_RULES, "命名规范丢失"
    assert "【STATE】" in rules.CORE_RULES, "状态申报协议丢失"


def test_all_rule_constants_nonempty() -> None:
    for name in ["OPTION_RULES", "AGENCY_RULES", "ANTI_MYSTERY",
                 "NPC_KNOWLEDGE_RULES", "IDENTITY_FREEDOM",
                 "ISEKAI_MODERN", "GAMEWORLD_VARIANTS", "FIRST_CHAPTER"]:
        assert getattr(rules, name).strip(), f"{name} 是空的"


# ── 世界包 ──────────────────────────────────────────────────────

def test_ten_worlds() -> None:
    assert len(worlds.WORLDS) == 10


def test_every_world_has_prompt_and_presets() -> None:
    for wid, w in worlds.WORLDS.items():
        assert w.prompt.strip(), f"{wid} 缺提示词"
        assert w.name and w.family and w.skill_label, f"{wid} 缺基础字段"
        assert w.daily, f"{wid} 缺快捷动作"
        assert w.presets, f"{wid} 缺特色预设"


def test_families_are_the_five_known_ones() -> None:
    fams = {w.family for w in worlds.WORLDS.values()}
    assert fams == {"东方", "幻想", "现代", "未来", "末日恐怖"}


# ── 抽取池的引用完整性（这类 bug 最难靠肉眼发现）──────────────────

def test_world_expansion_keys_resolve() -> None:
    """世界观 → 身份扩展 的映射不能指向不存在的条目。"""
    for wid, key in decks.WORLD_EXPANSION_KEYS.items():
        assert wid in worlds.WORLDS, f"映射里的世界观 {wid} 不存在"
        assert key in rules.WORLD_EXPANSIONS, f"{wid} 指向的扩展 {key} 不存在"


def test_preset_expansion_keys_resolve() -> None:
    """预设 → 身份扩展 的映射同理。"""
    known_presets = {p.id for w in worlds.WORLDS.values() for p in w.presets}
    for pid, key in decks.PRESET_EXPANSION_KEYS.items():
        assert pid in known_presets, f"映射里的预设 {pid} 在任何世界观里都不存在"
        assert key in rules.WORLD_EXPANSIONS, f"{pid} 指向的扩展 {key} 不存在"


def test_every_world_has_state_schema() -> None:
    """每个世界观都要有角色卡模板，否则开局就会崩。"""
    for wid in worlds.WORLDS:
        assert wid in decks.STATE_SCHEMAS, f"{wid} 缺角色卡模板"
    assert "__custom__" in decks.STATE_SCHEMAS, "自定义世界缺兜底模板"


@pytest.mark.parametrize("wid", list(decks.STATE_SCHEMAS))
def test_state_schema_shape(wid: str) -> None:
    """模板必须是 4 属性，且资源上限只针对存在的资源。"""
    sc = decks.STATE_SCHEMAS[wid]
    assert len(sc["attrs"]) == 4, f"{wid} 的属性不是 4 个"
    assert sc["res"], f"{wid} 没有资源"
    for cap_key in sc["caps"]:
        assert cap_key in sc["res"], f"{wid} 的上限 {cap_key} 没有对应资源"


def test_pref_maps_point_to_real_pools() -> None:
    """玩家的口味约束必须能落到真实存在的选项上。"""
    opening_names = {n for n, _ in decks.OPENING_STYLES} | {n for n, _ in decks.OPENING_STYLES_X}
    for label, allowed in decks.PREF_MAPS["opening"].items():
        for name in allowed:
            assert name in opening_names, f"约束「{label}」指向不存在的开局 {name}"

    for label, engines in decks.ENGINE_BUCKETS.items():
        assert label in decks.PREF_MAPS["skeleton"], f"引擎桶 {label} 没有对应的玩家约束"


def test_pace_config_complete() -> None:
    assert set(decks.PACE_CONFIG) == {"short", "medium", "long"}
    for k, v in decks.PACE_CONFIG.items():
        assert v["instruction"].strip(), f"{k} 缺篇幅指令"
