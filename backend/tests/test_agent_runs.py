"""AgentRun 持久化与查询契约。"""

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402


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


def new_session(client: TestClient) -> str:
    response = client.post(
        "/api/sessions",
        json={"world_id": "wuxia", "pace": "long", "title": "AgentRun 测试"},
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def run_payload(session_id: str, *, status: str = "running") -> dict:
    return {
        "run_id": "agent_test_run_1",
        "parent_id": "agent_parent_1",
        "session_id": session_id,
        "turn_id": 3,
        "agent": "commit",
        "title": "提交第 3 回合",
        "status": status,
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "thinking": True,
        "input": "commit_id=commit_test",
        "output": "第 3 回合提交完成",
        "reasoning": "先验证版本，再提交事务",
        "error": "",
        "usage": {"total_tokens": 42},
        "stages": [{"name": "服务端事务", "status": "done", "atMs": 120}],
        "meta": {"commitId": "commit_test"},
        "retries": 0,
        "started_at": "2026-08-24T10:00:00.000Z",
        "duration_ms": 240,
    }


def test_agent_run_upsert_and_get(client: TestClient) -> None:
    sid = new_session(client)
    first = client.post("/api/agent-runs", json=run_payload(sid))
    assert first.status_code == 200, first.text
    assert first.json()["session_id"] == sid
    assert first.json()["turn_id"] == 3
    assert first.json()["thinking"] is True

    updated = run_payload(sid, status="done")
    updated["output"] = "已完成并可恢复"
    second = client.post("/api/agent-runs", json=updated)
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "done"
    assert second.json()["output"] == "已完成并可恢复"

    got = client.get("/api/agent-runs/agent_test_run_1")
    assert got.status_code == 200
    assert got.json()["reasoning"] == "先验证版本，再提交事务"
    assert got.json()["stages"][0]["name"] == "服务端事务"


def test_agent_runs_are_queryable_by_session_and_turn(client: TestClient) -> None:
    sid = new_session(client)
    body = run_payload(sid)
    client.post("/api/agent-runs", json=body)
    body["run_id"] = "agent_test_run_2"
    body["turn_id"] = 4
    client.post("/api/agent-runs", json=body)

    all_rows = client.get(f"/api/sessions/{sid}/agent-runs").json()
    assert {row["run_id"] for row in all_rows} == {"agent_test_run_1", "agent_test_run_2"}
    turn_rows = client.get(f"/api/sessions/{sid}/agent-runs?turn_id=4").json()
    assert [row["run_id"] for row in turn_rows] == ["agent_test_run_2"]


def test_agent_runs_support_agent_status_and_offset_filters(client: TestClient) -> None:
    sid = new_session(client)
    for index, (agent, status) in enumerate(
        [("planner", "done"), ("narrative", "error"), ("planner", "running")],
        start=1,
    ):
        body = run_payload(sid, status=status)
        body.update({
            "run_id": f"agent_filter_{index}",
            "agent": agent,
            "started_at": f"2026-08-24T12:0{index}:00.000Z",
        })
        assert client.post("/api/agent-runs", json=body).status_code == 200

    planner = client.get(f"/api/sessions/{sid}/agent-runs?agent=planner").json()
    done = client.get(f"/api/sessions/{sid}/agent-runs?status=done").json()
    page = client.get(f"/api/sessions/{sid}/agent-runs?limit=1&offset=1").json()
    assert {row["agent"] for row in planner} == {"planner"}
    assert {row["status"] for row in done} == {"done"}
    assert len(page) == 1


def test_agent_run_rejects_cross_session_reuse(client: TestClient) -> None:
    sid1, sid2 = new_session(client), new_session(client)
    assert client.post("/api/agent-runs", json=run_payload(sid1)).status_code == 200
    reused = run_payload(sid2)
    assert client.post("/api/agent-runs", json=reused).status_code == 409


def test_agent_run_rejects_unknown_session(client: TestClient) -> None:
    response = client.post("/api/agent-runs", json=run_payload("missing-session"))
    assert response.status_code == 404
