"""从研究库生成每个世界的标签抽样池。

为什么需要这一步
----------------
研究库有 551 部作品、2876 条原始标签、17 类本体，但一个字都没进过提示词：
内置世界的 inspirationTags 字段根本不存在（只有自定义世界的手动勾选会填），
而且 agent 模式下写手那一侧整个跳过。玩家的问题是「明明有标签库，为什么
世界观还是趋同」。

直接手挑十个代表标签是行不通的——那只是换一种方式趋同，每局都一样。
要的是**在固定范围里抽**：范围固定住题材，抽样制造局间差异。

固定范围怎么来
--------------
本体的 17 类是正交轴（主角来历、故事发动机、冲突来源、基调、节奏……），
这本身就是那个「固定范围」。每局在选定的几条轴上各抽一个，组合出变化。
唯一的人工输入是「哪个世界对应哪些 world_frame 题材锚点」——2-7 个，
一眼可验，不是凭空挑十个。

两类轴分开处理
--------------
- **题材无关轴**（冲突来源、基调、节奏、信息结构、成长模式）：整条轴都可用。
  这些词在任何题材下都成立，用本体的完整列表。
- **题材相关轴**（故事发动机、中日网文母题、漫画形式）：只保留语料里
  和本世界题材共现过的标签。这里用语料是因为它有真实证据；但语料很薄
  （武侠只命中 6 部、赛博 7 部），所以它只用来**筛**题材相关轴，不用来
  加权，也不碰题材无关轴——薄样本的频次没有统计意义。

输出 backend/app/domain/tag_pools.json，由 app/domain/tag_pool.py 在运行时读取。
重新生成：python tools/build_tag_pools.py
"""
from __future__ import annotations

import collections
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESEARCH = os.path.join(ROOT, "research")
OUT = os.path.join(ROOT, "backend", "app", "domain", "tag_pools.json")

# 世界 → world_frame 题材锚点。
#
# 这是全文件唯一的人工映射。取值必须来自本体的 world_frame（79 个），
# 拼错会在校验时报错。选多个是因为一个世界本来就覆盖若干子题材——
# 「剑与魔法」的预设里就有王道/学院/黑暗三种。
WORLD_FRAMES: dict[str, list[str]] = {
    "wuxia": ["武侠江湖", "新武侠", "国术现代", "架空历史", "朝堂官场"],
    "xianxia": ["古典仙侠", "现代修仙", "凡俗仙侠", "东方玄幻", "民俗志怪", "香火神道"],
    "history": ["历史正剧", "架空历史", "古代市井", "年代生活", "朝堂官场", "乡村田园"],
    "fantasy": ["西式奇幻", "低魔奇幻", "高魔奇幻", "黑暗奇幻", "学院奇幻",
                "地下城社会", "异世界幻想", "多种族社会"],
    "modernlife": ["现代都市", "现实职业", "校园青春", "娱乐行业", "美食餐饮",
                   "体育竞技", "医疗行业", "法律行业", "科研学术", "商业金融"],
    "occult": ["都市异能", "都市奇幻", "现代怪谈", "规则怪谈", "异常收容", "超级英雄社会"],
    "cyber": ["赛博朋克", "后赛博朋克", "近未来科幻", "虚拟现实", "人工智能社会",
              "生物朋克", "反乌托邦"],
    "space": ["太空歌剧", "星际殖民", "硬科幻", "机甲战争", "近未来科幻"],
    "apocalypse": ["末日求生", "废土重建", "灾后新文明", "封闭空间"],
    "horror": ["克苏鲁神话", "规则怪谈", "现代怪谈", "异常收容", "封闭空间", "现代迷宫"],
}

# 题材无关轴：整条轴都可用。这些词换个题材照样成立。
NEUTRAL_AXES = [
    "conflict_source",        # 冲突来源——直接对着「非常之无聊，没有任何冲突」
    "growth_mode",            # 成长与爽感结构
    "information_structure",  # 信息与叙事结构
    "relationship",           # 关系结构
    "pacing",                 # 节奏与篇章组织
]

# 题材相关轴：只保留语料里和本世界题材共现过的标签。
GENRE_AXES = ["story_engine", "cn_web_trope", "jp_web_trope", "manga_form"]

# 题材相关轴少于这么多标签就整轴丢弃。
#
# 取 3 不是 4：门槛提到 2 之后，奇幻的 jp_web_trope 只剩「異世界転生／
# 異世界転移／人外转生」三个——而那恰恰是玩家点名想要的那种味道。
# 三个标签仍有三种变化，不构成趋同；两个就太少了。
MIN_GENRE_AXIS = 3

