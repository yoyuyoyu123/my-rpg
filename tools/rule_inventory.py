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
    ("app/domain/rules.py", "STRUCTURED_WRITER_RULES", "写手", "结构化输出信封"),
]

# 不是规则、只是被当成常量的东西。列在这里表示「看见了，确认不用清点」，
# 而不是漏掉。
NOT_RULES = {"COMPRESSED_NARRATION"}


def untracked_rule_constants() -> list[tuple[str, str]]:
    """找出像规则文本、却没进 SOURCES 的常量。

    SOURCES 是手列的，新增的规则常量会**静默漏掉**——实测就漏了一次：
    别人加了 STRUCTURED_WRITER_RULES 之后，棘轮照样全绿，因为清点器根本
    没看见那条规则。一个有盲区的警报器等于没有警报器，所以这里反过来扫。
    """
    tracked = {c for _, c, _, _ in SOURCES} | NOT_RULES
    out: list[tuple[str, str]] = []
    for root, _dirs, files in os.walk(os.path.join(BACKEND, "app")):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(root, fn)
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
            for m in re.finditer(r"^(_?[A-Z][A-Z_]{3,})\s*=\s*\(", src, re.M):
                name = m.group(1)
                if name in tracked:
                    continue
                body = extract_constant(src, name)
                # 够长且含中文才像规则文本，排除元组、路径、枚举一类
                if len(body) > 120 and re.search(r"[一-龥]", body):
                    out.append((name, os.path.relpath(path, BACKEND)))
    return sorted(out)

# 规划器的硬规则不是一个常量，是嵌在提示词模板里的编号列表。
PLANNER_FILE = "app/services/story_planner.py"

# 这条规则管哪个决策。一条规则可以命中多个。
#
# 决策域是按我们**实际踩过的冲突**划分的，不是凭空分类：
# 每一个域都对应至少一次「两条规则同时管它」的事故。
# 每个决策域**应该**由谁说了算。
#
# 这是注册表的核心：一个决策只能有一个权威。其他方要么不提，要么明确写成
# 「以 X 为准」——而不是各写一套独立说法。我们踩过的坑全长一个样：两方
# 各自给出完整判断，模型跟了更近或更具体的那一条。
#
# 「程序」意味着这件事根本不该在提示词里争——由代码保证，提示词只是转述。
AUTHORITY = {
    "本幕何时停":       "规划器",   # 场景卡的 stop_points 说了算
    "本幕写多长":       "规划器",   # 场景卡的 narration
    "谁决定玩家的行动":  "写手",     # 主权是写作纪律，程序侧另有守卫兜底
    "能不能引入新事件":  "规划器",   # 只有它有全局因果视野
    "强度与冲突":       "规划器",   # pressure_budget 与 conflict 都在场景卡上
    "迁移阶段推进":     "程序",     # 迁移契约，模型只负责表达
    "专名怎么起":       "程序",     # 命名从候选里挑，见 services/naming.py
    "NPC 知道什么":     "状态审计", # NpcBelief 是权威事实
    "状态怎么改":       "程序",     # STATE 协议 + apply_patch
    "行动选项":         "写手",     # 只有它在写正文结尾
}

# 一条「非权威方」的规则如果只是转述权威的结论，那是合规的转述，不是争夺。
# 这些词是转述的标志。
DEFERENCE = ["场景卡", "以…为准", "以叙事为准", "程序", "权威", "服从",
             "按场景卡", "不得自行", "由程序", "已经给出", "见上", "优先"]

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


def is_deferential(text: str) -> bool:
    """这条规则是在转述权威的结论，还是在自己下判断。"""
    return any(k in text for k in DEFERENCE)


def collect() -> tuple[list[dict], list[str]]:
    """抽出全部规则。测试和 CLI 共用这一份，避免两处漂移。"""
    rules: list[dict] = []
    for path, const, who, purpose in SOURCES:
        body = extract_constant(read(path), const)
        if not body:
            continue
        for item in split_items(body):
            rules.append({"source": const, "file": path, "audience": who,
                          "group": purpose, "text": item,
                          "decisions": classify(item),
                          "deferential": is_deferential(item)})
    sp = read(PLANNER_FILE)
    for item in planner_rules(sp):
        rules.append({"source": "规划器硬规则", "file": PLANNER_FILE, "audience": "规划器",
                      "group": "剧情规划", "text": item, "decisions": classify(item),
                      "deferential": is_deferential(item)})
    return rules, program_checks(sp)


def contenders(rules: list[dict], decision: str) -> dict[str, int]:
    """在这个决策上**自己下判断**（而非转述）的各方，各有几条。

    转述不算争夺——写手被告知「本幕详略看场景卡」是合规的传达；
    写手自己写一套「什么时候该略写」的判断才是。
    """
    out: dict[str, int] = {}
    for r in rules:
        if decision in r["decisions"] and not r["deferential"]:
            out[r["audience"]] = out.get(r["audience"], 0) + 1
    return out


def registry_report(rules: list[dict]) -> list[dict]:
    rows = []
    for decision, owner in AUTHORITY.items():
        c = contenders(rules, decision)
        # 「程序」权威意味着提示词侧任何一方自作判断都是越权
        intruders = {k: v for k, v in c.items() if k != owner}
        rows.append({
            "decision": decision,
            "authority": owner,
            "authority_rules": c.get(owner, 0),
            "intruders": intruders,
            "intruder_total": sum(intruders.values()),
        })
    return rows


def program_checks(src: str) -> list[str]:
    """程序侧的校验点——它们和提示词规则管的是同一批决策。"""
    out = []
    for m in re.finditer(r'warnings\.append\(\s*\n?\s*f?["\']([^"\']{4,60})', src):
        out.append(m.group(1))
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--overlap", action="store_true", help="只看哪些决策被多方共管")
    p.add_argument("--registry", action="store_true",
                   help="注册表：每个决策的权威方，以及有谁在越权自作判断")
    p.add_argument("--baseline", help="把当前越权情况写成基线文件（棘轮用）")
    p.add_argument("--json", help="导出结构化结果")
    a = p.parse_args()

    rules, checks = collect()

    if a.baseline:
        data = {r["decision"]: r["intruders"] for r in registry_report(rules)}
        with open(a.baseline, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1, sort_keys=True)
        total = sum(sum(v.values()) for v in data.values())
        print(f"基线已写入 {a.baseline}（越权规则合计 {total} 条）")
        return 0

    if a.registry:
        rows = registry_report(rules)
        print("=" * 66)
        print("规则注册表——一个决策只能有一个权威")
        print("=" * 66)
        print("越权 = 非权威方**自己下判断**；只是转述权威结论的不算。\n")
        rows.sort(key=lambda r: -r["intruder_total"])
        for r in rows:
            mark = "✗" if r["intruder_total"] else "✓"
            print(f"{mark} 【{r['decision']}】权威={r['authority']}"
                  f"（{r['authority_rules']} 条）")
            if r["intruders"]:
                for who, n in sorted(r["intruders"].items(), key=lambda kv: -kv[1]):
                    print(f"      越权：{who} {n} 条")
        bad = sum(r["intruder_total"] for r in rows)
        clean = sum(1 for r in rows if not r["intruder_total"])
        print(f"\n{clean}/{len(rows)} 个决策已单一权威 ｜ 越权规则合计 {bad} 条")
        return 0

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
