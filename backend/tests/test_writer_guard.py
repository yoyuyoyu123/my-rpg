"""
写手后处理测试
==============
两道补救题：模型替玩家做了决定时要求重写，正文没给行动参考时补一组。
它们是「模型没按契约交货」的兜底，不是常规流程。
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402
from app.services.writer_guard import (  # noqa: E402
    build_agency_guard, build_option_repair, strip_hidden_blocks,
)
from app.services.writer_output import normalize_writer_output  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ── 主权纠错 ────────────────────────────────────────────────────

def test_guard_lists_the_violations() -> None:
    g = build_agency_guard(["UNAUTHORIZED_CHOICE", "UNAUTHORIZED_COMMUNICATION"])
    assert "UNAUTHORIZED_CHOICE、UNAUTHORIZED_COMMUNICATION" in g


def test_guard_forbids_mentioning_itself() -> None:
    """玩家不该知道有这么一次纠错——那会打破叙事。"""
    assert "不得在正文提及纠错、上一稿或系统" in build_agency_guard([])


def test_guard_still_demands_options() -> None:
    """重写不能把行动参考弄丢，否则玩家这一回合无从下手。"""
    assert "仍需提供2-4个眼前行动参考和自由输入" in build_agency_guard([])


def test_guard_keeps_world_reaction() -> None:
    """
    纠错要删的是「替玩家行动」，不是整段重来。
    世界对玩家输入的反馈是合法内容，删掉就成了无事发生。
    """
    assert "保留世界对玩家输入的直接反馈与必要环境变化" in build_agency_guard([])


# ── 选项补全 ────────────────────────────────────────────────────

def test_option_prompt_requires_a_low_commitment_choice() -> None:
    """
    选项全是推进剧情的动作，等于把「什么也不做」这个合法选择从桌上拿走了。
    这个项目从一开始要解决的就是「玩家被推着走」。
    """
    p = build_option_repair(draft="雨停了。", player_input="看看")
    assert "至少包含一个低承诺或暂不推进的选择" in p


def test_option_prompt_forbids_inventing_content() -> None:
    """补选项是从已发生的场景里提取，不是接着编。"""
    p = build_option_repair(draft="雨停了。", player_input="看看")
    assert "不得新增人物、地点、物品、秘密、任务或尚未出现的信息" in p
    assert "不写或改动小说正文" in p


def test_option_prompt_strips_hidden_blocks() -> None:
    p = build_option_repair(
        draft='雨停了。\n【STATE】{"loc":"铁匠铺"}【/STATE】\n【大纲】备忘【/大纲】\n你推门。',
        player_input="进去")
    assert "雨停了。" in p and "你推门。" in p
    assert "铁匠铺" not in p and "备忘" not in p


def test_only_the_tail_of_a_long_draft_is_used() -> None:
    """选项针对的是「此刻」，几千字之前的场景已经不相关了。"""
    p = build_option_repair(draft="开头标记" + "正文。" * 3000, player_input="x")
    assert "开头标记" not in p


def test_player_input_is_capped() -> None:
    p = build_option_repair(draft="短", player_input="啰嗦" * 2000)
    assert p.count("啰嗦") <= 600


def test_strip_hidden_blocks_handles_unclosed() -> None:
    assert "正文" in strip_hidden_blocks('正文\n【STATE】{"loc":"半截')


# ── HTTP 契约 ───────────────────────────────────────────────────

def test_endpoints(client: TestClient) -> None:
    g = client.post("/api/writer/agency-guard", json={"codes": ["X"]})
    assert g.status_code == 200
    assert "玩家主权纠错" in g.json()["guard"]

    o = client.post("/api/writer/option-repair",
                    json={"draft": "雨停了。", "player_input": "看看"})
    assert o.status_code == 200
    body = o.json()
    assert "行动选项编辑器" in body["prompt"]
    assert body["temperature"] < 0.5      # 提取要稳定，不要发挥
    assert body["max_tokens"] > 0


def test_option_repair_requires_draft(client: TestClient) -> None:
    assert client.post("/api/writer/option-repair", json={}).status_code == 422


# ── 结构化写手信封（兼容切片） ──────────────────────────────────

def test_structured_writer_output_normalizes_json_and_caps_options() -> None:
    result = normalize_writer_output(
        '```json\n{"narrative":"  门开了。 ","options":["进去","进去","观察","询问","多余"],'
        '"state_patch":{"loc":"门口"}}\n```'
    )
    assert result is not None
    assert result.narrative == "门开了。"
    assert result.options == ["进去", "观察", "询问", "多余"]
    assert result.state_patch == {"loc": "门口"}


def test_plain_text_and_non_writer_json_fall_back() -> None:
    assert normalize_writer_output("雨停了。") is None
    assert normalize_writer_output('{"narrative":"资料","items":[]}') is None


def test_structured_writer_normalize_endpoint_is_non_destructive(client: TestClient) -> None:
    response = client.post(
        "/api/writer/normalize",
        json={"raw": '{"narrative":"门开了","options":["进去","离开"]}'},
    )
    assert response.status_code == 200
    assert response.json()["structured"] is True
    assert response.json()["options"] == ["进去", "离开"]

    fallback = client.post("/api/writer/normalize", json={"raw": "普通正文"})
    assert fallback.status_code == 200
    assert fallback.json() == {
        "structured": False,
        "narrative": "",
        "options": [],
        "state_patch": {},
        "memory_writes": [],
    }
