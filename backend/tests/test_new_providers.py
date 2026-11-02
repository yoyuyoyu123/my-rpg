from app.config import Settings
from app.domain.providers import PROVIDERS
from app.schemas.config import ConfigUpdate
from app.services.llm import _build_payload


def test_gemini_uses_official_compatible_endpoint_without_deepseek_fields():
    provider = PROVIDERS["gemini"]
    assert provider.chat_url == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    payload = _build_payload(provider.default_model, [], .85, 4096, provider, stream=True, thinking="enabled")
    assert payload["max_tokens"] == 4096
    assert "thinking" not in payload and "stream_options" not in payload


def test_luna_uses_completion_budget_and_supported_sampling_mode():
    provider = PROVIDERS["openai"]
    payload = _build_payload("gpt-6-luna", [], .85, 4096, provider, sampling={"top_p": .9})
    assert payload["max_completion_tokens"] == 4096 and "max_tokens" not in payload
    assert payload["reasoning_effort"] == "none" and payload["temperature"] == .85
    assert payload["store"] is False
    assert payload["top_p"] == .9


def test_reasoning_openai_model_does_not_receive_incompatible_sampling():
    payload = _build_payload("gpt-6-astra", [], .85, 4096, PROVIDERS["openai"], sampling={"top_p": .9})
    assert "temperature" not in payload and "top_p" not in payload
    assert payload["reasoning_effort"] == "low"


def test_keys_configure_independently_and_remain_optional():
    settings = Settings(gemini_api_key="fixture-google", openai_api_key="fixture-openai")
    assert settings.key_for("gemini") == "fixture-google"
    assert settings.key_for("openai") == "fixture-openai"
    assert ConfigUpdate(default_provider="gemini").default_provider == "gemini"
    assert ConfigUpdate(default_provider="openai").default_provider == "openai"
