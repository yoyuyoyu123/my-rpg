"""
配置层
======
职责：把「会变的东西」从代码里赶出去。

为什么需要这一层：
  API key、端口、允许的前端地址——这些在开发机、你朋友的电脑、云服务器上
  各不相同。写死在代码里就意味着换个环境要改代码。

  行业惯例（十二要素应用 The Twelve-Factor App 第三条）：
  配置存在环境变量里，代码只负责读。

用法：
  复制 .env.example 成 .env，填上你的 key。.env 已被 .gitignore 忽略，
  不会进版本库——这就是「密钥不入库」。
"""
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# 用绝对路径而不是依赖当前工作目录；这样从 dev.ps1、IDE 或服务管理器启动时
# 都能读到同一份 backend/.env。
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    """
    应用配置。

    继承 BaseSettings 后，Pydantic 会自动按这个顺序找值：
      1. 环境变量（部署到云上时用这个）
      2. .env 文件（本地开发用这个）
      3. 下面写的默认值

    找不到必填项就直接启动失败——这是好事，
    总比跑起来之后第一个请求才发现没配 key 强。
    """

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",  # .env 里有多余的键就忽略，不报错
    )

    # ── LLM 后端 ────────────────────────────────────────────────
    # 这些是「服务端持有」的密钥。前端永远看不到它们——
    # 这正是把 LLM 调用搬到后端的首要理由。
    deepseek_api_key: str = Field("", description="DeepSeek API Key")
    zhipu_api_key: str = Field("", description="智谱 API Key")
    siliconflow_api_key: str = Field("", description="硅基流动 API Key")
    openrouter_api_key: str = Field("", description="OpenRouter API Key")

    default_provider: str = Field("deepseek", description="默认使用哪个后端")

    # ── 服务本身 ────────────────────────────────────────────────
    host: str = Field("127.0.0.1", description="监听地址。手机要玩就改成 0.0.0.0")
    port: int = Field(8000, description="监听端口")

    # CORS：允许哪些前端页面调用这个后端。
    # 浏览器的同源策略默认禁止跨域请求，必须服务端明确放行。
    # 开发期用 * 图省事，真部署到公网时要收紧成具体域名。
    cors_origins: str = Field("*", description="允许的前端来源，逗号分隔")

    # ── 调用行为 ────────────────────────────────────────────────
    request_timeout_s: float = Field(120.0, description="调用 LLM 的超时秒数")
    max_retries: int = Field(3, description="遇到限流/网关错误的重试次数")

    @property
    def cors_origin_list(self) -> list[str]:
        """把逗号分隔的字符串拆成列表，给 CORS 中间件用。"""
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def key_for(self, provider: str) -> str:
        """按后端名取对应的 key。找不到返回空字符串，由调用方决定怎么处理。"""
        return {
            "deepseek": self.deepseek_api_key,
            "zhipu": self.zhipu_api_key,
            "siliconflow": self.siliconflow_api_key,
            "openrouter": self.openrouter_api_key,
        }.get(provider, "")


@lru_cache
def get_settings() -> Settings:
    """
    获取配置单例。

    加 lru_cache 是为了让 .env 只读一次——
    这也是 FastAPI 依赖注入的常见写法，测试时可以覆盖它。
    """
    return Settings()
