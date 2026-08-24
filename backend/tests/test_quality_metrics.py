"""叙事质量度量。

这组测试和别处不同：它锁的不是「代码有没有按我写的那样跑」，而是
**指标能不能把玩家已经骂过的那几局标出来**。指标要是标不出已知的坏局，
它就是自说自话，用它去判断新改动只会自欺。

回归语料在 research/regression/sessions/，是三局真实对局的裁剪版
（只留指标用到的字段），连同玩家原话一起冻结在这里。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.quality_metrics import (  # noqa: E402
    QUIET_STREAK_BAD, TRANSIT_SLOW_TURNS, score_session, verdicts,
)

SESSIONS = ROOT.parent / "research" / "regression" / "sessions"


def load(name: str) -> dict:
    with open(SESSIONS / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)


# ── 真实对局：指标必须复现玩家的判断 ────────────────────────────

def test_flags_the_travelogue_session() -> None:
    """玩家原话：非常之无聊，没有任何冲突。"""
    m = score_session(load("quiet_travelogue_wuxia"), "wuxia")
    assert m["quiet_streak_max"] >= QUIET_STREAK_BAD
    assert any("走马观花" in v for v in verdicts(m))


def test_flags_the_slow_transit_session() -> None:
    """玩家原话：穿越还是慢，戴个 VR 头显还在虚空里走半天。

    注意测的是**转移本身**占了几个回合，不是从开局到落地的总长——那一局
    第 7 回合就落地了，总长并不长，慢的是阈限之后那一段。
    """
    m = score_session(load("slow_transit_wuxia"), "wuxia")
    assert m["transit_turns"] is not None
    assert m["transit_turns"] > TRANSIT_SLOW_TURNS
    assert any("转移拖沓" in v for v in verdicts(m))


def test_flags_the_flat_world_session() -> None:
    """玩家原话：从头到尾没显示出什么剑与魔法。"""
    m = score_session(load("flat_world_fantasy"), "fantasy")
    assert m["flavor_hit_rate"] == 0.0
    assert any("世界没立起来" in v for v in verdicts(m))


@pytest.mark.xfail(reason="事实库滞后一到两个回合：榆树村只在最末回合出现，没进事实区", strict=True)
def test_flags_chinese_place_name_in_western_world() -> None:
    """
    玩家原话：明明是剑与魔法，命名却非常中式的榆树村。

    标成 xfail 而不是删掉：这是**已知且已定位**的局限，不是没想到的情况。
    之前用正则切正文试过，在真实文本上匹配出「半天到镇」「地址在城」
    「她榆树村」——中文没有词边界，词干必然切错。那版会给出正确结论但
    理由是错的，比漏报更危险，所以换成了事实库的结构化条目并接受滞后。
    """
    m = score_session(load("flat_world_fantasy"), "fantasy")
    assert m["cn_place_names_in_western_world"]


# ── 分段与边界 ──────────────────────────────────────────────────

def _monitor(scenes: list[dict], narratives: list[tuple[int, str]]) -> dict:
    runs = [{"agent": "planner", "turn": s.pop("_turn"),
             "output": json.dumps({"current_scene": s}, ensure_ascii=False)}
            for s in scenes]
    runs += [{"agent": "narrative", "turn": t, "output": text} for t, text in narratives]
    return {"runs": runs}


def test_flavor_is_scored_only_after_landing() -> None:
    """
    穿越局前期在原世界，本来就不该出现目标世界的特征。此前不分段落地算，
    结果五局武侠全部报「0%」——一个永远报警的指标等于没有指标。
    """
    mon = _monitor(
        [{"_turn": 0, "id": "a", "premise_phase": 0},
         {"_turn": 2, "id": "b", "premise_phase": 5}],
        [(0, "你在写字楼里加班"), (1, "雨还在下"),
         (2, "客栈的掌柜递来一碗茶，隔壁在谈镖局的买卖")],
    )
    m = score_session(mon, "wuxia")
    assert m["crossing_turn"] == 2
    assert m["flavor_scored_turns"] == 1        # 只算落地那一回合
    assert m["flavor_hit_rate"] > 0             # 客栈/掌柜/镖 都在
    assert not any("世界没立起来" in v for v in verdicts(m))


def test_flavor_is_not_scored_when_never_landed() -> None:
    """没到那个世界，就没法评判它像不像——报 None，不报 0%。"""
    mon = _monitor([{"_turn": 0, "id": "a", "premise_phase": 1}],
                   [(0, "你在写字楼里加班"), (1, "雨还在下")])
    m = score_session(mon, "wuxia")
    assert m["crossing_turn"] is None
    assert m["flavor_hit_rate"] is None
    assert not any("世界没立起来" in v for v in verdicts(m))


def test_short_migration_is_not_called_a_failure() -> None:
    """才玩了几回合还没穿越是正常的，不该报「从未发生」。"""
    mon = _monitor([{"_turn": 0, "id": "a", "premise_phase": 1}],
                   [(t, "日常") for t in range(3)])
    assert not any("从未发生" in v for v in verdicts(score_session(mon, "wuxia")))


def test_conflict_resets_the_quiet_streak() -> None:
    mon = _monitor(
        [{"_turn": 0, "id": "a"}, {"_turn": 1, "id": "b"},
         {"_turn": 2, "id": "c", "conflict": "客栈老板要押金，玩家不够"},
         {"_turn": 3, "id": "d"}],
        [(t, "正文") for t in range(4)],
    )
    m = score_session(mon, "wuxia")
    assert m["quiet_streak_max"] == 2
    assert m["scenes_without_conflict"] == 3


def test_non_migration_session_scores_all_turns() -> None:
    mon = _monitor([{"_turn": 0, "id": "a"}],
                   [(0, "你在便利店买了关东煮，手机弹出房租提醒")])
    m = score_session(mon, "modernlife")
    assert m["is_migration"] is False
    assert m["flavor_scored_turns"] == 1
    assert m["flavor_hit_rate"] > 0


def test_empty_monitor_does_not_crash() -> None:
    m = score_session({"runs": []}, "wuxia")
    assert m["turns"] == 0 and verdicts(m) == []
