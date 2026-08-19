"""
状态结算测试
============
这里锁的是「程序说了算」的那些规则。它们的作用是挡住模型的得寸进尺：
不加约束的话，聊几十回合属性就会被一路加上去，物品也会越报越多。

另外锁住一批 JS 语义换算。移植时踩过的坑几乎全在这上面：
Number(null) 是 0、空数组是真值、Math.max(0,NaN) 是 NaN……
差一点点，物品数量就会从「归零删除」变成「保持一件」。
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402
from app.services.game_state import (  # noqa: E402
    apply_patch, js_number, js_truthy, normalize_inventory, normalize_item,
    stable_state_id,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def state(**kw) -> dict:
    base = {
        "revealed": True,
        "attrs": {"力量": 5, "身法": 3, "悟性": 7},
        "res": {"体力": 80, "内力": 40},
        "caps": {"体力": 100, "内力": 100},
        "talents": ["过目不忘"],
        "inv": [
            {"id": "item_1kn0yp3", "name": "铁剑", "quantity": 1, "category": "兵器",
             "equipped": True, "description": "", "consumable": False, "tags": []},
            {"id": "item_1rmi9ck", "name": "伤药", "quantity": 3, "category": "药品",
             "equipped": False, "description": "", "consumable": True, "tags": []},
        ],
        "skills": [
            {"id": "skill_85dzi3", "name": "太祖长拳", "category": "外功", "realm": "小成",
             "coefficient": 1.5, "proficiency": 62, "attribute": "力量",
             "description": "刚猛", "active": False},
        ],
        "npcs": {"吴四娘": {"rel": "邻居", "att": 1, "note": "浆洗为生", "knows": ["主角会拳脚"]}},
        "loadout": {"activeCoreId": None},
        "ledger": [],
        "loc": "陈家渡",
    }
    base.update(kw)
    return base


def run(patch: dict, st: dict | None = None) -> dict:
    return apply_patch(st or state(), patch, world_id="wuxia", turn=7)


# ── JS 语义换算 ─────────────────────────────────────────────────

def test_js_number_matches_javascript() -> None:
    """这些值都是模型输出里真出现过的，换算错一个就是一个线上 bug。"""
    assert js_number(None) == 0        # Number(null) === 0，不是 NaN
    assert js_number("") == 0
    assert js_number(True) == 1
    assert js_number([]) == 0          # Number([]) === 0
    assert js_number([7]) == 7
    assert js_number("3") == 3
    for bad in ("abc", {}, [1, 2]):
        assert js_number(bad) != js_number(bad)   # NaN


def test_js_truthy_differs_from_python() -> None:
    """空数组和空对象在 JS 里是真值——Python 直觉在这里会带偏。"""
    assert js_truthy([]) is True
    assert js_truthy({}) is True
    assert js_truthy(0) is False
    assert js_truthy("") is False
    assert js_truthy(None) is False


def test_stable_id_matches_frontend() -> None:
    """
    物品 id 由名字哈希而来，存进存档、还被 activeCoreId 引用。
    这几个期望值是从浏览器里跑前端实现取回来的，算错就意味着老存档
    认不出自己的物品，会凭空多出一份。
    """
    assert stable_state_id("item", "铁剑") == "item_1kn0yp3"
    assert stable_state_id("item", "伤药") == "item_1rmi9ck"
    assert stable_state_id("skill", "太祖长拳") == "skill_85dzi3"
    assert stable_state_id("item", "物品1") == "item_mo488a"
    assert stable_state_id("item", "123") == "item_vowx0b"


# ── 程序说了算的约束 ────────────────────────────────────────────

def test_attribute_moves_at_most_one_per_turn() -> None:
    """不设这条，模型一句「你感觉自己强了很多」就能加 5 点。"""
    assert run({"attr_delta": {"力量": 5}})["attrs"]["力量"] == 6
    assert run({"attr_delta": {"力量": -5}})["attrs"]["力量"] == 4
    assert run({"attr_set": {"力量": 20}})["attrs"]["力量"] == 6


def test_attribute_keys_are_schema_locked() -> None:
    """只能改已有的键，模型不能自造属性。"""
    out = run({"attr_delta": {"根本没有这个": 3}})
    assert "根本没有这个" not in out["attrs"]


def test_attributes_frozen_before_reveal() -> None:
    """角色卡没揭示时不该有数值，更不该被偷偷加天赋。"""
    st = state(revealed=False)
    out = run({"attr_delta": {"力量": 1}, "talent_add": ["天生神力"]}, st)
    assert out["attrs"]["力量"] == 5
    assert "天生神力" not in out["talents"]


def test_resource_respects_cap_and_floor() -> None:
    assert run({"res_delta": {"体力": 999}})["res"]["体力"] == 100
    assert run({"res_delta": {"体力": -9999}})["res"]["体力"] == 0


def test_npc_attitude_moves_one_step_at_a_time() -> None:
    """关系不该因为一句话就从点头之交变成生死之交。"""
    assert run({"npc_set": {"吴四娘": {"att": 5}}})["npcs"]["吴四娘"]["att"] == 2
    assert run({"npc_set": {"吴四娘": {"att": -5}}})["npcs"]["吴四娘"]["att"] == 0


def test_npc_knowledge_is_capped() -> None:
    """每个 NPC 的知情列表有上限，否则提示词会被它挤爆。"""
    adds = [f"事实{i}" for i in range(50)]
    knows = run({"npc_set": {"吴四娘": {"knows_add": adds}}})["npcs"]["吴四娘"]["knows"]
    assert len(knows) == 30


def test_skill_proficiency_capped() -> None:
    assert run({"skill_progress": [{"name": "太祖长拳", "delta": 999}]})["skills"][0]["proficiency"] == 100


# ── 物品 ────────────────────────────────────────────────────────

def test_item_consumed_to_zero_is_removed() -> None:
    out = run({"inv_delta": [{"name": "伤药", "delta": -3}]})
    assert [x["name"] for x in out["inv"]] == ["铁剑"]


def test_new_item_gets_stable_id_and_guessed_category() -> None:
    out = run({"inv_delta": [{"name": "金疮药", "delta": 2}]})
    new = next(x for x in out["inv"] if x["name"] == "金疮药")
    assert new["id"] == stable_state_id("item", "金疮药")
    assert new["category"] == "药品"


def test_same_item_merges_instead_of_duplicating() -> None:
    """模型换个说法就造出重复物品，是这套归一化要挡的主要问题。"""
    merged = normalize_inventory([
        {"name": "伤药", "quantity": 2},
        {"name": "伤药", "quantity": 3},
    ])
    assert len(merged) == 1 and merged[0]["quantity"] == 5


def test_null_quantity_means_zero_not_default() -> None:
    """
    {"quantity": null} 走 Number(null)=0，结果是这件物品被清零删除。
    这条是模糊测试逮出来的——手写用例根本想不到。
    """
    out = run({"inv_upsert": [{"name": "伤药", "quantity": None}]})
    assert [x["name"] for x in out["inv"]] == ["铁剑"]


def test_unusable_quantity_falls_back_to_one() -> None:
    """
    inv_add 末尾有个 isFinite(q)?q:1 的兜底：数量取不出来时按 1 件算，
    而不是放弃这一条。漏掉它会让「模型写了个怪数量」变成「物品凭空消失」。
    """
    out = run({"inv_add": [{"name": "干粮", "qty": {}}]})
    assert next(x for x in out["inv"] if x["name"] == "干粮")["quantity"] == 1


def test_normalize_item_keeps_unknown_keys() -> None:
    """
    前端是 Object.assign({}, raw) 起手的，多余的键会留在物品上。
    算个小瑕疵，但它已经写进现有存档了，迁移期间必须保持一致。
    """
    assert normalize_item({"name": "干粮", "delta": 2})["delta"] == 2


# ── 对垃圾输入的耐受 ────────────────────────────────────────────

@pytest.mark.parametrize("patch", [
    {"inv_add": [None]}, {"inv_rm": [None]}, {"inv_delta": [None]},
    {"skill_upsert": [123]}, {"inv_add": [123]}, {"npc_set": {"x": None}},
    {"attr_delta": "不是对象"}, {"inv_delta": 42}, {"talent_add": "字符串"},
    {"skill_progress": [None]}, {"equip_set": None}, {"loc": []},
])
def test_garbage_patch_never_raises(patch: dict) -> None:
    """
    原实现遇到 inv_add:[null] 会抛异常（JS 里 typeof null === 'object'，
    于是去读 null.quantity），而且是在补丁应用到一半时抛的，
    状态会停在不完整的样子。这里必须扛住。
    """
    out = run(patch)
    assert isinstance(out, dict) and "inv" in out


def test_partial_failure_cannot_corrupt_state() -> None:
    """垃圾字段不该阻断同一补丁里其它字段的生效。"""
    out = run({"res_delta": {"体力": -10}, "inv_add": [None], "loc": "城南"})
    assert out["res"]["体力"] == 70
    assert out["loc"] == "城南"


def test_input_state_is_not_mutated() -> None:
    """调用方可能还要拿原状态做对比或回滚。"""
    st = state()
    before = str(st)
    apply_patch(st, {"attr_delta": {"力量": 1}}, world_id="wuxia", turn=1)
    assert str(st) == before


# ── 账本 ────────────────────────────────────────────────────────

def test_ledger_records_every_change() -> None:
    """玩家发现数字不对时，这是唯一能回答「什么时候、因为什么变的」的地方。"""
    out = run({"inv_delta": [{"name": "伤药", "delta": -1}], "active_skill": "太祖长拳"})
    kinds = [(e["type"], e["ref"], e["note"]) for e in out["ledger"]]
    assert ("item", "伤药", "减少") in kinds
    assert ("loadout", "太祖长拳", "切换当前运转") in kinds
    assert all(e["turn"] == 7 for e in out["ledger"])


def test_ledger_is_bounded() -> None:
    st = state(ledger=[{"turn": 0, "time": 0, "type": "x", "ref": "", "note": "", "delta": None}] * 299)
    out = run({"inv_delta": [{"name": "伤药", "delta": -1}, {"name": "铁剑", "delta": 1}]}, st)
    assert len(out["ledger"]) == 300


# ── HTTP 契约 ───────────────────────────────────────────────────

def test_endpoint_returns_state_and_new_ledger(client: TestClient) -> None:
    r = client.post("/api/state/apply", json={
        "state": state(), "patch": {"inv_delta": [{"name": "伤药", "delta": -1}]},
        "world_id": "wuxia", "turn": 3})
    assert r.status_code == 200
    body = r.json()
    assert next(x for x in body["state"]["inv"] if x["name"] == "伤药")["quantity"] == 2
    # 只回本次新增的账本条目，前端可以直接拿来提示玩家
    assert len(body["ledger_added"]) == 1
    assert body["ledger_added"][0]["ref"] == "伤药"


def test_endpoint_rejects_missing_state(client: TestClient) -> None:
    assert client.post("/api/state/apply", json={"patch": {}}).status_code == 422
