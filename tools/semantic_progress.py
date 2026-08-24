#!/usr/bin/env python3
"""语义推进度：用嵌入测「这一回合到底往前走了没有」。

    backend/.venv/Scripts/python.exe tools/semantic_progress.py \
        --session research/regression/sessions/slow_transit_wuxia.json --calibrate

为什么需要它
------------
玩家抱怨的重复是**语义层面**的：「每回合换个感官细节重复同一件事」——
用词不同，事件相同。此前用字符二元组 Jaccard 量，已知的坏局（0.084-0.122）
和随便一次重放（0.088）落在同一区间，全都远低于「实质相同」的 0.45 阈值。
**那把尺在好坏之间没有区分度**，架在它上面的 A/B 结论一律无效。

另外试过一个免费信号——每回合新增了几条事实——被证伪：记忆抽取只跑在
24 个回合里的 12 个，「零新事实」分不清是「什么都没发生」还是「抽取器没跑」。

所以只剩嵌入。它比生成便宜约两个数量级，而且中文嵌入模型现成。

怎么校准（关键）
----------------
**标注不在「局」这一层，在「回合」这一层。**玩家说「传送过程写了 11 个回合」
「戴个 VR 头显还在虚空里走半天」，指的都是具体几个回合——同一局里既有坏回合
也有正常回合。所以不需要一整个「好局」当正例，局内对比就能校准。

判据先定死，再看结果，避免事后找解释：

    坏回合的相邻语义相似度，必须显著高于同一局其余回合。
    「显著」= 坏回合均值 - 其余均值 ≥ 0.05，且坏回合均值更高。

达不到就是这把尺也测不出来，如实记下，不要迁就。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.services.quality_metrics import _strip_protocol  # noqa: E402

EMBED_URL = "https://api.siliconflow.cn/v1/embeddings"
# bge-m3 而不是 bge-large-zh-v1.5：后者只有 512 token 上限，我们的正文
# 四百到八百字，直接 HTTP 400（code 20015 参数非法）。m3 是长上下文的。
DEFAULT_MODEL = "BAAI/bge-m3"

# 玩家逐回合的抱怨落在哪些回合上。
#
# slow_transit：阈限在第 4 回合，第 7 回合才落地——中间那几个回合就是
# 「虚空里走半天」。
# quiet_travelogue：落地后整段都是「抵达、观察、再选下一个地方」，
# 玩家原话「非常之无聊，没有任何冲突」。
COMPLAINT_TURNS = {
    "slow_transit_wuxia": ([5, 6, 7, 8], "戴个 VR 头显还在虚空里走半天"),
    "quiet_travelogue_wuxia": (list(range(13, 32)), "非常之无聊，没有任何冲突"),
}

# 事先定死的通过线。改这个数就等于迁就结果，改之前先问自己为什么。
MIN_SEPARATION = 0.05


def embed(texts: list[str], key: str, model: str) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), 16):
        body = {"model": model, "input": texts[i:i + 16]}
        req = urllib.request.Request(
            EMBED_URL, method="POST", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        out += [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]
    return out


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def read_key() -> str:
    env = os.path.join(ROOT, "backend", ".env")
    for line in open(env, encoding="utf-8"):
        m = re.match(r"\s*([A-Z_]*SILICON[A-Z_]*)\s*=\s*(.+)", line.strip())
        if m:
            return m.group(2).strip().strip("\"'")
    raise SystemExit("backend/.env 里没找到硅基流动的 key")


def load_turns(path: str) -> list[tuple[int, str]]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    runs = [r for r in data.get("runs") or [] if r.get("agent") == "narrative"]
    runs.sort(key=lambda r: r.get("turn") if isinstance(r.get("turn"), int) else 0)
    return [(r.get("turn") or 0, _strip_protocol(r.get("output") or "")) for r in runs]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--session", required=True)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--calibrate", action="store_true",
                   help="对照玩家的逐回合抱怨，检验这把尺有没有区分度")
    a = p.parse_args()

    turns = load_turns(a.session)
    if len(turns) < 3:
        print("回合太少", file=sys.stderr)
        return 2

    vecs = embed([t for _, t in turns], read_key(), a.model)
    sims = [(turns[i + 1][0], cosine(vecs[i], vecs[i + 1])) for i in range(len(vecs) - 1)]

    name = os.path.splitext(os.path.basename(a.session))[0]
    print(f"== {name} ｜ {a.model} ｜ {len(turns)} 回合 ==\n")
    for turn, s in sims:
        bar = "█" * int(s * 50)
        print(f"  t{turn:<3} {s:.4f} {bar}")

    if not a.calibrate:
        return 0

    marked, quote = COMPLAINT_TURNS.get(name, ([], ""))
    if not marked:
        print("\n这一局没有逐回合标注，跳过校准")
        return 0

    bad = [s for t, s in sims if t in marked]
    rest = [s for t, s in sims if t not in marked]
    if not bad or not rest:
        print("\n标注回合与其余回合无法分组，跳过")
        return 0

    mb, mr = sum(bad) / len(bad), sum(rest) / len(rest)
    gap = mb - mr
    ok = gap >= MIN_SEPARATION
    print(f"\n玩家标注（{quote}）落在回合 {marked[:6]}{'…' if len(marked) > 6 else ''}")
    print(f"  标注回合 相邻语义相似度 均值 {mb:.4f}（{len(bad)} 个）")
    print(f"  其余回合                 均值 {mr:.4f}（{len(rest)} 个）")
    print(f"  差值 {gap:+.4f}   通过线 ≥{MIN_SEPARATION}")
    print("\n" + ("✓ 这把尺有区分度，可以用来做 A/B"
                  if ok else
                  "✗ 这把尺同样测不出来——不要在它上面架结论"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
