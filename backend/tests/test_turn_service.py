"""TurnService 第一阶段：账本与自动存档的事务、幂等和冲突语义。"""
import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture
def client() -> TestClient:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def create_tables() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(create_tables())

    async def override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def new_session(client: TestClient) -> str:
    response = client.post("/api/sessions", json={"world_id": "fantasy", "pace": "long"})
    assert response.status_code == 200
    return response.json()["id"]


def snapshot(session_id: str, turn: int) -> dict:
    return {
        "schema_version": 2,
        "history": [
            {"role": "user", "content": "去冒险者公会看看"},
            {"role": "assistant", "content": "委托板前挤满了不同种族的冒险者。"},
        ],
        "gstate": {"attrs": {}, "inv": [], "skills": []},
        "world": "fantasy",
        "pace": "long",
        "turns": turn,
        "loreSid": session_id,
    }


def request_body(session_id: str, *, commit_id: str = "commit_turn_1", base_revision: int = 0) -> dict:
    turn = 1
    return {
        "commit_id": commit_id,
        "ledger": {
            "turn": turn,
            "events": [{
                "id": "event_turn_1",
                "kind": "player_turn",
                "actor": "玩家",
                "action": "去冒险者公会看看",
                "outcome": "玩家抵达公会并看见委托板。",
                "location": "冒险者公会",
            }],
        },
        "save_slot": "auto",
        "save": {
            "payload": snapshot(session_id, turn),
            "desc": "抵达冒险者公会",
            "world_id": "fantasy",
            "world_name": "剑与魔法",
            "turns": turn,
            "client_time": "8/24 18:00",
            "base_revision": base_revision,
        },
    }


def test_commit_writes_ledger_save_and_session_once(client: TestClient) -> None:
    session_id = new_session(client)
    body = request_body(session_id)

    first = client.post(f"/api/sessions/{session_id}/turn/commit", json=body)
    assert first.status_code == 200, first.text
    assert first.json()["replayed"] is False
    assert first.json()["ledger"]["events_written"] == 1
    assert first.json()["save"]["revision"] == 1

    assert client.get(f"/api/sessions/{session_id}").json()["turn_no"] == 1
    assert len(client.get(f"/api/sessions/{session_id}/ledger").json()["events"]) == 1
    assert client.get("/api/saves/auto").json()["payload"]["turns"] == 1

    replay = client.post(f"/api/sessions/{session_id}/turn/commit", json=body)
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["save"]["revision"] == 1
    assert len(client.get(f"/api/sessions/{session_id}/ledger").json()["events"]) == 1


def test_save_conflict_rolls_back_the_entire_turn(client: TestClient) -> None:
    session_id = new_session(client)
    old = snapshot(session_id, 0)
    old["history"] = []
    created = client.put("/api/saves/auto", json={
        "payload": old,
        "desc": "另一台设备的存档",
        "world_id": "fantasy",
        "world_name": "剑与魔法",
        "turns": 0,
        "base_revision": 0,
    })
    assert created.status_code == 200

    response = client.post(
        f"/api/sessions/{session_id}/turn/commit",
        json=request_body(session_id, base_revision=0),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "save_conflict"
    assert client.get(f"/api/sessions/{session_id}").json()["turn_no"] == 0
    assert client.get(f"/api/sessions/{session_id}/ledger").json()["events"] == []
    assert client.get("/api/saves/auto").json()["revision"] == 1


def test_turn_contract_rejects_mixed_session_or_turn(client: TestClient) -> None:
    session_id = new_session(client)
    body = request_body(session_id)
    body["save"]["payload"]["turns"] = 2
    mismatch = client.post(f"/api/sessions/{session_id}/turn/commit", json=body)
    assert mismatch.status_code == 422
    assert mismatch.json()["detail"]["code"] == "turn_number_mismatch"

    body = request_body(session_id)
    body["save"]["payload"]["loreSid"] = "another-session"
    mismatch = client.post(f"/api/sessions/{session_id}/turn/commit", json=body)
    assert mismatch.status_code == 422
    assert mismatch.json()["detail"]["code"] == "turn_session_mismatch"


def test_commit_id_and_turn_number_cannot_be_reused_for_other_content(client: TestClient) -> None:
    session_id = new_session(client)
    body = request_body(session_id)
    assert client.post(f"/api/sessions/{session_id}/turn/commit", json=body).status_code == 200

    changed = request_body(session_id)
    changed["ledger"]["events"][0]["outcome"] = "另一份结果"
    reused_id = client.post(f"/api/sessions/{session_id}/turn/commit", json=changed)
    assert reused_id.status_code == 409
    assert reused_id.json()["detail"]["code"] == "commit_id_reused"

    changed["commit_id"] = "another_commit_1"
    changed["save"]["base_revision"] = 1
    reused_turn = client.post(f"/api/sessions/{session_id}/turn/commit", json=changed)
    assert reused_turn.status_code == 409
    assert reused_turn.json()["detail"]["code"] == "turn_already_committed"


def test_rollback_releases_turn_for_regeneration(client: TestClient) -> None:
    session_id = new_session(client)
    assert client.post(
        f"/api/sessions/{session_id}/turn/commit",
        json=request_body(session_id),
    ).status_code == 200

    rolled = client.post(
        f"/api/sessions/{session_id}/rollback",
        json={"from_turn": 1, "reason": "regen"},
    )
    assert rolled.status_code == 200
    assert rolled.json()["turn_commits"] == 1

    regenerated = request_body(
        session_id, commit_id="commit_turn_1_regenerated", base_revision=1,
    )
    regenerated["ledger"]["events"][0]["outcome"] = "重写后的公会场景。"
    response = client.post(
        f"/api/sessions/{session_id}/turn/commit", json=regenerated,
    )
    assert response.status_code == 200, response.text
    assert response.json()["save"]["revision"] == 2
