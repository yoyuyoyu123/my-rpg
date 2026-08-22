import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402
from app.schemas.story import StoryPlanContext  # noqa: E402
from app.schemas.turn import TurnContext  # noqa: E402
from app.services.prompt_builder import build_system_prompt  # noqa: E402
from app.services.story_planner import (  # noqa: E402
    build_story_plan_prompt, parse_story_runtime, state_digest,
)


def sample_runtime(private_cause: str = "老板私下欠了税") -> dict:
    return {
        "version": 1,
        "revision": 1,
        "premise": "玩家刚到镇上，想找住处",
        "threads": [{
            "id": "work", "title": "临时工作", "kind": "职业",
            "public_goal": "在镇上赚到第一笔食宿费", "private_cause": private_cause,
            "why_now": "面包店今天缺人", "player_connection": "玩家正在找工作",
            "established_clues": ["门口贴有招工纸"], "open_questions": [],
            "beats": [{"id": "ask", "label": "询问工作", "purpose": "给出公开条件",
                       "prerequisites": [], "setup": ["招工纸"],
                       "activation_condition": "玩家主动询问", "status": "available"}],
            "status": "active",
        }],
        "current_scene": {
            "id": "bakery", "title": "面包店门口", "situation": "清晨，店门刚开",
            "purpose": "让玩家自主决定是否询问", "causal_bridge": "玩家沿主街寻找便宜住处时看见招工纸",
            "active_thread_ids": ["work"], "participant_intents": {"老板": "尽快找到半天帮工"},
            "available_information": ["工资和工时可以直接询问"],
            "causal_event_ids": ["evt_walk_main_street"],
            "affordances": ["询问工资", "继续找住处"],
            "allowed_developments": ["正常问价", "离开继续找住处"],
            "forbidden": ["突然出现神秘组织"],
            "soft_commitment_ids": ["com_find_lodging"],
            "pressure_budget": 1, "mystery_budget": 0,
            "stop_points": ["老板等待玩家开口"], "refresh_after_turn": 3,
            "premise_phase": None, "status": "active",
        },
        "last_planned_turn": 0, "plan_reason": "opening",
    }


def test_planner_prompt_demands_partial_order_and_causal_bridge() -> None:
    prompt = build_story_plan_prompt(StoryPlanContext(
        world_id="fantasy", story_dna="主角可能是任何种族；基调温馨日常",
        recent_messages=[{"role": "user", "content": "开始游戏"}],
    ))
    assert "部分有序剧情节点" in prompt
    assert "causal_bridge" in prompt
    assert "不能预定玩家会接受任务" in prompt
    assert "主角可能是任何种族" in prompt
    assert "西式奇幻世界" in prompt


def test_transmigration_plan_is_bound_to_program_phase() -> None:
    prompt = build_story_plan_prompt(StoryPlanContext(
        world_id="fantasy",
        turn=2,
        reason="premise",
        story_dna="穿越者；真实异界",
        premise_state={"kind": "transmigration", "phase": 2, "fast": True},
    ))
    assert "穿越规划专用约束" in prompt
    assert "current_scene.premise_phase 必须填写这个数值" in prompt
    assert "快速迁移路线" in prompt


def test_parser_clamps_planner_migration_jump() -> None:
    """
    规划器一次最多推进一级。1→5 是在赶进度，会被压回 2。

    （规则从「完全禁止上调」放宽到「最多一级」，是因为正则证据只认得
    「游戏弹窗」那一类路线的措辞：召唤路线第 0 回合就出现了明确征兆却
    一个都匹配不上，阶段在 0 停了九回合。详见 test_premise_stall.py。）
    """
    raw = sample_runtime()
    raw["current_scene"]["premise_phase"] = 5
    runtime, warnings = parse_story_runtime(
        json.dumps(raw, ensure_ascii=False), {}, 2, "premise",
        {"kind": "transmigration", "phase": 1},
    )
    assert runtime.current_scene.premise_phase == 2
    assert any("限制为只前进一级" in w for w in warnings)


def test_parser_accepts_fenced_json_and_clamps_growth() -> None:
    raw = sample_runtime()
    raw["current_scene"]["refresh_after_turn"] = 99
    raw["current_scene"]["available_information"] = ["同一条"] * 12
    raw["threads"] = raw["threads"] * 5
    runtime, warnings = parse_story_runtime(
        "```json\n" + json.dumps(raw, ensure_ascii=False) + "\n```",
        {"revision": 8}, 10, "horizon",
    )
    assert runtime.revision == 9
    assert runtime.current_scene.refresh_after_turn == 16
    assert runtime.current_scene.available_information == ["同一条"]
    assert runtime.current_scene.pressure_budget == 1
    assert runtime.current_scene.mystery_budget == 0
    assert len(runtime.threads) == 3
    assert warnings


def test_parser_rejects_missing_scene() -> None:
    with pytest.raises(ValueError, match="current_scene"):
        parse_story_runtime('{"threads":[]}', {}, 0, "opening")


