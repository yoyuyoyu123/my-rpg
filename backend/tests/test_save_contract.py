"""
存档契约测试
============
存档是玩家几十小时的进度。以前这里的契约是 `payload: dict[str, Any]`——
等于「随便什么都收」。代价实测过：把 gstate 改个名，后端照收 HTTP 200，
读档时属性、背包、位置全部消失，一句报错都没有。

所以这组测试锁的是三件事：
    1. 缺必要字段要**当场报错**，不能静默吞掉；
    2. 冻结契约之前的老存档要能继续打开（尽力抢救并告知）；
    3. 版本比程序新的存档要拒绝打开，而不是读一半丢一半。
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
from app.schemas.save import SAVE_SCHEMA_VERSION  # noqa: E402
from app.services.save_migration import (  # noqa: E402
    SaveFormatError, migrate_payload, stamp,
)


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


def a_save(**kw) -> dict:
    """一份结构完整的存档正文。"""
    payload = {
        "schema_version": SAVE_SCHEMA_VERSION,
        "history": [{"role": "user", "content": "开始游戏"},
                    {"role": "assistant", "content": "雨停了。"}],
        "gstate": {"revealed": True, "attrs": {"力量": 7}, "loc": "陈家渡",
                   "inv": [{"id": "i1", "name": "铁剑", "quantity": 1}]},
        "world": "wuxia", "pace": "long", "turns": 23,
        # 另外三十来个运行时字段，靠 extra=allow 原样透传
        "outline": "主角想重开铁匠铺", "loreSid": "abc123", "prefs": {"tone": "温馨"},
    }
    payload.update(kw)
    return payload


def _put(client: TestClient, slot: str, payload: dict):
    return client.put(f"/api/saves/{slot}", json={
        "payload": payload, "desc": "测试", "world_id": "wuxia",
        "world_name": "武侠江湖", "turns": 23, "client_time": "8/22 10:00"})


# ── 字段改名必须当场炸，而不是静默丢进度 ────────────────────────

def test_renamed_field_is_rejected_loudly(client: TestClient) -> None:
    """
    这条是整组测试存在的理由。
    `gstate` 改名成 `game_state` 是一次很平常的重构，以前它会让后端返回 200、
    玩家读档时角色卡变空白且毫无提示。现在必须 422。
    """
    broken = a_save()
    broken["game_state"] = broken.pop("gstate")

    r = _put(client, "sv_0", broken)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "save_invalid"
    assert "gstate" in r.json()["detail"]["message"]

    # 而且坏数据不能进库
    assert client.get("/api/saves/sv_0").status_code == 404


def test_missing_history_is_rejected(client: TestClient) -> None:
    """没有历史就不是存档，只是一坨设置。"""
    broken = a_save()
    del broken["history"]
    assert _put(client, "sv_0", broken).status_code == 422


@pytest.mark.parametrize("bad", [
    {"history": "不是数组"}, {"gstate": "不是对象"}, {"turns": -5},
])
def test_wrong_types_are_rejected(client: TestClient, bad: dict) -> None:
    assert _put(client, "sv_0", a_save(**bad)).status_code == 422


# ── 老存档要能继续打开 ──────────────────────────────────────────

def test_legacy_save_without_version_still_loads(client: TestClient) -> None:
    """
    冻结契约之前写的存档没有 schema_version。它们的字段本来就没保证，
    不该因为我们后来定了规矩就打不开——那是拿玩家的进度给自己的规范陪葬。
    """
    legacy = a_save()
    del legacy["schema_version"]

    assert _put(client, "sv_1", legacy).status_code == 200
    got = client.get("/api/saves/sv_1").json()
    assert got["payload"]["schema_version"] == SAVE_SCHEMA_VERSION
    assert got["payload"]["gstate"]["loc"] == "陈家渡"      # 内容没动
    assert got["payload"]["outline"] == "主角想重开铁匠铺"   # 额外字段也透传


def test_legacy_missing_gstate_is_repaired_with_a_note() -> None:
    """
    没版本号 + 缺角色卡 = 很老的存档，尽力抢救并明确告知，
    而不是假装没事。注意这跟「声明了版本却缺字段」是两种处理。
    """
    legacy = {"history": [{"role": "user", "content": "x"}], "world": "wuxia"}
    payload, notes = migrate_payload(legacy)
    assert payload["gstate"] == {}
    assert payload["schema_version"] == SAVE_SCHEMA_VERSION
    assert any("角色状态" in n for n in notes)


def test_declared_version_gets_no_mercy() -> None:
    """
    同样是缺 gstate，声明了版本的直接报错——那不是老存档，
    是新规矩下写坏的数据，多半有人改了字段名。
    """
    with pytest.raises(SaveFormatError):
        migrate_payload({"schema_version": SAVE_SCHEMA_VERSION,
                         "history": [{"role": "user", "content": "x"}]})


def test_migration_notes_reach_the_client(client: TestClient) -> None:
    """补救记录要传到前端，玩家才知道自己的存档被动过什么。"""
    legacy = {"history": [{"role": "user", "content": "x"}], "world": "wuxia"}
    r = _put(client, "sv_2", legacy)
    assert r.status_code == 200
    # 补救发生在写入那一刻，所以提示必须出现在写入的回应里——
    # 只在读取时回传的话，本机镜像上传的老存档永远等不到那个提示
    assert any("角色状态" in n for n in r.json()["migrations"])


# ── 版本比程序新的要拒绝 ────────────────────────────────────────

def test_future_version_is_refused() -> None:
    """
    手机上用新版存的档，拿到没升级的电脑上打开——读一半丢一半比打不开更糟。
    存档跟着服务端走之后，这种跨版本情况是会真实发生的。
    """
    with pytest.raises(SaveFormatError) as exc:
        migrate_payload(a_save(schema_version=SAVE_SCHEMA_VERSION + 5))
    assert "更新" in str(exc.value)


# ── 版本戳与列表 ────────────────────────────────────────────────

def test_saved_payload_is_stamped(client: TestClient) -> None:
    """写进去的一律盖当前版本，下次读取才知道该不该迁移。"""
    _put(client, "sv_0", a_save())
    assert client.get("/api/saves/sv_0").json()["payload"]["schema_version"] == SAVE_SCHEMA_VERSION
    assert client.get("/api/saves").json()[0]["schema_version"] == SAVE_SCHEMA_VERSION


def test_stamp_does_not_mutate_input() -> None:
    src = {"history": [], "gstate": {}}
    stamp(src)
    assert "schema_version" not in src


def test_round_trip_preserves_every_field(client: TestClient) -> None:
    """除了盖版本号，正文一个字段都不能少——存档丢字段就是丢进度。"""
    original = a_save()
    _put(client, "sv_0", original)
    got = client.get("/api/saves/sv_0").json()["payload"]
    for key, value in original.items():
        assert got[key] == value, f"字段 {key} 在往返中变了"
