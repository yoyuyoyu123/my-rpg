"""
服务层 · LLM 调用
=================
职责：真正去调外部 API，并处理「外部世界不可靠」这件事。

为什么这些逻辑属于后端而不是前端：
  1. 要用 API key —— 前端拿不到 key
  2. 重试/超时/降级是「系统行为」，不是「界面行为」
  3. 将来要加缓存、限流、成本统计，都在这一层加，前端零改动

分层原则：
  routers（HTTP 层）只管收发和校验，
  services（业务层）管真正干活，
  这样业务逻辑可以脱离 HTTP 单独测试。
"""
import asyncio
import random
from dataclasses import dataclass

import httpx

from app.config import Settings
from app.domain.providers import Provider, get_provider, requires_key


class LLMError(Exception):
    """
    业务异常。带上错误码和「能否重试」，让上层知道该怎么处理。

    这是「让失败可被处理」的关键设计——
    抛一个裸 Exception，上层只能一概而论；带上分类，上层才能分情况应对。
    """

    def __init__(self, code: str, message: str, retryable: bool = False, status: int = 502):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status = status


@dataclass
class LLMResult:
    content: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    retries: int = 0


def _is_retryable_status(status: int) -> bool:
    """
    429 限流、5xx 服务端错误 → 等一下可能就好，值得重试。
    401/403 鉴权失败、404 模型不存在 → 重试多少次都一样，立刻失败。
    """
    return status == 429 or 500 <= status < 600


def _backoff_seconds(attempt: int) -> float:
    """指数退避 + 抖动。抖动是为了避免多个请求在同一刻集体重试。"""
    base = 1.2 * (2 ** attempt)
    return base * (0.75 + random.random() * 0.5)


def _build_payload(req_model: str, messages: list[dict], temperature: float,
                   max_tokens: int, provider: Provider, stream: bool = False) -> dict:
    """组装请求体。Ollama 的参数结构和别家不同，在这里抹平。"""
    if provider.id == "ollama":
        return {
            "model": req_model,
            "messages": messages,
            "stream": stream,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
    return {
        "model": req_model,
        "messages": messages,
        "stream": stream,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }


def _build_headers(provider: Provider, api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json", **provider.extra_headers}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


async def call_chat(
    *,
    settings: Settings,
    provider_id: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.85,
    max_tokens: int = 4096,
) -> LLMResult:
    """
    调用一次对话补全，自动处理限流与瞬时故障。

    抛出 LLMError（带错误码和可重试标记），由路由层翻译成 HTTP 响应。
    """
    provider = get_provider(provider_id)
    if provider is None:
        raise LLMError("unknown_provider", f"未知的后端：{provider_id}", status=400)

    api_key = settings.key_for(provider_id)
    if requires_key(provider_id) and not api_key:
        raise LLMError(
            "provider_not_configured",
            f"服务端没有配置 {provider.label} 的 API Key，请在 .env 里填写",
            status=503,
        )

    use_model = (model or "").strip() or provider.default_model
    payload = _build_payload(use_model, messages, temperature, max_tokens, provider)
    headers = _build_headers(provider, api_key)

    last_error: LLMError | None = None

    async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
        for attempt in range(settings.max_retries):
            try:
                resp = await client.post(provider.chat_url, json=payload, headers=headers)
            except httpx.TimeoutException:
                last_error = LLMError("timeout", "调用后端超时", retryable=True, status=504)
            except httpx.HTTPError as exc:
                last_error = LLMError("network_error", f"网络错误：{exc}", retryable=True, status=502)
            else:
                if resp.status_code == 200:
                    return _parse_success(resp.json(), provider_id, use_model, attempt)

                body = resp.text[:300]
                retryable = _is_retryable_status(resp.status_code)
                code = "rate_limited" if resp.status_code == 429 else (
                    "upstream_error" if retryable else "upstream_rejected"
                )
                last_error = LLMError(
                    code,
                    f"后端返回 HTTP {resp.status_code}：{body}",
                    retryable=retryable,
                    status=429 if resp.status_code == 429 else 502,
                )
                if not retryable:
                    raise last_error

            # 走到这里说明这次失败且可重试
            if attempt < settings.max_retries - 1:
                await asyncio.sleep(_backoff_seconds(attempt))

    assert last_error is not None
    raise last_error


def _parse_success(data: dict, provider_id: str, model: str, attempt: int) -> LLMResult:
    """
    解析成功响应。

    各家都号称兼容 OpenAI 格式，但字段偶有差异，
    所以这里全部用 .get() 兜底，避免因为少一个字段就整个崩掉。
    """
    if data.get("error"):
        err = data["error"]
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise LLMError("upstream_rejected", f"后端返回错误：{msg}", status=502)

    choices = data.get("choices") or []
    if not choices:
        raise LLMError("empty_response", "后端没有返回任何内容", retryable=True, status=502)

    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    if not content.strip():
        raise LLMError("empty_response", "后端返回了空内容", retryable=True, status=502)

    usage = data.get("usage") or {}
    return LLMResult(
        content=content,
        provider=provider_id,
        model=model,
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        total_tokens=int(usage.get("total_tokens") or 0),
        retries=attempt,
    )