# 一个标签要和本世界题材共现几次才算数。
#
# 门槛 1 太松：语料薄，共现一次基本是噪声。实测「都市人间」（明确无超自然）
# 在门槛 1 下抽到了「故事发动机=跨世界论坛」，武侠抽到了「财富神豪」。
# 门槛 2 把这些筛掉，同时保住奇幻的異世界転生/転移这类真正的题材特征。
MIN_TAG_EVIDENCE = 2

# 现实向世界：世界包明写「无超自然，纯写实」，硬约束比统计证据优先。
#
# 这些世界的证据门槛提到 3（还剩「迷宫攻略」这类擦边的会在门槛 2 通过），
# 并且整个不挂网文母题轴——那几条轴的词表本身大多带幻想设定。
REALIST_WORLDS = {"history", "modernlife"}
REALIST_TAG_EVIDENCE = 3
REALIST_SKIP_AXES = {"cn_web_trope", "jp_web_trope", "manga_form"}


def load_ontology() -> dict[str, list[str]]:
    with open(os.path.join(RESEARCH, "tag_ontology.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    return {c["id"]: list(c["tags"]) for c in data["categories"]}


def load_crosswalk() -> dict[str, list[str]]:
    with open(os.path.join(RESEARCH, "research_db.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    cw: dict[str, list[str]] = {}
    for entry in data.get("tag_crosswalk") or []:
        raw = entry.get("raw_tag")
        canon = entry.get("canonical_tags") or []
        if raw and canon:
            cw.setdefault(raw, []).extend(canon)
    return cw


def load_works() -> list[dict]:
    works: list[dict] = []
    for path in sorted(glob.glob(os.path.join(RESEARCH, "*works*.json"))):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            works += [w for w in data if isinstance(w, dict) and w.get("tags")]
    return works


def canonical_tags(work: dict, cw: dict[str, list[str]]) -> set[str]:
    out: set[str] = set()
    for raw in work.get("tags") or []:
        out.update(cw.get(raw, [raw]))
    return out


def main() -> int:
    onto = load_ontology()
    cw = load_crosswalk()
    works = load_works()
    frames_all = set(onto["world_frame"])

    # 锚点拼错会静默产出空池子，必须先校验。
    bad = {w: [f for f in fr if f not in frames_all] for w, fr in WORLD_FRAMES.items()}
    bad = {w: f for w, f in bad.items() if f}
    if bad:
        print("锚点不在本体 world_frame 里：", json.dumps(bad, ensure_ascii=False))
        return 1

    corpus = [canonical_tags(w, cw) for w in works]
    pools: dict[str, dict] = {}
    for wid, frames in WORLD_FRAMES.items():
        fs = set(frames)
        hits = [tags for tags in corpus if tags & fs]
        seen = collections.Counter()
        for tags in hits:
            seen.update(tags)

        realist = wid in REALIST_WORLDS
        need = REALIST_TAG_EVIDENCE if realist else MIN_TAG_EVIDENCE

        axes: dict[str, list[str]] = {}
        for axis in NEUTRAL_AXES:
            axes[axis] = list(onto[axis])
        for axis in GENRE_AXES:
            if realist and axis in REALIST_SKIP_AXES:
                continue
            picked = [t for t in onto[axis] if seen[t] >= need]
            if len(picked) >= MIN_GENRE_AXIS:
                axes[axis] = picked

        pools[wid] = {"frames": frames, "works_matched": len(hits),
                      "evidence_threshold": need, "realist": realist, "axes": axes}

    payload = {
        "generated_by": "tools/build_tag_pools.py",
        "ontology_version": json.load(
            open(os.path.join(RESEARCH, "tag_ontology.json"), encoding="utf-8")
        ).get("version"),
        "corpus_works": len(works),
        "neutral_axes": NEUTRAL_AXES,
        "genre_axes": GENRE_AXES,
        "worlds": pools,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=True)

    for wid, p in pools.items():
        axes = p["axes"]
        print("%-11s 命中%3d部 ｜ 轴%d 条 ｜ 可抽标签 %3d 个 ｜ 题材轴: %s" % (
            wid, p["works_matched"], len(axes),
            sum(len(v) for v in axes.values()),
            "、".join(f"{a}({len(axes[a])})" for a in GENRE_AXES if a in axes) or "无",
        ))
    print("\n写入", os.path.relpath(OUT, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
