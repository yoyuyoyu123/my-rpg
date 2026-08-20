"""
会话与记忆 API 测试
===================
锁死前端依赖的 HTTP 契约：开局、写事实、检索注入、矛盾拦截。

和 test_memory.py 的分工：
    test_memory.py  —— 服务层逻辑（不经过 HTTP）
    这个文件        —— 路由层契约（状态码、字段名、请求体校验）
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
    """
    每个测试一个全新的内存数据库。

    做法是覆盖 get_db 这个依赖——这正是依赖注入的价值：
    生产用文件数据库，测试用内存数据库，被测代码一行都不用改。
    """
    # StaticPool：让所有请求复用同一条内存连接，否则每次连接都是一个空库
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


def _new_session(client: TestClient, **kw) -> str:
    body = {"world_id": "wuxia", "pace": "long", "title": "测试局"}
    body.update(kw)
    r = client.post("/api/sessions", json=body)
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ── 世界观目录 ──────────────────────────────────────────────────

def test_worlds_never_leak_prompt(client: TestClient) -> None:
    """提示词是核心资产，绝不能随目录下发。"""
    r = client.get("/api/worlds")
    assert r.status_code == 200
    worlds = r.json()
    assert len(worlds) >= 5
    for w in worlds:
        assert "prompt" not in w
        assert w["id"] and w["name"]


# ── 会话 ────────────────────────────────────────────────────────

def test_create_and_read_session(client: TestClient) -> None:
    sid = _new_session(client)
    r = client.get(f"/api/sessions/{sid}")
    assert r.status_code == 200
    data = r.json()
    assert data["world_id"] == "wuxia"
    assert data["world_name"] == "武侠江湖"
    assert data["turn_no"] == 0


def test_unknown_world_rejected(client: TestClient) -> None:
    r = client.post("/api/sessions", json={"world_id": "不存在的世界"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "unknown_world"


def test_missing_session_is_404(client: TestClient) -> None:
    r = client.get("/api/sessions/nope")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "session_not_found"


def test_delete_session(client: TestClient) -> None:
    sid = _new_session(client)
    assert client.delete(f"/api/sessions/{sid}").status_code == 200
    assert client.get(f"/api/sessions/{sid}").status_code == 404


# ── 记忆写入与矛盾拦截 ──────────────────────────────────────────

def test_write_facts_then_retrieve(client: TestClient) -> None:
    sid = _new_session(client)
    r = client.post(f"/api/sessions/{sid}/memory", json={
        "turn": 3,
        "entities": [{
            "name": "吴四娘", "kind": "person", "aliases": ["吴婶"], "importance": 2,
            "facts": [{"key": "职业", "value": "洗衣妇"},
                      {"key": "出身", "value": "陈家渡本地人"}],
        }],
    })
    assert r.status_code == 200
    assert r.json()["facts_written"] == 2
    assert r.json()["conflicts"] == []

    # 用别名也要能检索到
    r = client.get(f"/api/sessions/{sid}/context", params={"mentioned": "吴婶"})
    assert r.status_code == 200
    text = r.json()["text"]
    assert "吴四娘" in text and "洗衣妇" in text
    assert r.json()["entity_count"] == 1


def test_stable_attr_change_is_blocked(client: TestClient) -> None:
    """稳定属性被改写 → 拦截并上报，且不写库。这是一致性的核心保证。"""
    sid = _new_session(client)
    client.post(f"/api/sessions/{sid}/memory", json={
        "turn": 3,
        "entities": [{"name": "吴四娘", "kind": "person",
                      "facts": [{"key": "出身", "value": "陈家渡本地人"}]}],
    })
    r = client.post(f"/api/sessions/{sid}/memory", json={
        "turn": 12,
        "entities": [{"name": "吴四娘", "kind": "person",
                      "facts": [{"key": "出身", "value": "府城来的"},
                                {"key": "居所", "value": "槐树巷"}]}],
    })
    body = r.json()
    assert body["facts_written"] == 1          # 只有可变的「居所」写进去了
    assert len(body["conflicts"]) == 1
    c = body["conflicts"][0]
    assert c["key"] == "出身"
    assert c["old_value"] == "陈家渡本地人" and c["new_value"] == "府城来的"
    assert c["old_turn"] == 3

    # 库里仍是原值
    text = client.get(f"/api/sessions/{sid}/context").json()["text"]
    assert "陈家渡本地人" in text and "府城来的" not in text


def test_player_declaration_overrides_ai(client: TestClient) -> None:
    """玩家说了算——source=player 可以改稳定属性。"""
    sid = _new_session(client)
    client.post(f"/api/sessions/{sid}/memory", json={
        "turn": 3,
        "entities": [{"name": "吴四娘", "kind": "person",
                      "facts": [{"key": "出身", "value": "陈家渡本地人"}]}],
    })
    r = client.post(f"/api/sessions/{sid}/memory", json={
        "turn": 5, "source": "player",
        "entities": [{"name": "吴四娘", "kind": "person",
                      "facts": [{"key": "出身", "value": "府城来的"}]}],
    })
    assert r.json()["conflicts"] == []
    assert "府城来的" in client.get(f"/api/sessions/{sid}/context").json()["text"]


def test_context_empty_when_nothing_recorded(client: TestClient) -> None:
    """没记住东西时返回空串，前端拼进提示词不会多出噪音。"""
    sid = _new_session(client)
    r = client.get(f"/api/sessions/{sid}/context")
    assert r.json()["text"] == ""
    assert r.json()["entity_count"] == 0


# ── 前端代跑模型的「出题/交卷」两步 ────────────────────────────

def test_extract_prompt_carries_vocabulary(client: TestClient) -> None:
    """题目里必须带属性词表，否则模型会自造 key，查询和矛盾检测就全失效。"""
    sid = _new_session(client)
    r = client.post(f"/api/sessions/{sid}/extract/prompt", json={
        "turn": 1, "narrative": "吴四娘在河边洗衣。", "player_input": "打招呼",
    })
    assert r.status_code == 200
    p = r.json()["prompt"]
    assert "出身" in p and "person" in p          # 词表在
    assert "吴四娘在河边洗衣" in p                  # 叙事在
    assert r.json()["max_tokens"] > 0


def test_extract_prompt_carries_known_facts_for_deduplication(client: TestClient) -> None:
    """抽取器必须看到旧事实，否则同一描述换个说法就会反复报警。"""
    sid = _new_session(client)
    client.post(f"/api/sessions/{sid}/memory", json={
        "turn": 1,
        "entities": [{"name": "莉亚", "kind": "person",
                      "facts": [{"key": "出身", "value": "北境"}]}],
    })
    r = client.post(f"/api/sessions/{sid}/extract/prompt", json={
        "turn": 2, "narrative": "莉亚谈起故乡。", "player_input": "听她说",
    })
    prompt = r.json()["prompt"]
    assert "已记录事实（不要重复抽取）" in prompt
    assert "莉亚" in prompt and "出身=北境" in prompt


def test_extract_result_parses_and_stores(client: TestClient) -> None:
    """前端把模型原文交回来，后端负责挖 JSON、清洗、入库。"""
    sid = _new_session(client)
    raw = (
        "好的，结果如下：\n```json\n"
        '{"entities":[{"name":"吴四娘","kind":"person","aliases":["吴婶"],'
        '"importance":2,"facts":[{"key":"职业","value":"洗衣妇"},'
        '{"key":"胡说八道","value":"词表外的属性"}]}]}\n```'
    )
    r = client.post(f"/api/sessions/{sid}/extract/result", json={"turn": 4, "raw": raw})
    assert r.status_code == 200
    assert r.json()["facts_written"] == 1        # 词表外的那条被丢掉了

    text = client.get(f"/api/sessions/{sid}/context").json()["text"]
    assert "洗衣妇" in text and "胡说八道" not in text


def test_extract_result_survives_garbage(client: TestClient) -> None:
    """模型抽风时只是「这回合没记住东西」，绝不能让玩家的回合失败。"""
    sid = _new_session(client)
    r = client.post(f"/api/sessions/{sid}/extract/result",
                    json={"turn": 4, "raw": "抱歉，我无法完成这个请求。"})
    assert r.status_code == 200
    assert r.json()["facts_written"] == 0


# ── 设定档案 ────────────────────────────────────────────────────

def test_entities_panel_and_manual_delete(client: TestClient) -> None:
    """玩家发现程序记错了，能手动删掉。"""
    sid = _new_session(client)
    client.post(f"/api/sessions/{sid}/memory", json={
        "turn": 1,
        "entities": [{"name": "陈家渡", "kind": "place", "importance": 3,
                      "facts": [{"key": "类型", "value": "渡口小镇"}]}],
    })
    ents = client.get(f"/api/sessions/{sid}/entities").json()
    assert len(ents) == 1
    assert ents[0]["name"] == "陈家渡"
    assert ents[0]["facts"][0]["stability"] in {"stable", "mutable"}

    eid = ents[0]["id"]
    assert client.delete(f"/api/sessions/{sid}/entities/{eid}").status_code == 200
    assert client.get(f"/api/sessions/{sid}/entities").json() == []


def test_turn_no_advances_with_writes(client: TestClient) -> None:
    sid = _new_session(client)
    client.post(f"/api/sessions/{sid}/memory", json={
        "turn": 7,
        "entities": [{"name": "陈家渡", "kind": "place",
                      "facts": [{"key": "类型", "value": "渡口小镇"}]}],
    })
    assert client.get(f"/api/sessions/{sid}").json()["turn_no"] == 7
