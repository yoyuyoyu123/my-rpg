#!/usr/bin/env python3
"""规则清点：这个引擎到底有多少条规则，各自管什么，谁和谁管同一件事。

    backend/.venv/Scripts/python.exe tools/rule_inventory.py
    backend/.venv/Scripts/python.exe tools/rule_inventory.py --overlap
    backend/.venv/Scripts/python.exe tools/rule_inventory.py --json out.json

为什么要程序抽取而不是手写清单
------------------------------
手写的清单三天就过时。这个脚本直接从源码里抽，跑一次就是当下的真实状态。

为什么要清点
------------
把 18 条功能提交按 bug 性质分类，**56% 是「两个机制互相矛盾」而不是
「某个部件写错了」**——迁移阶段被两条指令锁死、停止点和 purpose 打架、
强制令被每回合指令吃掉、详略判据和阶段判据冲突……

这是过度约束系统的签名：约束数量线性增长，两两冲突面平方增长。
而过去每一轮的动作都是「加一条保证」，**从来没有减过**。

所以第一步是把账摊开：一共多少条，分别管哪个决策，哪些管同一个决策。
管同一个决策的两条规则就是下一个冲突的候选。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")

# 规则文本所在的位置：(文件, 常量名, 收件人, 这批规则的用途)
#
# 「收件人」是关键维度——同一句话发给规划器和发给写手是两回事，
# 而我们踩过的坑里有好几个正是「两个收件人收到相反的指示」。
SOURCES = [
    ("app/domain/rules.py", "CORE_RULES", "写手", "核心叙事规则"),
    ("app/domain/rules.py", "OPTION_RULES", "写手", "行动选项格式"),
    ("app/domain/rules.py", "AGENCY_RULES", "写手", "玩家主权"),
    ("app/domain/rules.py", "ANTI_MYSTERY", "写手", "反神秘化"),
    ("app/domain/rules.py", "NPC_KNOWLEDGE_RULES", "写手", "NPC 认知边界"),
    ("app/domain/rules.py", "IDENTITY_FREEDOM", "写手", "身份自由"),
    ("app/domain/rules.py", "ISEKAI_MODERN", "写手", "穿越世界设定"),
    ("app/domain/rules.py", "GAMEWORLD_VARIANTS", "写手", "游戏化世界"),
    ("app/domain/rules.py", "FIRST_CHAPTER", "写手", "开局"),
    ("app/services/prompt_builder.py", "STATE_PROTOCOL", "写手", "状态申报协议"),
    ("app/services/prompt_builder.py", "AGENT_WRITER_RULES", "写手", "场景写手契约"),
    ("app/services/prompt_builder.py", "SUMMARY_MODE_RULES", "写手", "略写模式"),
    ("app/services/prompt_builder.py", "ELLIPSIS_MODE_RULES", "写手", "省略模式"),
    ("app/services/director.py", "_AUTHORITY_RULES", "GM 裁定", "裁定权限"),
    ("app/services/director.py", "_BEAT_RULES", "GM 裁定", "节拍"),
    ("app/services/director.py", "_CHECK_RULES", "GM 裁定", "检定"),
    ("app/services/state_audit.py", "AUDIT_RULES", "状态审计", "状态审计"),
    ("app/services/naming.py", "NAMING_INSTRUCTION", "规划器", "新专名产生方式"),
]

# 规划器的硬规则不是一个常量，是嵌在提示词模板里的编号列表。
PLANNER_FILE = "app/services/story_planner.py"

# 这条规则管哪个决策。一条规则可以命中多个。
#
# 决策域是按我们**实际踩过的冲突**划分的，不是凭空分类：
# 每一个域都对应至少一次「两条规则同时管它」的事故。
DECISIONS = {
    "本幕何时停": ["停下", "停在", "停止点", "决策边界", "交还", "收场"],
    "本幕写多长": ["略写", "详写", "省略", "篇幅", "压缩", "逐步展开", "一两段", "叙事密度"],
    "谁决定玩家的行动": ["替玩家", "玩家主权", "越权", "不得替", "自主"],
    "能不能引入新事件": ["新开", "凭空", "强塞", "causal_bridge", "铺垫", "没有铺垫", "新增"],
    "强度与冲突": ["压力", "pressure", "冲突", "危险", "代价", "赌注", "紧张"],
    "迁移阶段推进": ["迁移", "穿越", "premise_phase", "阶段", "落地", "阈限"],
    "专名怎么起": ["命名", "地名", "人名", "专名", "译名"],
    "NPC 知道什么": ["NPC", "知情", "认知", "不知道"],
    "状态怎么改": ["STATE", "attr_delta", "状态栏", "申报", "结算"],
    "行动选项": ["选项", "行动参考", "2-4"],
}


def read(path: str) -> str:
    with open(os.path.join(BACKEND, path), encoding="utf-8") as fh:
        return fh.read()


def extract_constant(src: str, name: str) -> str:
    """把 NAME = ( "..." "..." ) 这种拼接常量的内容取出来。"""
    m = re.search(rf"^{re.escape(name)}\s*=\s*\(", src, re.M)
    if not m:
        return ""
    i, depth, out = m.end() - 1, 0, []
    while i < len(src):
        ch = src[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                break
        out.append(ch)
        i += 1
    body = "".join(out)
    # 只取字符串字面量，丢掉代码
    parts = re.findall(r"['\"]([^'\"]*)['\"]", body)
    return "".join(parts)


def split_items(text: str) -> list[str]:
    """把一段规则正文切成一条条。优先按编号切，没有编号就按句号。"""
    text = text.replace("\\n", "\n")
    numbered = re.split(r"(?m)^(?=\s*\d+[a-z]?\.\s)", text)
    items = [s.strip() for s in numbered if s.strip()]
    if len(items) > 1:
        return items
    return [s.strip() for s in re.split(r"(?<=。)\s*", text) if len(s.strip()) > 8]


def planner_rules(src: str) -> list[str]:
    """规划器硬规则：提示词模板里的编号列表。"""
    m = re.search(r"硬规则：\n([\s\S]*?)\n\n输出结构", src)
    if not m:
        return []
    return [s.strip() for s in re.split(r"(?m)^(?=\d+[a-z]?\.\s)", m.group(1)) if s.strip()]


def classify(text: str) -> list[str]:
    return [name for name, keys in DECISIONS.items() if any(k in text for k in keys)]


def program_checks(src: str) -> list[str]:
    """程序侧的校验点——它们和提示词规则管的是同一批决策。"""
    out = []
    for m in re.finditer(r'warnings\.append\(\s*\n?\s*f?["\']([^"\']{4,60})', src):
        out.append(m.group(1))
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--overlap", action="store_true", help="只看哪些决策被多方共管")
    p.add_argument("--json", help="导出结构化结果")
    a = p.parse_args()

    rules: list[dict] = []
    for path, const, who, purpose in SOURCES:
        body = extract_constant(read(path), const)
        if not body:
            print(f"!! 取不到 {const}（{path}）", file=sys.stderr)
            continue
        for item in split_items(body):
            rules.append({"source": f"{const}", "file": path, "audience": who,
                          "group": purpose, "text": item,
                          "decisions": classify(item)})

    sp = read(PLANNER_FILE)
    for item in planner_rules(sp):
        rules.append({"source": "规划器硬规则", "file": PLANNER_FILE, "audience": "规划器",
                      "group": "剧情规划", "text": item, "decisions": classify(item)})

    checks = program_checks(sp)

    if not a.overlap:
        print("=" * 62)
        print("按收件人")
        print("=" * 62)
        by_who: dict[str, list[dict]] = {}
        for r in rules:
            by_who.setdefault(r["audience"], []).append(r)
        for who, items in sorted(by_who.items(), key=lambda kv: -len(kv[1])):
            groups: dict[str, int] = {}
            for r in items:
                groups[r["group"]] = groups.get(r["group"], 0) + 1
            print(f"\n{who}：{len(items)} 条")
            for g, n in sorted(groups.items(), key=lambda kv: -kv[1]):
                print(f"    {g:<16} {n:>3} 条")
        print(f"\n程序侧校验点：{len(checks)} 处（story_planner）")
        print(f"\n总计：提示词规则 {len(rules)} 条 + 程序校验 {len(checks)} 处")

    print()
    print("=" * 62)
    print("按决策域——**一个决策被几方共管，就是几方冲突的候选**")
    print("=" * 62)
    for name in DECISIONS:
        hits = [r for r in rules if name in r["decisions"]]
        if not hits:
            continue
        who = sorted({r["audience"] for r in hits})
        src = sorted({r["source"] for r in hits})
        flag = "  ⚠ 多方共管" if len(src) >= 3 else ""
        print(f"\n【{name}】{len(hits)} 条 ｜ 收件人 {'/'.join(who)}{flag}")
        for s in src:
            n = len([r for r in hits if r["source"] == s])
            print(f"    {s:<24} {n:>2} 条")

    unclassified = [r for r in rules if not r["decisions"]]
    print(f"\n未归类 {len(unclassified)} 条（多为格式、文风一类，不参与决策冲突）")

    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({"rules": rules, "program_checks": checks}, fh,
                      ensure_ascii=False, indent=1)
        print(f"\n已导出 {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
