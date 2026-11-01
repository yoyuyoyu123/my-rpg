"""Fixed RPG fixtures test contracts and failures; they do NOT prove prose quality."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import app
from app.schemas.novel import DraftReview, EventNode, NovelRequest, NovelRuntime
from app.services import novel_engine as engine
from app.services.llm import LLMError, LLMResult, _parse_success
from app.services.novel_math import choose_event, choose_styles, recall, select_review, style_mean


def node(id="a", **kwargs):
    return EventNode(id=id, **{"development": "掌柜把茶碗推近一点。", "evidence": ["掌柜正在擦桌"], **kwargs})


def request(**kwargs):
    return NovelRequest.model_validate({
        "provider": "ollama", "model": "fixture", "max_tokens": 1024,
        "messages": [{"role": "system", "content": "遵从GM与玩家授权，返回游戏正文和行动选项。"},
                     {"role": "assistant", "content": "掌柜正在擦桌。你还没告诉他那封密信。"},
                     {"role": "user", "content": "我放下茶钱，问他昨晚的客人。"}],
        "context": {"world_id": "wuxia", "turns": 3,
                    "story_runtime": {"current_scene": {"id": "teahouse", "narration": "scene"}}},
        "runtime": {"scene_id": "teahouse", "scene_age": 2}, **kwargs,
    })


def review(id=0, **kwargs):
    values = dict(id=id, agency_ok=True, facts_ok=True, knowledge_ok=True,
                  causal=.8, character=.8, prose=.8, pacing=.8)
    values.update(kwargs)
    return DraftReview(**values)


@pytest.mark.parametrize("nodes", [
    [node(parent="missing")], [node(parent="b"), node("b", parent="a")],
    [node(), node()], [node(actor="玩家")],
    [EventNode(id="fake", development="秘密组织闯入。", evidence=["从未发生的事"])],
    [node(perceived=["NPC并不知情的秘密"])],
])
def test_unsupported_graphs_cannot_direct_game(nodes):
    selected, trace = choose_event(nodes, "掌柜正在擦桌")
    assert selected is None
    assert trace["rejected"]


def test_lookahead_selects_first_step_and_never_executes_future():
    first, trace = choose_event([node(), node("future", parent="a", causal=1)], "掌柜正在擦桌")
    assert first.id == "a"
    assert trace["path"] == ["a", "future"]


def test_world_truth_cannot_be_used_as_uninformed_npc_knowledge():
    nodes = [node(actor="掌柜", perceived=["密信藏在包里"])]
    world = "掌柜正在擦桌。密信藏在包里。"
    assert choose_event(nodes, world, {"掌柜": []})[0] is None
    assert choose_event(nodes, world, {"掌柜": ["玩家已告诉他：密信藏在包里"]})[0] is not None


def test_unknown_actor_cannot_drive_an_unestablished_plot():
    assert choose_event([node(actor="陌生幕后组织")], "掌柜正在擦桌", {"掌柜": []})[0] is None


def test_memory_keeps_original_prose_within_budget():
    runtime = NovelRuntime(excerpts=[
        {"turn": 1, "text": "掌柜擦桌时总会避开那道刀痕。"},
        {"turn": 2, "text": "山路积雪，车轮陷进泥里。"},
        {"turn": 3, "text": "掌柜擦桌时总会避开那道刀痕。"},
    ])
    result = recall(runtime, "掌柜桌上的刀痕", budget=20)
    assert sum(len(e["text"]) for e in result) <= 20
    assert result[0]["text"] == runtime.excerpts[0].text
    assert all(e["turn"] != 2 for e in result)


def test_preferences_are_explicit_and_do_not_update_from_model_scores():
    runtime = NovelRuntime(preferences={"dialogue": {"likes": 8, "dislikes": 0}})
    before = runtime.model_dump()
    assert style_mean(runtime, "dialogue") == .9
    assert "dialogue" in choose_styles(runtime, 2, 1)
    select_review([review()], {0: "dialogue"}, runtime)
    assert runtime.model_dump() == before


def test_safety_precedes_all_quality_and_preference_scores():
    selected = select_review([review(0, agency_ok=False, prose=1), review(1, prose=.2)],
                             {0: "lyrical", 1: "grounded"}, NovelRuntime())
    assert selected.id == 1
    assert select_review([review(knowledge_ok=False)], {0: "grounded"}, NovelRuntime()) is None
    with pytest.raises(ValidationError):
        DraftReview(id=0, prose=1)


def install_fake(monkeypatch, *, judge="ok", writer="ok", edit=False, plan="ok"):
    seen = []
    async def call(**kwargs):
        messages = kwargs["messages"]
        last = messages[-1]["content"]
        seen.append(messages)
        if last == engine.PLAN_PROMPT:
            if plan == "bad":
                text = "not-json"
            else:
                text = json.dumps({"nodes": [node().model_dump(), node("unwritten_future", parent="a", development="未来专有暗号NEVER_CANON").model_dump()]}, ensure_ascii=False)
        elif last.startswith("【本回合写法】"):
            assert "NEVER_CANON" not in json.dumps(messages, ensure_ascii=False)
            text = "掌柜停下擦桌的手，往窗边看了一眼。\n1. 继续询问\n2. 安静等候\n或自由输入"
            if writer == "all_truncated" or (writer == "partial" and "潜台词" in last):
                return LLMResult(text, "", "ollama", "fixture", finish_reason="length")
        elif last.startswith("只按以下校读意见"):
            text = "掌柜收好茶钱，向窗边扬了扬下巴。\n1. 望向窗边\n2. 继续询问\n或自由输入"
        else:
            assert messages[-2]["content"] == engine.REVIEW_PROMPT
            if judge == "error":
                raise LLMError("offline", "test")
            drafts = json.loads(last)["drafts"]
            rows = [review(int(i), knowledge_ok=judge != "leak", agency_ok=judge != "agency",
                           edit="压缩重复的动作。" if edit else "").model_dump() for i in drafts]
            if judge == "missing":
                rows = rows[:1] if len(rows) > 1 else []
            text = json.dumps({"reviews": rows}, ensure_ascii=False)
        return LLMResult(text, "", "ollama", "fixture", prompt_tokens=5, completion_tokens=5, total_tokens=10)
    monkeypatch.setattr(engine, "call_chat", call)
    return seen


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", [{}, {"mode": "balanced"}])
async def test_complete_rpg_turn_uses_scene_age_and_keeps_runtime_unmodified(monkeypatch, kwargs):
    seen = install_fake(monkeypatch)
    req = request(**kwargs)
    before = req.model_dump()
    stages = []
    result = await engine.generate_turn(req, Settings(), lambda stage: append(stages, stage))
    assert req.model_dump() == before
    assert result["meta"]["scene_age"] == 3
    assert result["meta"]["candidate_count"] == (1 if kwargs else 2)
    assert "1. " in result["content"]
    assert "NEVER_CANON" not in json.dumps(result, ensure_ascii=False)
    assert result["usage"]["total_tokens"] == 10 * len(seen)


async def append(values, value):
    values.append(value)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["leak", "agency"])
async def test_explicit_rejection_aborts_instead_of_silent_fallback(monkeypatch, kind):
    install_fake(monkeypatch, judge=kind)
    with pytest.raises(LLMError, match="候选均未通过"):
        await engine.generate_turn(request(), Settings(), lambda stage: asyncio.sleep(0))


@pytest.mark.asyncio
@pytest.mark.parametrize("options", [{"judge": "error"}, {"judge": "missing"}, {"plan": "bad"}, {"writer": "partial"}])
async def test_optional_failures_are_visible_and_keep_complete_game_turn(monkeypatch, options):
    install_fake(monkeypatch, **options)
    result = await engine.generate_turn(request(), Settings(), lambda stage: asyncio.sleep(0))
    assert result["content"]
    assert result["meta"]["status"] == "degraded"
    assert result["meta"]["warnings"]


@pytest.mark.asyncio
async def test_no_truncated_candidate_can_be_committed(monkeypatch):
    install_fake(monkeypatch, writer="all_truncated")
    with pytest.raises(LLMError, match="候选未完整生成"):
        await engine.generate_turn(request(), Settings(), lambda stage: asyncio.sleep(0))


@pytest.mark.asyncio
async def test_edit_is_rechecked_with_total_budget(monkeypatch):
    seen = install_fake(monkeypatch, edit=True)
    result = await engine.generate_turn(request(), Settings(), lambda stage: asyncio.sleep(0))
    assert result["meta"]["edited"]
    assert "收好茶钱" in result["content"]
    assert len(seen) == 6


def test_sse_contract_contains_progress_meta_usage_and_completed_turn(monkeypatch):
    install_fake(monkeypatch)
    with TestClient(app) as client:
        response = client.post("/api/novel/turn/stream", json=request().model_dump())
    assert response.status_code == 200
    assert "novel_stage" in response.text
    assert "novel_meta" in response.text
    assert "finish_reason" in response.text
    assert response.text.endswith("data: [DONE]\n\n")


def test_provider_truncation_is_preserved_for_quality_gate():
    parsed = _parse_success({"choices": [{"message": {"content": "半截"}, "finish_reason": "length"}]}, "ollama", "fixture", 0)
    assert parsed.finish_reason == "length"


@pytest.mark.asyncio
async def test_disconnecting_stream_cancels_upstream_work(monkeypatch):
    from app.routers.novel import novel_turn
    started, cancelled = asyncio.Event(), asyncio.Event()
    async def blocked_call(**kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    monkeypatch.setattr(engine, "call_chat", blocked_call)
    response = await novel_turn(request(), Settings())
    iterator = response.body_iterator
    assert "novel_stage" in await anext(iterator)
    await asyncio.wait_for(started.wait(), 1)
    await iterator.aclose()
    assert cancelled.is_set()


def test_rejected_turn_stream_has_no_content_or_completion_marker(monkeypatch):
    install_fake(monkeypatch, judge="agency")
    with TestClient(app) as client:
        response = client.post("/api/novel/turn/stream", json=request().model_dump())
    assert '"code": "drafts_rejected"' in response.text
    assert '"content"' not in response.text
    assert "[DONE]" not in response.text