def test_writer_sees_scene_but_not_private_cause() -> None:
    legacy = build_system_prompt(TurnContext(
        world_id="fantasy", pace="long", turns=2, game_state={"revealed": False},
        story_dna="温馨生活冒险", outline="旧式隐藏大纲",
        inspiration_tags=["转生异种", "退队流"],
    ))
    agent = build_system_prompt(TurnContext(
        world_id="fantasy", pace="long", turns=2, game_state={"revealed": False},
        story_dna="温馨生活冒险", outline="旧式隐藏大纲",
        inspiration_tags=["转生异种", "退队流"], story_runtime=sample_runtime(),
    ))
    assert "【场景写手契约】" in agent
    assert "【当前场景卡" in agent
    assert "面包店门口" in agent and "门口贴有招工纸" in agent
    assert "压力=1/4" in agent and "悬疑=0/4" in agent
    assert "突然出现神秘组织" in agent
    assert "老板私下欠了税" not in agent
    assert "旧式隐藏大纲" not in agent
    assert "【研究库灵感候选】" not in agent
    assert "【行动选项格式】" in agent
    assert "数字+空格+完整行动描述" in agent
    assert len(agent) < len(legacy)


def test_story_endpoints() -> None:
    client = TestClient(app)
    p = client.post("/api/story/plan/prompt", json={"world_id": "fantasy"})
    assert p.status_code == 200 and p.json()["max_tokens"] >= 1000
    r = client.post("/api/story/plan/result", json={
        "raw": json.dumps(sample_runtime(), ensure_ascii=False),
        "previous_runtime": {}, "premise_state": {}, "turn": 0, "reason": "opening",
    })
    assert r.status_code == 200
    assert r.json()["runtime"]["current_scene"]["id"] == "bakery"


# ── 规划器拿到的状态必须是精简过的 ──────────────────────────────

def _bloated_state() -> dict:
    """玩久了的真实规模：账本攒满 300 条，物品技能人物都不少。"""
    return {
        "version": 4, "revealed": True,
        "attrs": {"力量": 5, "身法": 3}, "res": {"体力": 80}, "caps": {"体力": 100},
        "talents": ["过目不忘"],
        "inv": [{"id": f"i{i}", "name": f"物品{i}", "quantity": 1, "category": "其他",
                 "equipped": False, "description": "描述" * 40, "consumable": False,
                 "tags": []} for i in range(15)],
        "skills": [{"id": f"s{i}", "name": f"技能{i}", "realm": "小成",
                    "description": "说明" * 40} for i in range(8)],
        "loadout": {"activeCoreId": None}, "skillCapacity": 20,
        # 账本排在 loc/npcs 前面，正是它把后面的字段挤出窗口的
        "ledger": [{"turn": i, "time": 1755000000000 + i, "type": "item",
                    "ref": f"物品{i}", "note": "增加", "delta": 1} for i in range(300)],
        "loc": "陈家渡渡口",
        "npcs": {"吴四娘": {"rel": "邻居", "att": 2, "note": "浆洗为生",
                            "knows": ["主角会拳脚"]},
                 "王掌柜": {"rel": "债主", "att": -1, "note": "催债",
                            "knows": ["主角欠钱"]}},
        "lastCheck": None,
    }


def test_planner_sees_location_and_npcs_even_with_full_ledger() -> None:
    """
    这条锁的是一个只在长局才发作的坑：
    整坨 game_state 序列化再硬截断时，账本（占八成以上、且排在前面）
    会把 loc 和 npcs 挤出窗口——规划器于是读满了物品增减流水，
    却不知道玩家在哪、认识谁，而这两样正是规划下一幕最需要的。
    """
    prompt = build_story_plan_prompt(StoryPlanContext(
        world_id="wuxia", pace="long", turn=40, reason="horizon",
        story_dna="x", game_state=_bloated_state(), recent_messages=[],
    ))
    assert "陈家渡渡口" in prompt
    assert "吴四娘" in prompt and "王掌柜" in prompt
    assert "债主" in prompt          # 关系本身，不只是名字


def test_planner_state_excludes_audit_ledger() -> None:
    """账本是给玩家查账用的审计日志，规划器用不上，不该占预算。"""
    digest = state_digest(_bloated_state())
    assert '"note":"增加"' not in digest
    assert "ledger" not in digest
    # 原始 JSON 三万多字符，精简后必须是一个量级以内的小串
    assert len(digest) < 1500


def test_state_digest_survives_garbage() -> None:
    """状态字段类型不对时不能抛异常——规划失败会让整局退回兼容模式。"""
    for bad in ({}, {"npcs": "不是字典"}, {"inv": 42}, {"skills": None},
                {"attrs": [], "res": "x", "talents": {}}, {"loc": None}):
        assert isinstance(state_digest(bad), str)


def test_unrevealed_sheet_tells_planner_not_to_use_numbers() -> None:
    digest = state_digest({"revealed": False, "attrs": {"力量": 5}, "loc": "村口"})
    assert "尚未揭示" in digest
    assert "力量5" not in digest
    assert "村口" in digest          # 位置任何时候都要给
