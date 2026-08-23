"""命名：用 Verbalized Sampling 绕开模型的默认偏好。

问题
----
实测两局完全不同的游戏（工坊铜钱路线、VR 路线），新世界的落点都被命名为
「青石镇」。这个词最早出现在写手的**输出**里，任何提示词输入都没有它——
不是我们固化了案例，是模型自己的默认反应。

学名叫 mode collapse。根因在训练数据层：偏好数据的标注者系统性偏好
「熟悉的」文本（typicality bias），于是对齐后的模型收敛到最典型的表达。
**这不是提示词能根治的问题**——我们已经写过一条「名字必须从这地方靠什么
活着、地形、历史里长出来」的规则，它仍然是软规则，约束不住模型。

做法
----
Verbalized Sampling（arXiv 2510.01171）：不让模型直接给一个答案，而是让它
**列出若干候选并给出各自概率**，再从分布里挑——而不是取众数。论文在创意
写作上测得多样性提升 1.6-2.1 倍，且不损失事实准确性，是免训练的纯提示词
技巧。

关键洞察：**模型直接输出的那个，就是分布的众数，也就是最陈词滥调的那个。**
所以只要不取众数就有收益。

我们的分工照旧：模型负责生成候选和自评概率（表达），程序负责挑（保证）。

为什么是确定性挑选
------------------
不用随机采样，取「概率最低但不低于地板」的那个。两个理由：

1. 回放基线要求确定性协议回放每次给出相同结果（见 docs/REPLAY_BASELINE.md），
   引入随机数会直接破坏那条硬门；
2. 地板本身就够用了——排除众数就是全部收益所在，再引入随机性只是让
   结果不可复现，换不到额外的多样性。

参考：docs/RESEARCH_MAP.md 第五节。
"""
from __future__ import annotations

from typing import Any

# 候选数量。论文用的是 5，我们照抄——太少覆盖不到分布尾部，
# 太多则每次规划都要多付一截输出 token。
NAME_CANDIDATE_COUNT = 5

# 概率地板。低于这个值的候选多半是模型为了凑数硬编的，
# 挑中了会得到明显不合世界观的名字。
NAME_PROBABILITY_FLOOR = 0.05

# 概率天花板。高于这个值基本就是众数——正是要避开的那个。
# 只有在所有候选都超过它时才会退而求其次（见 pick_name）。
NAME_PROBABILITY_CEILING = 0.40


def _prob(value: Any) -> float:
    try:
        p = float(value)
    except (TypeError, ValueError):
        return 0.0
    if p != p or p in (float("inf"), float("-inf")):  # NaN / inf
        return 0.0
    # 模型有时给百分数（35 而不是 0.35），按比例还原
    if p > 1.0:
        p = p / 100.0
    return max(0.0, min(1.0, p))


def clean_candidates(raw: Any, limit: int = NAME_CANDIDATE_COUNT * 2) -> list[dict]:
    """把模型给的候选整理成 [{"name": str, "probability": float}]。"""
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for item in raw[:limit]:
        if isinstance(item, str):
            name, prob = item.strip(), 0.0
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("候选") or "").strip()
            prob = _prob(item.get("probability", item.get("p", item.get("概率"))))
        else:
            continue
        name = name[:40]
        if not name or name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "probability": prob})
    return out


def pick_name(candidates: list[dict]) -> tuple[str, str]:
    """从候选里挑一个，返回 (选中的名字, 说明)。

    说明字段会进 warnings，让调试面板能看出程序为什么挑了这个——
    命名出问题时不必猜。
    """
    usable = [c for c in candidates if c.get("name")]
    if not usable:
        return "", "没有可用候选"

    # 正常情况：避开众数，也避开明显是凑数的尾巴。
    band = [c for c in usable
            if NAME_PROBABILITY_FLOOR <= c["probability"] <= NAME_PROBABILITY_CEILING]
    if band:
        chosen = min(band, key=lambda c: c["probability"])
        return chosen["name"], (
            f"从 {len(usable)} 个候选中取概率最低者 {chosen['name']}"
            f"（p={chosen['probability']:.2f}）"
        )

    # 所有候选都在地板以下：模型没认真给概率（常见的是全填 0）。
    # 这时概率没有信息量，退回第一个，至少不比直接生成差。
    above_floor = [c for c in usable if c["probability"] >= NAME_PROBABILITY_FLOOR]
    if not above_floor:
        return usable[0]["name"], "候选概率全部无效，退回第一个"

    # 所有候选都在天花板以上：分布过于集中，说明模型没给出真正不同的选项。
    # 仍然取最低的那个，聊胜于无，但要在说明里点出来。
    chosen = min(above_floor, key=lambda c: c["probability"])
    return chosen["name"], (
        f"候选概率全部偏高（分布过窄，模型没给出真正不同的选项），"
        f"取最低者 {chosen['name']}（p={chosen['probability']:.2f}）"
    )


# 写进规划器提示词的说明。单独抽出来，是因为它要同时被提示词和测试引用。
NAMING_INSTRUCTION = (
    "【新专名的产生方式】\n"
    "本幕如果要引入**当前还不存在的**地名、势力名或人名，不要直接写定一个，"
    f"而是在 new_names 里为每个新专名列出 {NAME_CANDIDATE_COUNT} 个候选，"
    "并给出每个候选「在你看来有多大概率是这个世界会用的名字」（0-1，加起来约等于 1）。\n"
    "候选必须是**真正不同的方案**，不是同一个想法的换字版本："
    "分别从这地方靠什么活着、地形有什么特别、历史上出过什么事、"
    "谁世代把持着它等不同角度各起一个。\n"
    "程序会从中挑选并写进命名表，你不必自己决定用哪个。"
    "不引入新专名时 new_names 留空数组。"
)
