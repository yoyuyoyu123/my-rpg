#!/usr/bin/env python3
"""解码参数 A/B：同一批提示词，只改一个参数，比较重复度。

    backend/.venv/Scripts/python.exe tools/ab_decoding.py \
        --session research/regression/sessions/slow_transit_wuxia.json \
        --provider siliconflow --model Qwen/Qwen2.5-14B-Instruct \
        --arm baseline --arm freq=0.6 --turns 8

为什么这么设计
--------------
要回答的问题很窄：**frequency_penalty 能不能减少「每回合换个感官细节重复
同一件事」**。要回答它，必须只让这一个变量变。

所以不重跑整局游戏——那样规划器会产出不同的场景卡，写手的输入就变了，
比出来的差异分不清是参数带来的还是剧情走向带来的。这里直接**重放存档里
录下的写手提示词**：场景卡、玩家输入、历史全部固定，只有采样参数不同。

DeepSeek 那边 frequency_penalty 已弃用（官方明写传了不生效），所以这个
实验必须在支持它的 provider 上跑，默认硅基流动。

会真的花钱：轮数 × 分支数 次调用。默认 8 回合 × 2 分支 = 16 次。
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

BACKEND = "http://127.0.0.1:8000"


def bigrams(text: str) -> set[str]:
    s = re.sub(r"[\s，。、；：,.;:！？「」【】()（）]", "", text or "")
    return {s[i:i + 2] for i in range(len(s) - 1)}


def overlap(a: str, b: str) -> float:
    ga, gb = bigrams(a), bigrams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def repetition(bodies: list[str]) -> dict:
    """相邻回合之间的重复度。

    这正是玩家描述的那个毛病的形状：「每回合只是换个感官细节重复同一件事」
    ——相邻两段会高度重合。用字符二元组 Jaccard，和 story_planner 里判断
    purpose 重复用的是同一把尺，读数可以互相参照。
    """
    pairs = [overlap(bodies[i], bodies[i + 1]) for i in range(len(bodies) - 1)]
    if not pairs:
        return {"adjacent_avg": 0.0, "adjacent_max": 0.0, "chars_avg": 0}
    return {
        "adjacent_avg": round(sum(pairs) / len(pairs), 4),
        "adjacent_max": round(max(pairs), 4),
        "chars_avg": round(sum(len(b) for b in bodies) / len(bodies)),
    }


def parse_arm(spec: str) -> tuple[str, dict]:
    """`baseline` 或 `freq=0.6,top_p=0.9` → (名字, 采样参数)。"""
    if spec.strip().lower() in ("baseline", "base", "none"):
        return "baseline", {}
    alias = {"freq": "frequency_penalty", "fp": "frequency_penalty",
             "topp": "top_p", "topk": "top_k", "minp": "min_p"}
    out: dict[str, float] = {}
    for part in spec.split(","):
        k, _, v = part.partition("=")
        k = alias.get(k.strip(), k.strip())
        out[k] = float(v) if "." in v else int(v)
    return spec, out


def writer_prompts(session: dict, limit: int) -> list[dict]:
    """从存档里取出写手每回合收到的完整输入。"""
    runs = [r for r in session.get("runs") or [] if r.get("agent") == "narrative"]
    runs.sort(key=lambda r: r.get("turn") if isinstance(r.get("turn"), int) else 0)
    return runs[:limit]


def call(provider: str, model: str, messages: list[dict], sampling: dict,
         max_tokens: int) -> str:
    body = {"messages": messages, "provider": provider, "model": model,
            "max_tokens": max_tokens, "stream": False, **sampling}
    req = urllib.request.Request(
        BACKEND + "/api/chat", method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps(body).encode(),
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read()).get("content") or ""


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--session", required=True, help="裁剪版对局导出")
    p.add_argument("--provider", default="siliconflow")
    p.add_argument("--model", default="")
    p.add_argument("--arm", action="append", default=[],
                   help="baseline 或 freq=0.6[,top_p=0.9]；可给多次")
    p.add_argument("--turns", type=int, default=8)
    p.add_argument("--max-tokens", type=int, default=1200)
    p.add_argument("--out", help="把两边的正文也存下来，供人工过目")
    a = p.parse_args()

    arms = [parse_arm(s) for s in (a.arm or ["baseline", "freq=0.6"])]
    with open(a.session, encoding="utf-8") as fh:
        session = json.load(fh)
    runs = writer_prompts(session, a.turns)
    if not runs:
        print("这份存档里没有写手记录", file=sys.stderr)
        return 2

    print(f"重放 {len(runs)} 个回合的写手提示词 ｜ provider={a.provider} "
          f"model={a.model or '(默认)'} ｜ 分支 {len(arms)} 个")
    print("场景卡与玩家输入全部固定，唯一变量是采样参数\n")

    results = {}
    for name, sampling in arms:
        bodies = []
        for r in runs:
            prompt = r.get("input") or ""
            if not prompt.strip():
                continue
            # 存档里 input 是拼好的整段提示词，原样当 system 发回去
            text = call(a.provider, a.model, [{"role": "system", "content": prompt}],
                        sampling, a.max_tokens)
            bodies.append(_strip_protocol(text))
            print(".", end="", flush=True)
        results[name] = {"metrics": repetition(bodies), "bodies": bodies}
        print(f"  {name} 完成")

    print()
    print(f"{'分支':<22}{'相邻重复(均)':>14}{'相邻重复(峰)':>14}{'正文均长':>10}")
    for name, r in results.items():
        m = r["metrics"]
        print(f"{name:<22}{m['adjacent_avg']:>14.4f}{m['adjacent_max']:>14.4f}"
              f"{m['chars_avg']:>10}")

    names = list(results)
    if len(names) >= 2:
        base = results[names[0]]["metrics"]["adjacent_avg"]
        for other in names[1:]:
            cur = results[other]["metrics"]["adjacent_avg"]
            delta = (cur - base) / base * 100 if base else 0.0
            print(f"\n{other} 相对 {names[0]}：相邻重复度 {delta:+.1f}%")
    print("\n⚠️ 单次运行、样本很小，只能当线索。方向一致才值得改默认值。")

    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(results, fh, ensure_ascii=False, indent=1)
        print(f"正文已写入 {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
