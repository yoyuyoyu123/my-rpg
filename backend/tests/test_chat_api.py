"""
后端测试
========
跑法（backend 目录下）：
    .venv/Scripts/python.exe -m pytest tests/ -v

为什么要写测试：
  这些行为（错误码、状态码、重试判断）是前端依赖的契约。
  以后重构服务层时，测试会告诉你有没有把契约改坏。
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings, get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.services.llm import _backoff_seconds, _is_retryable_status  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ── 基础端点 ────────────────────────────────────────────────────

def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["product"] == "wuji-rpg"


def test_providers_lists_all(client: TestClient) -> None:
    r = client.get("/api/providers")
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()}
    assert {"deepseek", "zhipu", "siliconflow", "openrouter", "ollama"} <= ids


def test_providers_never_leaks_keys(client: TestClient) -> None:
    """最重要的一条：这个接口绝不能把 key 本身发给前端。"""
    body = client.get("/api/providers").text
    assert "api_key" not in body.lower()
    assert "sk-" not in body


def test_ollama_needs_no_key(client: TestClient) -> None:
    """本地 Ollama 不需要 key，应该始终显示为已配置。"""
    ollama = next(p for p in client.get("/api/providers").json() if p["id"] == "ollama")
    assert ollama["configured"] is True


# ── 契约校验（Pydantic 自动完成，我们只验证它确实生效）──────────

def test_empty_messages_rejected(client: TestClient) -> None:
    r = client.post("/api/chat", json={"messages": [], "provider": "deepseek"})
    assert r.status_code == 422


def test_bad_role_rejected(client: TestClient) -> None:
    r = client.post("/api/chat", json={
        "messages": [{"role": "wizard", "content": "hi"}], "provider": "deepseek"})
    assert r.status_code == 422


def test_temperature_out_of_range_rejected(client: TestClient) -> None:
    """防止前端传出离谱参数把账单打爆。"""
    r = client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "hi"}], "temperature": 99})
    assert r.status_code == 422


# ── 错误处理 ────────────────────────────────────────────────────

def test_unknown_provider(client: TestClient) -> None:
    r = client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "hi"}], "provider": "nope"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "unknown_provider"


def test_unconfigured_provider_returns_503(client: TestClient) -> None:
    """没配 key 时要明确告诉前端「是服务端没配好」，而不是含糊报错。"""
    app.dependency_overrides[get_settings] = lambda: Settings(deepseek_api_key="")
    try:
        r = client.post("/api/chat", json={
            "messages": [{"role": "user", "content": "hi"}], "provider": "deepseek"})
        assert r.status_code == 503
        assert r.json()["detail"]["code"] == "provider_not_configured"
        assert r.json()["detail"]["retryable"] is False
    finally:
        app.dependency_overrides.clear()


# ── 重试策略（纯函数，可直接测）──────────────────────────────────

@pytest.mark.parametrize("status,expected", [
    (429, True),    # 限流 → 等一下可能就好
    (500, True), (502, True), (503, True),
    (401, False),   # 鉴权失败 → 重试无意义
    (403, False), (404, False), (400, False),
])
def test_retryable_classification(status: int, expected: bool) -> None:
    assert _is_retryable_status(status) is expected


def test_backoff_grows_and_jitters() -> None:
    """退避要递增（避免连续冲击），且带抖动（避免集体同时重试）。"""
    first = [_backoff_seconds(0) for _ in range(20)]
    second = [_backoff_seconds(1) for _ in range(20)]
    assert min(second) > min(first)          # 递增
    assert len(set(first)) > 1               # 有抖动，不是固定值


# ── 采样参数按 provider 能力分发 ────────────────────────────────
#
# 不能统一加：llm.py 里那条 thinking 的注释已经写过教训——兼容 OpenAI 的
# 后端收到未知字段可能直接拒绝请求。而且差异是实的：DeepSeek 把
# frequency_penalty 标为弃用（官方明写「传了也不生效」），硅基流动支持。

def _payload(provider_id: str, **sampling):
    from app.domain.providers import get_provider
    from app.services.llm import _build_payload
    return _build_payload("m", [{"role": "user", "content": "x"}], 0.85, 100,
                          get_provider(provider_id), sampling=sampling)


def test_deepseek_never_receives_frequency_penalty() -> None:
    """
    传了不生效还占字段。真正的风险是它给人「已经治了重复」的错觉——
    我们为这个毛病改过三轮提示词。
    """
    p = _payload("deepseek", frequency_penalty=0.6, top_p=0.9)
    assert "frequency_penalty" not in p
    assert p["top_p"] == 0.9


def test_siliconflow_receives_the_verified_params() -> None:
    p = _payload("siliconflow", frequency_penalty=0.6, top_k=40, min_p=0.05)
    assert p["frequency_penalty"] == 0.6
    assert p["top_k"] == 40 and p["min_p"] == 0.05


def test_unverified_providers_get_the_minimal_safe_set() -> None:
    """没查过文档的几家只发通用字段，不照抄别家的能力表。"""
    p = _payload("zhipu", frequency_penalty=0.6, top_k=40, top_p=0.9)
    assert "frequency_penalty" not in p and "top_k" not in p
    assert p["top_p"] == 0.9


def test_absent_params_are_not_sent_as_defaults() -> None:
    """
    留空表示不发送，不是「发一个我们以为的默认值」——各家默认值不一定
    相同，显式发反而改变行为。
    """
    from app.schemas.chat import ChatRequest
    req = ChatRequest(messages=[{"role": "user", "content": "x"}])
    assert req.sampling() == {}
    p = _payload("siliconflow")
    for key in ("top_p", "top_k", "frequency_penalty", "min_p"):
        assert key not in p


def test_out_of_range_sampling_is_rejected() -> None:
    import pytest as _pytest
    from pydantic import ValidationError
    from app.schemas.chat import ChatRequest
    with _pytest.raises(ValidationError):
        ChatRequest(messages=[{"role": "user", "content": "x"}], frequency_penalty=9.0)
