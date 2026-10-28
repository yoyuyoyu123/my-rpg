#!/usr/bin/env python3
"""给导出的对局记录打质量分。

    backend/.venv/Scripts/python.exe tools/score_session.py 监控导出.json [--world fantasy]
    backend/.venv/Scripts/python.exe tools/score_session.py --dir ~/Downloads --validate

--validate 会跑一份「玩家已经骂过什么」的对照表：指标只有能把那几局标出来
才算可信，否则就是自说自话。对照表在 SESSION_TRUTH 里，取自玩家原话。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

# Windows 控制台默认 GBK，勾叉号会直接抛 UnicodeEncodeError。
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.services.quality_metrics import (  # noqa: E402
    compare_branch_sessions, score_session, verdicts,
)

# 人工标注的真值：玩家对每一局的原话，以及该局的世界。
# 指标要能在这些局上触发对应的判定。
SESSION_TRUTH = {
    "2026-08-22T15-24": ("wuxia", "推进依然慢得要死；有太多篇幅画在描述传送过程",
                         ["穿越"]),
    "2026-08-23T05-57": ("wuxia", "依然不穿越", ["穿越"]),
    "2026-08-23T07-00": ("wuxia", "终于能穿越了，但还是隔了一回合", []),
    "2026-08-23T13-11": ("wuxia", "穿越还是慢，戴个 VR 头显还在虚空里走半天", ["穿越"]),
    "2026-08-23T14-37": ("wuxia", "非常之无聊，没有任何冲突", ["走马观花"]),
    "2026-08-23T14-58": ("fantasy", "命名非常中式的榆树村；没显示出什么剑与魔法",
                         ["中式地名", "世界没立起来"]),
}


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def report(path: str, world: str) -> dict:
    m = score_session(load(path), world)
    v = verdicts(m)
    print(f"── {os.path.basename(path)}  [{world or '?'}]")
    print(f"   回合 {m['turns']} ｜ 幕 {m['scenes']} ｜ 平均每幕 {m['scene_span_avg']} 回合"
          f"（最长 {m['scene_span_max']}）｜ 正文均长 {m['narrative_chars_avg']}")
    print(f"   无冲突幕 {m['scenes_without_conflict']}/{m['scenes']}"
          f"，最长连续 {m['quiet_streak_max']}")
    if m["is_migration"]:
        print(f"   穿越落地回合 {m['crossing_turn']} ｜ 程序接管 {m['forced_takeovers']} 次")
    if m["flavor_hit_rate"] is not None:
        print(f"   题材特征命中 {m['flavor_hit_rate']:.0%}：{'、'.join(m['flavor_hits'][:8]) or '无'}")
    if m["cn_place_names_in_western_world"]:
        print(f"   中式地名：{'、'.join(m['cn_place_names_in_western_world'][:6])}")
    print(f"   详略分布 {m['narration_mix']}")
    if m.get("option_complete_rate") is not None:
        print(f"   选项完整度 {m['option_complete_rate']:.0%}，缺失回合 {m['option_missing_turns']}，数量序列 {m['option_counts']}")
    if m.get("mystery_evasion_rate") is not None:
        print(f"   谜语人回避信号 {m['mystery_evasion_rate']:.0%}（{m['mystery_evasion_turns']}/{m['turns']} 回合）")
    if m.get("causal_bridge_missing_rate") is not None:
        print(f"   因果桥缺失 {m['causal_bridge_missing_rate']:.0%}，重复场景目的 {m['repeated_purpose_turns']} 次")
    if m.get("memory_trace_coverage") is not None:
        print(f"   记忆召回解释覆盖 {m['memory_trace_coverage']:.0%}（{m['memory_trace_included'] if 'memory_trace_included' in m else '?'} 条有理由）")
    for line in v:
        print(f"   ✗ {line}")
    if not v:
        print("   ✓ 没有已知问题被触发")
    print()
    return {"path": path, "world": world, "metrics": m, "verdicts": v}


def validate(folder: str) -> int:
    """指标能不能把玩家骂过的局标出来。"""
    files = sorted(glob.glob(os.path.join(os.path.expanduser(folder), "myrpg_agent_monitor_*.json")))
    ok = miss = 0
    print("== 对照玩家原话验证指标 ==\n")
    for key, (world, quote, expect) in SESSION_TRUTH.items():
        hit = [f for f in files if key in os.path.basename(f)]
        if not hit:
            print(f"?? {key} 找不到导出文件，跳过")
            continue
        m = score_session(load(hit[0]), world)
        v = verdicts(m)
        joined = " ".join(v)
        missing = [e for e in expect if e not in joined]
        mark = "✓" if not missing else "✗"
        if missing:
            miss += 1
        else:
            ok += 1
        print(f"{mark} {key} [{world}]  玩家：{quote}")
        print(f"    指标判定：{('；'.join(v)) or '（无）'}")
        if missing:
            print(f"    !! 漏报：{'、'.join(missing)}")
        print()
    print(f"验证结果：{ok} 命中 / {miss} 漏报")
    return 0 if miss == 0 else 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("files", nargs="*", help="监控导出 JSON")
    p.add_argument("--compare", nargs=2, metavar=("LEFT", "RIGHT"),
                   help="比较同一初始局面的两条分支")
    p.add_argument("--world", default="", help="世界 id，导出里没有时手动指定")
    p.add_argument("--dir", help="批量扫描目录")
    p.add_argument("--validate", action="store_true", help="对照玩家原话验证指标")
    a = p.parse_args()

    if a.validate:
        return validate(a.dir or "~/Downloads")
    if a.compare:
        left_path, right_path = a.compare
        result = compare_branch_sessions(load(left_path), load(right_path), a.world)
        print("== 玩家分支比较 ==")
        print(f"共同回合：{result['shared_turns']}；分支输入回合：{result['different_input_turns']}")
        print(f"正文差异：{result['narrative_divergent_turns']}；选项差异：{result['option_divergent_turns']}")
        print(f"状态候选差异：{result['state_divergent_turns']}；首次差异：{result['first_divergence_turn']}")
        if result["verdicts"]:
            for line in result["verdicts"]:
                print(f"   ✗ {line}")
        else:
            print("   ✓ 玩家输入产生了可检测的分支影响")
        return 0
    targets = list(a.files)
    if a.dir:
        targets += sorted(glob.glob(os.path.join(os.path.expanduser(a.dir),
                                                 "myrpg_agent_monitor_*.json")))
    if not targets:
        p.error("给一个导出文件，或用 --dir")
    for path in targets:
        report(path, a.world)
    return 0


if __name__ == "__main__":
    sys.exit(main())
