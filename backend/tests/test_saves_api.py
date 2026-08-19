"""
存档 API 测试
=============
存档从 IndexedDB 搬到服务端，是为了让手机和电脑看到同一批进度。
这里锁住前端依赖的契约：槽位约束、摘要与正文分离、覆盖语义。
"""
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
        async with maker() as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


SNAPSHOT = {
    "history": [{"role": "user", "content": "开始游戏"},
                {"role": "assistant", "content": "河面上浮着薄雾。"}],
    "gstate": {"attrs": {"体质": 3}},
    "loreSid": "abc123",
}


def _write(client: TestClient, slot: str, **kw):
    body = {"payload": SNAPSHOT, "desc": "陈家渡的清晨", "world_id": "wuxia",
            "world_name": "武侠江湖", "turns": 7, "client_time": "8/19 10:30"}
    body.update(kw)
    return client.put(f"/api/saves/{slot}", json=body)


# ── 槽位约束 ────────────────────────────────────────────────────

def test_only_known_slots_accepted(client: TestClient) -> None:
    """限制槽位名，避免这个接口变成任人写入的键值仓库。"""
    assert _write(client, "auto").status_code == 200
    assert _write(client, "sv_0").status_code == 200
    for bad in ("hacker", "sv_abc", "sv_999", ""):
        r = client.put(f"/api/saves/{bad}", json={"payload": {}})
        assert r.status_code in (400, 404, 405), f"{bad} 应被拒绝"


# ── 摘要与正文分离 ──────────────────────────────────────────────

def test_list_never_includes_payload(client: TestClient) -> None:
    """
    存档正文可能几 MB。列表接口带上正文的话，
    打开一次侧栏就要传十几 MB —— 手机上尤其难受。
    """
    _write(client, "sv_0")
    rows = client.get("/api/saves").json()
    assert len(rows) == 1
    assert "payload" not in rows[0]
    assert rows[0]["desc"] == "陈家渡的清晨"
    assert rows[0]["world_name"] == "武侠江湖"
    assert rows[0]["turns"] == 7
    assert rows[0]["size_bytes"] > 0


def test_detail_round_trips_payload(client: TestClient) -> None:
    """存进去什么，读出来必须一模一样——存档丢字段就是丢进度。"""
    _write(client, "sv_1")
    got = client.get("/api/saves/sv_1").json()
    assert got["payload"] == SNAPSHOT
    assert got["payload"]["loreSid"] == "abc123"


# ── 覆盖与删除 ──────────────────────────────────────────────────

def test_put_overwrites_same_slot(client: TestClient) -> None:
    """存档是覆盖语义，不该在同一个槽位堆出两条记录。"""
    _write(client, "sv_0", desc="第一次")
    _write(client, "sv_0", desc="第二次", turns=20,
           payload={"history": [], "marker": "新的"})
    rows = client.get("/api/saves").json()
    assert len(rows) == 1
    assert rows[0]["desc"] == "第二次" and rows[0]["turns"] == 20
    assert client.get("/api/saves/sv_0").json()["payload"]["marker"] == "新的"


def test_missing_save_is_404(client: TestClient) -> None:
    """空槽位返回 404，前端据此显示「— 空 —」，不是错误。"""
    r = client.get("/api/saves/sv_2")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "save_not_found"


def test_delete_save(client: TestClient) -> None:
    _write(client, "sv_0")
    assert client.delete("/api/saves/sv_0").status_code == 200
    assert client.get("/api/saves/sv_0").status_code == 404
    assert client.get("/api/saves").json() == []


def test_delete_missing_is_404(client: TestClient) -> None:
    assert client.delete("/api/saves/sv_0").status_code == 404


def test_slots_are_independent(client: TestClient) -> None:
    """三个手动槽位加一个自动槽位互不干扰。"""
    for slot in ("auto", "sv_0", "sv_1", "sv_2"):
        _write(client, slot, desc=f"进度-{slot}")
    rows = {r["slot"]: r["desc"] for r in client.get("/api/saves").json()}
    assert rows == {s: f"进度-{s}" for s in ("auto", "sv_0", "sv_1", "sv_2")}
