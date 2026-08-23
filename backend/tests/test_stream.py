"""
流式转发测试
============
流式的价值是玩家不用盯着转圈等一整段叙事，但它也是最容易出错的一条路：
分帧、结束标记、以及「什么时候还能重试」都有讲究。这里把契约锁住。
"""
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings, get_settings  # noqa: E402
from app.domain.providers import PROVIDERS  # noqa: E402
from app.main import app  # noqa: E402
from app.services.llm import LLMError, _build_payload, _parse_success, call_chat  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ── 请求体组装 ──────────────────────────────────────────────────

def test_ollama_uses_openai_field_names() -> None:
    """
    我们打的是 Ollama 的 /v1/ 兼容端点，它只认 max_tokens。
    以前按原生 API 的 options/num_predict 发，输出长度上限被静默忽略。
    """
    payload = _build_payload("m", [], 0.8, 512, PROVIDERS["ollama"])
    assert payload["max_tokens"] == 512
    assert "options" not in payload


def test_stream_options_only_where_supported() -> None:
    """流式默认不回 token 用量，要显式索取——但不是每家都认这个字段。"""
    ds = _build_payload("m", [], 0.8, 512, PROVIDERS["deepseek"], stream=True)
    assert ds["stream_options"] == {"include_usage": True}

    zp = _build_payload("m", [], 0.8, 512, PROVIDERS["zhipu"], stream=True)
    assert "stream_options" not in zp

    ds_disabled = _build_payload(
        "m", [], 0.8, 512, PROVIDERS["deepseek"], stream=True,
        thinking="disabled",
    )
    assert ds_disabled["thinking"] == {"type": "disabled"}

    ds_enabled = _build_payload(
        "m", [], 0.8, 512, PROVIDERS["deepseek"], stream=True,
        thinking="enabled",
    )
    assert ds_enabled["thinking"] == {"type": "enabled"}
    assert "thinking" not in _build_payload(
        "m", [], 0.8, 512, PROVIDERS["zhipu"], stream=True,
        thinking="enabled",
    )


def test_stream_options_absent_when_not_streaming() -> None:
    assert "stream_options" not in _build_payload(
        "m", [], 0.8, 512, PROVIDERS["deepseek"], stream=False
    )


def test_non_stream_reasoning_is_preserved_for_monitor() -> None:
    result = _parse_success({
        "choices": [{"message": {"content": "最终答案", "reasoning_content": "内部推理"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }, "deepseek", "deepseek-v4-flash", 0)
    assert result.content == "最终答案"
    assert result.reasoning_content == "内部推理"
    assert result.total_tokens == 30


# ── 连接阶段的失败必须是普通 HTTP 错误 ──────────────────────────
# 一旦开始流式输出，状态码就发出去了改不了；所以这些必须在连接前就拦下。

def test_stream_unknown_provider_is_400(client: TestClient) -> None:
    r = client.post("/api/chat/stream", json={
        "messages": [{"role": "user", "content": "hi"}], "provider": "nope"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "unknown_provider"
    assert r.headers["content-type"].startswith("application/json")


def test_stream_missing_key_is_503(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(deepseek_api_key="")
    try:
        r = client.post("/api/chat/stream", json={
            "messages": [{"role": "user", "content": "hi"}], "provider": "deepseek"})
        assert r.status_code == 503
        assert r.json()["detail"]["code"] == "provider_not_configured"
    finally:
        app.dependency_overrides.clear()


def test_stream_validates_body_like_non_stream(client: TestClient) -> None:
    """流式和非流式共用同一个请求契约，校验不能松。"""
    assert client.post("/api/chat/stream", json={
        "messages": [], "provider": "deepseek"}).status_code == 422
    assert client.post("/api/chat/stream", json={
        "messages": [{"role": "user", "content": "hi"}], "temperature": 99}).status_code == 422


# ── 上游返回 200 但内容不是 JSON ────────────────────────────────

@pytest.mark.asyncio
async def test_non_json_200_becomes_structured_error(monkeypatch) -> None:
    """
    上游返回 HTML 错误页、网关插了东西、端点配错——都会是「200 但不是 JSON」。
    这种情况必须变成带错误码的 502，而不是冒成 500：
    前端只看到「服务器错误」时无从判断该重试还是该改配置。
    """
    async def fake_post(self, url, **kw):
        return httpx.Response(200, text="<html>502 Bad Gateway</html>",
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    with pytest.raises(LLMError) as exc:
        await call_chat(
            settings=Settings(deepseek_api_key="test-key"),
            provider_id="deepseek", model="m",
            messages=[{"role": "user", "content": "hi"}],
        )
    assert exc.value.code == "malformed_response"
    assert exc.value.status == 502
