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
