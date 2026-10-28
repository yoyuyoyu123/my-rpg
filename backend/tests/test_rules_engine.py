import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.schemas.rules import RuleActionIn, RuleCheckIn  # noqa: E402
from app.services.rules_engine import resolve_action, resolve_check  # noqa: E402


def test_check_is_deterministic_when_die_is_supplied() -> None:
    result = resolve_check(RuleCheckIn(
        action="潜行", attr="身法", attr_value=4, skill="潜行",
        skill_bonus=6, die=40, dc=60,
    ))
    assert result.die == 40
    assert result.total == 66
    assert result.outcome == "成功"
    assert result.success is True


def test_extreme_results_are_classified_by_program() -> None:
    assert resolve_check(RuleCheckIn(die=100, dc=50)).outcome == "大成功"
    assert resolve_check(RuleCheckIn(die=1, dc=90)).outcome == "大失败"


def test_check_endpoint_returns_structured_result() -> None:
    response = TestClient(app).post("/api/rules/check", json={
        "action": "开锁", "attr": "身法", "attr_value": 2,
        "die": 50, "dc": 55,
    })
    assert response.status_code == 200
    assert response.json()["total"] == 60
    assert response.json()["success"] is True


def test_move_action_rejects_unknown_location_and_returns_patch() -> None:
    rejected = resolve_action(RuleActionIn(
        kind="move", state={"loc": "南门"}, payload={"destination": "未开放区域"},
        known_locations=["南门", "北门"],
    ))
    assert rejected.accepted is False
    assert rejected.errors == ["unknown_location:未开放区域"]

    accepted = resolve_action(RuleActionIn(
        kind="move", state={"loc": "南门"}, payload={"destination": "北门"},
        known_locations=["南门", "北门"], turn=3,
    ))
    assert accepted.accepted is True
    assert accepted.patch == {"loc": "北门"}
    assert accepted.effects["clock_delta"] == 1


def test_trade_action_checks_authoritative_resources_and_inventory() -> None:
    state = {"res": {"coins": 100}, "inv": [{"id": "item_tea", "name": "茶叶", "quantity": 2}]}
    buy = resolve_action(RuleActionIn(
        kind="trade", state=state,
        payload={"direction": "buy", "item_id": "item_salt", "item_name": "盐", "quantity": 2, "unit_price": 15},
    ))
    assert buy.accepted is True
    assert buy.patch == {"res_delta": {"coins": -30.0}, "inv_delta": [{"id": "item_salt", "name": "盐", "delta": 2}]}

    sell = resolve_action(RuleActionIn(
        kind="trade", state=state,
        payload={"direction": "sell", "item": {"id": "item_tea", "name": "茶叶"}, "quantity": 3, "unit_price": 10},
    ))
    assert sell.accepted is False
    assert sell.errors == ["insufficient_item"]


def test_quest_action_owns_lifecycle_without_parsing_narrative() -> None:
    added = resolve_action(RuleActionIn(
        kind="quest", quests={"main": [], "side": []},
        payload={"op": "add", "type": "main", "name": "修好渡船", "description": "找到木料"},
    ))
    assert added.accepted is True
    assert added.quest_patch["add"][0]["bucket"] == "main"
    quest = added.quest_patch["add"][0]["quest"]

    completed = resolve_action(RuleActionIn(
        kind="quest", quests={"main": [quest], "side": []},
        payload={"op": "complete", "name": "修好渡船"},
    ))
    assert completed.accepted is True
    assert completed.quest_patch["complete"] == [{"id": None, "name": "修好渡船"}]


def test_action_endpoint_exposes_same_contract() -> None:
    response = TestClient(app).post("/api/rules/action", json={
        "kind": "move", "state": {"loc": "旧街"},
        "payload": {"destination": "码头"}, "known_locations": ["旧街", "码头"],
    })
    assert response.status_code == 200
    assert response.json()["patch"] == {"loc": "码头"}
