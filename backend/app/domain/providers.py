"""
领域层 · LLM 后端目录
=====================
职责：描述「有哪些可用的 LLM 后端，各自怎么调」。

为什么单独一层：
  各家 API 长得像但不一样——路径不同（智谱是 /api/paas/v4/，别家是 /v1/）、
  有的要额外请求头。把这些差异集中在一个地方，
  上层代码就可以统一按「provider 名字」调用，不用到处写 if。

这是「防腐层」的思路：外部系统的不一致性挡在这里，不渗透进业务逻辑。
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Provider:
    """一个 LLM 后端的调用参数。frozen=True 表示不可变，避免运行时被误改。"""

    id: str
    label: str
    base_url: str
    chat_path: str = "/v1/chat/completions"
    models_path: str = "/v1/models"
    default_model: str = ""
    # 某些平台要求额外请求头（如 OpenRouter 要 Referer）
    extra_headers: dict[str, str] = field(default_factory=dict)
    note: str = ""

    @property
    def chat_url(self) -> str:
        return self.base_url.rstrip("/") + self.chat_path

    @property
    def models_url(self) -> str:
        return self.base_url.rstrip("/") + self.models_path


# 注册表：新增一个后端只要在这里加一条，上层代码零改动。
PROVIDERS: dict[str, Provider] = {
    "deepseek": Provider(
        id="deepseek",
        label="DeepSeek",
        base_url="https://api.deepseek.com",
        default_model="deepseek-v4-flash",
        note="峰谷定价，工作日 9-12 与 14-18 为峰时",
    ),
    "zhipu": Provider(
        id="zhipu",
        label="智谱 GLM",
        base_url="https://open.bigmodel.cn",
        # 智谱不用标准的 /v1/ —— 这正是要有这一层的原因
        chat_path="/api/paas/v4/chat/completions",
        models_path="/api/paas/v4/models",
        default_model="glm-4.7-flash",
        note="Flash 系列免费，但免费池限流较重",
    ),
    "siliconflow": Provider(
        id="siliconflow",
        label="硅基流动",
        base_url="https://api.siliconflow.cn",
        default_model="deepseek-ai/DeepSeek-V3",
        note="聚合平台，注册赠送额度",
    ),
    "openrouter": Provider(
        id="openrouter",
        label="OpenRouter",
        base_url="https://openrouter.ai/api",
        default_model="deepseek/deepseek-chat",
        extra_headers={"HTTP-Referer": "http://localhost", "X-Title": "WujiNarrativeEngine"},
        note="一个 key 转发多家模型",
    ),
    "ollama": Provider(
        id="ollama",
        label="本地 Ollama",
        base_url="http://127.0.0.1:11434",
        models_path="/api/tags",
        default_model="qwen2.5:14b",
        note="本地模型，不需要 key",
    ),
}


def get_provider(provider_id: str) -> Provider | None:
    return PROVIDERS.get(provider_id)


def requires_key(provider_id: str) -> bool:
    """本地 Ollama 不需要 key，其余都需要。"""
    return provider_id != "ollama"
