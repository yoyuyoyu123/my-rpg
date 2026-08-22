"""
GM 裁定测试
===========
裁判和写手的分工是刻意的：裁判只判定、玩家看不到它的输出；写手只按判定叙事、
不得改判。合在一起做的话，模型会一边编故事一边为故事的需要放宽判定——
「为了戏剧性」是最常见的失控来源。

这组测试锁两类东西：题目里必须出现哪些约束，以及结果解析的边界。
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402
from app.services.director import (  # noqa: E402
    build_director_prompt, parse_ruling, strip_blocks,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def a_state(**kw) -> dict:
    base = {
        "revealed": True,
        "attrs": {"力量": 5, "身法": 3},
        "res": {"体力": 80},
        "talents": ["过目不忘"],
        "skills": [{"name": "太祖长拳", "realm": "小成", "proficiency": 62,
                    "coefficient": 1.5, "active": False}],
        "npcs": {"吴四娘": {"rel": "邻居", "att": 2, "knows": ["主角会拳脚"]}},
    }
    base.update(kw)
    return base


def prompt(**kw) -> str:
    args = {"player_input": "看看四周", "game_state": a_state()}
    args.update(kw)
    return build_director_prompt(**args)


# ── 题目里必须有的约束 ──────────────────────────────────────────

def test_check_threshold_is_strict() -> None:
    """
    模型天然倾向于「为了戏剧性」掷骰。每一次不必要的检定都在把日常变成闯关，
    所以门槛必须写死在题目里，而不是指望模型自觉。
    """
    p = prompt()
    assert "不要为了制造戏剧而检定" in p
    assert "普通走路、观察可见物、正常交谈" in p
    assert "角色卡未揭示时risky必须为false" in p


def test_authority_boundary_is_stated() -> None:
    """裁定的首要职责是划边界：玩家说了什么，就只授权什么。"""
    p = prompt()
    assert "只把玩家明确说出的动作" in p
    assert "scene_note必须写明本回合在哪里停下" in p


def test_npc_knowledge_boundary_is_stated() -> None:
    """NPC 不能用它「已知」列表之外的秘密——这是同一套规则的第二处出口。"""
    p = prompt()
    assert "不得使用其“已知”列表之外的主角秘密" in p
    assert "陌生言行不能直接推导穿越身份" in p


def test_refusing_hooks_must_be_respected() -> None:
    """玩家拒绝钩子后不许换皮重发——这是这个项目最早要解决的问题之一。"""
    assert "禁止设计换皮事件把玩家强拉回原路线" in prompt()


# ── 状态渲染 ────────────────────────────────────────────────────

def test_state_is_rendered_for_judgement() -> None:
    p = prompt()
    assert "力量=5,身法=3" in p
    assert "太祖长拳(小成,熟练62%,系数1.5)" in p
    assert "吴四娘(邻居,态度2,已知=主角会拳脚)" in p


def test_empty_state_has_readable_placeholders() -> None:
    """空局也要能出题，占位文案不能是空白——空白会让模型自己编。"""
    p = build_director_prompt(player_input="我是谁", game_state={})
    assert "未知（可自定合理属性名）" in p
    assert "角色技能:无" in p and "角色天赋:无" in p
    assert "人物关系与各自知情:无" in p


def test_only_recent_npcs_are_listed() -> None:
    """人物多了只带最近的，否则这一段会把题目撑爆。"""
    npcs = {f"人物{i}": {"rel": "邻居", "att": 0, "knows": []} for i in range(20)}
    p = prompt(game_state=a_state(npcs=npcs))
    assert "人物19" in p and "人物0(" not in p


def test_hidden_blocks_are_stripped_from_recent_history() -> None:
    """裁判要看的是剧情，不是模型的申报。"""
    p = prompt(recent_messages=[
        {"role": "assistant",
         "content": '你推开门。\n【STATE】{"loc":"铁匠铺"}【/STATE】\n【大纲】备忘【/大纲】'}])
    assert "你推开门。" in p
    assert "铁匠铺" not in p and "备忘" not in p


def test_strip_blocks_leaves_unclosed_block_alone() -> None:
    assert "正文" in strip_blocks('正文\n【STATE】{"loc":"半截')


# ── 结果解析 ────────────────────────────────────────────────────

def test_parse_returns_none_when_unusable() -> None:
    """
    裁定失败返回 None，调用方按「本回合不做额外裁定」处理——
    那只是少一层约束，不会让状态出错，所以不必当成硬故障。
    """
    assert parse_ruling("模型今天不想回答") is None
    assert parse_ruling("") is None
    assert parse_ruling("[1,2,3]") is None


def test_parse_recovers_json_from_prose() -> None:
    r = parse_ruling('好的：\n```json\n{"risky":true,"dc":70}\n```')
    assert r == {"risky": True, "dc": 70}


def test_parse_does_not_tighten_values() -> None:
    """
    这里刻意只解析、不收紧。取值收紧目前在前端的回合编排里，规则和直觉不同
    （属性名无效时回退到第一个属性，而不是丢弃）。迁移期间顺手改行为会让
    「搬完行为没变」失去意义，也就没法用对拍验证。
    """
    r = parse_ruling('{"attr":"根本没有这个属性","dc":9999,"beat":"胡说"}')
    assert r["attr"] == "根本没有这个属性"
    assert r["dc"] == 9999


# ── HTTP 契约 ───────────────────────────────────────────────────

def test_prompt_endpoint(client: TestClient) -> None:
    r = client.post("/api/director/prompt", json={
        "player_input": "攻击那个人", "game_state": a_state()})
    assert r.status_code == 200
    body = r.json()
    assert "后台GM裁判" in body["prompt"]
    assert body["temperature"] < 0.5      # 裁定要稳定
    assert body["max_tokens"] > 0


def test_result_endpoint_reports_failure(client: TestClient) -> None:
    ok = client.post("/api/director/result", json={"raw": '{"risky":false}'}).json()
    assert ok["ok"] is True and ok["ruling"] == {"risky": False}

    bad = client.post("/api/director/result", json={"raw": "答非所问"}).json()
    assert bad["ok"] is False and bad["ruling"] is None


def test_prompt_requires_player_input(client: TestClient) -> None:
    assert client.post("/api/director/prompt", json={}).status_code == 422
