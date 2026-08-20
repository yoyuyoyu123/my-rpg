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
from app.services.story_planner import build_story_plan_prompt, parse_story_runtime  # noqa: E402


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
            "allowed_developments": ["正常问价", "离开继续找住处"],
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
    assert "老板私下欠了税" not in agent
    assert "旧式隐藏大纲" not in agent
    assert "【研究库灵感候选】" not in agent
    assert len(agent) < len(legacy)


def test_story_endpoints() -> None:
    client = TestClient(app)
    p = client.post("/api/story/plan/prompt", json={"world_id": "fantasy"})
    assert p.status_code == 200 and p.json()["max_tokens"] >= 1000
    r = client.post("/api/story/plan/result", json={
        "raw": json.dumps(sample_runtime(), ensure_ascii=False),
        "previous_runtime": {}, "turn": 0, "reason": "opening",
    })
    assert r.status_code == 200
    assert r.json()["runtime"]["current_scene"]["id"] == "bakery"
