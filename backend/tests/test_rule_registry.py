"""规则注册表：一个决策只能有一个权威。

为什么有这组测试
----------------
把 18 条功能提交按 bug 性质分类，**10 条是「两个机制互相矛盾」，8 条是
「某个部件写错了」——56% 的 bug 不在部件里，在部件之间**。

清点出来的账：提示词规则 138 条，10 个决策域，**没有一个是单方管辖的**。
「强度与冲突」被四方同时管，「本幕何时停」15 条规则来自 9 个规则组。
这不是理论风险——purpose 和 stop_points 打架、强制令被每回合指令吃掉、
迁移阶段被两条矛盾指令锁死，都是这些格子变成的真实 bug。

约束数量线性增长，两两冲突面平方增长。而过去每一轮的动作都是「加一条
保证」，从来没有减过。

这组测试做的事
--------------
59 条越权规则今天改不完。所以先**上棘轮**：把当前状态冻结成基线，
任何一方在任何决策上多写一条自作判断的规则，测试就失败。

方向是单向的——减少了就重新冻结，把成果锁住；增加了必须先回答
「它和已有那条谁说了算」。这正好打在那 56% 上。

「越权」的定义
--------------
非权威方**自己下判断**才算。只是转述权威结论的不算——写手被告知
「本幕详略看场景卡」是合规的传达，写手自己写一套「什么时候该略写」
的判断才是争夺。判据见 tools/rule_inventory.py 的 DEFERENCE。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from rule_inventory import (  # noqa: E402
    AUTHORITY, DECISIONS, collect, registry_report,
)

BASELINE = ROOT / "research" / "regression" / "rule_baseline.json"


@pytest.fixture(scope="module")
def report():
    rules, _ = collect()
    return {r["decision"]: r for r in registry_report(rules)}


@pytest.fixture(scope="module")
def baseline():
    with open(BASELINE, encoding="utf-8") as fh:
        return json.load(fh)


def test_extraction_still_works(report) -> None:
    """
    规则是从源码正文里抽的。哪天常量改名或格式变了，抽取会静默地变成 0 条，
    而所有「没有越权」的断言都会假装通过——先在这里挡住。
    """
    rules, checks = collect()
    assert len(rules) > 100, f"只抽到 {len(rules)} 条规则，抽取器多半坏了"
    assert len(checks) > 10
    assert len(report) == len(AUTHORITY)


def test_every_decision_has_exactly_one_authority() -> None:
    """注册表本身要自洽：每个决策域都得指定权威，不能漏。"""
    assert set(AUTHORITY) == set(DECISIONS), "决策域和权威表对不上"
    for decision, owner in AUTHORITY.items():
        assert owner, f"{decision} 没有指定权威"


def test_intrusions_never_grow(report, baseline) -> None:
    """
    棘轮：任何一方在任何决策上多写一条自作判断的规则，这里就失败。

    失败不代表那条规则是错的，代表**它和已有的那条得先说清楚谁说了算**。
    我们每一次「两个机制打架」的事故，都是从这一步没人拦住开始的。
    """
    grown = []
    for decision, before in baseline.items():
        now = report[decision]["intruders"]
        for who, n in now.items():
            was = before.get(who, 0)
            if n > was:
                grown.append(f"【{decision}】{who} 越权规则 {was} → {n}")
    assert not grown, (
        "有人在已经很拥挤的决策上又加了一条：\n  " + "\n  ".join(grown)
        + "\n\n先回答：这条和该决策已有的规则，谁说了算？"
        "\n若确实是必要的新权威，改 tools/rule_inventory.py 的 AUTHORITY；"
        "\n若是减少后重新冻结，跑 tools/rule_inventory.py --baseline "
        "research/regression/rule_baseline.json"
    )


def test_baseline_is_not_stale(report, baseline) -> None:
    """
    减少了就该重新冻结，否则棘轮会一直停在旧刻度上，白白放掉已经拿到的成果。

    这条失败是好消息。
    """
    shrunk = []
    for decision, before in baseline.items():
        now = report[decision]["intruders"]
        for who, was in before.items():
            n = now.get(who, 0)
            if n < was:
                shrunk.append(f"【{decision}】{who} {was} → {n}")
    assert not shrunk, (
        "越权规则减少了，请重新冻结基线把成果锁住：\n  " + "\n  ".join(shrunk)
        + "\n\n  tools/rule_inventory.py --baseline "
        "research/regression/rule_baseline.json"
    )


def test_the_worst_offenders_are_named(report) -> None:
    """
    把当前最拥挤的三个决策写进测试，是为了让它们一直可见。

    这三个不是随便挑的——每一个都已经变成过真实 bug：
      迁移阶段推进：两条矛盾指令锁死，迁移只在模型违抗指令时才前进
      本幕何时停：  停止点设在 purpose 兑现之前，每一幕都白写
      状态怎么改：  程序、写手、审计三方各有一套说法
    """
    worst = sorted(report.values(), key=lambda r: -r["intruder_total"])[:3]
    names = {r["decision"] for r in worst}
    assert "迁移阶段推进" in names or "NPC 知道什么" in names
    for r in worst:
        assert r["intruder_total"] > 0


def test_program_owned_decisions_have_no_prompt_authority(report) -> None:
    """
    权威标成「程序」的决策，提示词里不该有任何一方自作判断——那件事由代码
    保证，提示词只负责转述。

    现在三个「程序」决策全部有越权（迁移阶段推进 12 条、状态怎么改 8 条、
    专名怎么起 4 条），所以这里只记录现状不做硬断言；清干净之后改成断言 0。
    """
    program_owned = [d for d, o in AUTHORITY.items() if o == "程序"]
    assert program_owned, "至少该有一个决策由程序说了算"
    total = sum(report[d]["intruder_total"] for d in program_owned)
    # 现状快照。清理时这个数字只能往下走。
    assert total <= 24, f"程序权威的决策上，提示词越权已涨到 {total} 条"
