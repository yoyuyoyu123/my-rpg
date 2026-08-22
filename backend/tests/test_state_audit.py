"""
状态审计测试
============
审计负责回答「叙事里真正发生了什么状态变化」，它的结论决定要不要动权威数值。

两条最容易搞错、也最要命的语义：
    patch = None  →  审计**没能完成**。调用方必须据此不结算。
    patch = {}    →  审计确认这一回合没有变化。是有效结论。
混为一谈的后果是：审计一失败就退回去用叙事模型自己的申报——
而那份申报正是审计要核对的对象，等于审计从来没存在过。
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402
from app.services.state_audit import (  # noqa: E402
    build_audit_prompt, compact_state, parse_audit_result, strip_protocol_blocks,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def a_state() -> dict:
    return {
        "revealed": True,
        "attrs": {"力量": 5}, "res": {"体力": 80}, "caps": {"体力": 100},
        "talents": ["过目不忘"],
        "inv": [{"id": "item_1rmi9ck", "name": "伤药", "quantity": 3,
                 "category": "药品", "equipped": False, "description": "",
                 "consumable": True, "tags": []}],
        "skills": [{"id": "skill_85dzi3", "name": "太祖长拳", "category": "外功",
                    "realm": "小成", "coefficient": 1.5, "proficiency": 62,
                    "attribute": "力量", "description": "刚猛", "active": False}],
        "loadout": {"activeCoreId": None},
        "loc": "陈家渡",
        "npcs": {"吴四娘": {"rel": "邻居", "att": 2, "note": "浆洗为生",
                            "knows": ["主角会拳脚"]}},
        # 账本最多 300 条、占状态 JSON 的八成——它绝不该进提示词
        "ledger": [{"turn": i, "type": "item", "ref": f"物品{i}",
                    "note": "增加", "delta": 1} for i in range(300)],
    }


# ── 提示词只带该带的 ────────────────────────────────────────────

def test_audit_prompt_excludes_the_ledger() -> None:
    """
    账本是给玩家查账用的审计日志，塞进提示词纯属烧钱，
    还会把真正有用的字段挤出上下文——规划器那边踩过一模一样的坑。
    """
    prompt = build_audit_prompt(
        before=a_state(), player_input="吃药", reply="你服下伤药。", declared=[])
    assert '"note":"增加"' not in prompt
    assert "ledger" not in prompt
    # 但真正要判断的东西必须在
    assert "陈家渡" in prompt and "伤药" in prompt and "吴四娘" in prompt


def test_compact_state_keeps_only_what_matters() -> None:
    c = compact_state(a_state())
    assert set(c) == {"revealed", "attrs", "res", "inv", "skills",
                      "talents", "loc", "npcs"}
    # 物品只留判断得上的字段，描述和标签不进提示词
    assert set(c["inv"][0]) == {"id", "name", "category", "quantity", "equipped"}


def test_declared_patch_is_labelled_as_candidate_only() -> None:
    """
    叙事模型的申报只是候选。把它和「可见结果」混在一起，
    等于让模型自己给自己作证。
    """
    prompt = build_audit_prompt(
        before=a_state(), player_input="练拳", reply="你练了一个时辰。",
        declared=[{"skill_progress": [{"name": "太祖长拳", "delta": 3}]}])
    assert "候选申报" in prompt
    assert "叙事模型申报只是候选" in prompt


def test_hidden_blocks_are_stripped_from_visible_result() -> None:
    """STATE 块是模型的申报，不是证据——它另外走 declared 字段。"""
    text = strip_protocol_blocks(
        '正文在这里。\n【STATE】{"loc":"城南"}【/STATE】\n'
        '【大纲】主线备忘【/大纲】\n还有后文。')
    assert "正文在这里。" in text and "还有后文。" in text
    assert "城南" not in text and "主线备忘" not in text


def test_unclosed_block_is_left_alone() -> None:
    """截断的正文里可能有半个协议块；剥不掉就留着，总好过误删正文。"""
    assert "正文" in strip_protocol_blocks('正文\n【STATE】{"loc":"半截')


def test_long_inputs_are_capped() -> None:
    prompt = build_audit_prompt(
        before={}, player_input="啰嗦" * 2000, reply="回复" * 2000, declared=[])
    assert prompt.count("啰嗦") <= 800     # 1600 字符上限
    assert prompt.count("回复") <= 1250    # 2500 字符上限


# ── 结果解析：None 与 {} 含义不同 ───────────────────────────────

def test_no_json_means_audit_failed_not_no_change() -> None:
    """
    这条是整个模块最要命的语义。解析不出来 → None → 调用方不结算。
    要是返回 {} ，调用方会以为「审计确认没变化」而放行，
    实际上审计压根没跑成。
    """
    assert parse_audit_result("模型今天不想回答") is None
    assert parse_audit_result("") is None
    assert parse_audit_result('{"loc": 这不是合法 JSON}') is None


def test_empty_object_means_confirmed_no_change() -> None:
    assert parse_audit_result("{}") == {}
    assert parse_audit_result("经过核对，没有变化。\n{}") == {}


def test_out_of_vocabulary_fields_are_dropped() -> None:
    """
    apply_patch 不认识的字段留着只会在调试记录里制造
    「申报了但没生效」的噪音。
    """
    out = parse_audit_result(
        '{"loc":"城南","胡说八道":1,"inv_delta":[{"name":"伤药","delta":-1}]}')
    assert out == {"loc": "城南", "inv_delta": [{"name": "伤药", "delta": -1}]}


def test_json_embedded_in_prose_is_recovered() -> None:
    """模型常会包一层解释文字，这属于常规防御。"""
    assert parse_audit_result(
        '好的，结果如下：\n```json\n{"loc":"城南"}\n```\n以上。') == {"loc": "城南"}


# ── HTTP 契约 ───────────────────────────────────────────────────

def test_prompt_endpoint(client: TestClient) -> None:
    r = client.post("/api/state/audit/prompt", json={
        "before": a_state(), "player_input": "吃药",
        "reply": "你服下伤药。", "declared": []})
    assert r.status_code == 200
    body = r.json()
    assert "确定性状态结算器" in body["prompt"]
    assert body["max_tokens"] > 0
    assert body["temperature"] < 0.5     # 审计要稳定，不要发挥


def test_result_endpoint_distinguishes_failure_from_no_change(client: TestClient) -> None:
    ok = client.post("/api/state/audit/result", json={"raw": "{}"}).json()
    assert ok["ok"] is True and ok["patch"] == {}

    bad = client.post("/api/state/audit/result", json={"raw": "答非所问"}).json()
    assert bad["ok"] is False and bad["patch"] is None


def test_audit_result_feeds_apply_patch(client: TestClient) -> None:
    """审计产出的补丁必须能被结算接口直接吃下——两边字段词表要对齐。"""
    patch = client.post("/api/state/audit/result", json={
        "raw": '{"inv_delta":[{"name":"伤药","delta":-1}],"loc":"城南"}'}).json()["patch"]

    r = client.post("/api/state/apply", json={
        "state": a_state(), "patch": patch, "world_id": "wuxia", "turn": 3})
    assert r.status_code == 200
    new_state = r.json()["state"]
    assert next(x for x in new_state["inv"] if x["name"] == "伤药")["quantity"] == 2
    assert new_state["loc"] == "城南"
