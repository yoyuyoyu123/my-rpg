"""研究库标签的抽样：在固定范围里抽，制造局间差异。

背景
----
研究库（551 部作品 / 2876 条原始标签 / 17 类本体）此前一个字都没进过提示词：
内置世界根本没有 inspirationTags 字段，只有自定义世界的手动勾选会填，
而且 agent 模式下写手那一侧整个跳过。玩家的问题是「明明有标签库，
为什么世界观还是趋同」。

直接手挑十个代表标签行不通——那只是换一种方式趋同，每局都一样。
本体的 17 类是正交轴，这才是「固定范围」：范围固定住题材，抽样制造差异。
池子由 tools/build_tag_pools.py 从本体和语料生成（见那个文件的说明）。

三个硬约束
----------
1. **确定性**：回放基线要求确定性协议回放每次结果相同
   （docs/REPLAY_BASELINE.md），所以不能用 random，种子必须可复现。
2. **局内稳定**：标签进的是提示词的固定前缀区。每回合重抽会让前缀每回合
   都变，直接毁掉各家的前缀缓存——那是这个项目省钱的主要手段。所以种子
   取自「一局之内不变」的东西。
3. **局间不同**：这才是加它的理由。种子里必须有随局变化的成分。

种子取 story_dna（开局生成、一局之内不变、每局不同）加世界与预设。
story_dna 缺失时退回开局正文，再缺就只剩世界 id——那种情况下同世界的
每一局会抽到同样的配方，属于可接受的退化，但会在返回值里标出来。
"""
from __future__ import annotations

import json
import os
from typing import Any

_POOLS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tag_pools.json")

with open(_POOLS_PATH, encoding="utf-8") as _fh:
    _POOLS: dict[str, Any] = json.load(_fh)

WORLD_POOLS: dict[str, Any] = _POOLS.get("worlds") or {}

# 每条轴抽几个。取 1：轴本身就是维度，一条轴抽两个等于自相矛盾
# （既「资源不足」又「政治权力」是两台发动机，不是一个配方）。
PICKS_PER_AXIS = 1

# 轴 id → 给模型看的名字。本体里的 label 偏学术（「成长与爽感结构」），
# 这里换成提示词里读着顺的说法。
AXIS_LABEL = {
    "conflict_source": "冲突来源",
    "growth_mode": "成长方式",
    "information_structure": "信息结构",
    "relationship": "关系结构",
    "pacing": "节奏",
    "story_engine": "故事发动机",
    "cn_web_trope": "母题",
    "jp_web_trope": "母题",
    "manga_form": "叙事形式",
}

# 抽样顺序固定，保证同一种子每次得到同样的配方；也让提示词里的顺序稳定。
AXIS_ORDER = [
    "conflict_source", "story_engine", "growth_mode",
    "relationship", "information_structure", "pacing",
    "cn_web_trope", "jp_web_trope", "manga_form",
]


def _fnv(text: str) -> int:
    """FNV-1a 32 位。和 prompt_builder.debug_hash 同一套，不引入随机数依赖。"""
    h = 2166136261
    for ch in str(text or ""):
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def run_seed(world_id: str, preset_id: str, story_dna: str, opening_text: str) -> tuple[str, bool]:
    """返回 (种子文本, 是否有随局变化的成分)。"""
    varying = str(story_dna or "").strip() or str(opening_text or "").strip()
    seed = f"{world_id}|{preset_id}|{varying}"
    return seed, bool(varying)


def sample_recipe(
    world_id: str,
    preset_id: str = "",
    story_dna: str = "",
    opening_text: str = "",
) -> dict[str, Any]:
    """为这一局抽一份叙事配方。

    返回 {"picks": [(轴名, 标签), ...], "frames": [...], "stable": bool}。
    stable=False 表示种子里没有随局变化的成分，同世界每局配方相同。
    """
    pool = WORLD_POOLS.get(world_id)
    if not pool:
        return {"picks": [], "frames": [], "stable": False}

    seed, varying = run_seed(world_id, preset_id, story_dna, opening_text)
    axes = pool.get("axes") or {}
    picks: list[tuple[str, str]] = []
    for axis in AXIS_ORDER:
        tags = axes.get(axis)
        if not tags:
            continue
        # 每条轴用自己的子种子，否则相邻轴会被同一个哈希带着一起走。
        idx = _fnv(f"{seed}#{axis}") % len(tags)
        picks.append((AXIS_LABEL.get(axis, axis), tags[idx]))
    return {"picks": picks, "frames": list(pool.get("frames") or []), "stable": varying}


def recipe_line(recipe: dict[str, Any]) -> str:
    """配方渲染成提示词里的一行。

    措辞是要紧的。此前研究库那一行写的是「兼容灵感候选——**只在自然相容时
    选用**」，那等于告诉模型可以无视它；实测那一局里它连一个标签都没用上
    （其实列表本来就是空的，但措辞同样是问题）。
    这里改成「取材优先从这里取」，同时明说不是必须逐条出现——既要它真的
    用，又不能变成把九个标签硬塞进正文的清单。
    """
    picks = recipe.get("picks") or []
    if not picks:
        return ""
    body = "｜".join(f"{k}={v}" for k, v in picks)
    return (
        "【本局叙事配方——研究库按本世界题材抽样，用来把这一局和别的局区分开】"
        + body
        + "。这是**取材方向**：需要安排冲突、发动机、关系或节奏时优先从这里取，"
        "不是必须逐条写进正文的清单，也不要用它替换玩家已经确立的事实。"
    )
