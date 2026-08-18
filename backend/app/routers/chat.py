"""
路由层 · 对话代理
=================
职责：只做三件事——收请求、调服务、把结果或错误翻译成 HTTP 响应。

注意这个文件里【没有】任何业务逻辑：
  没有重试、没有拼请求体、没有解析各家的返回格式。
  那些都在 services/llm.py 里。

这就是分层的意义：
  想换 Web 框架（比如从 FastAPI 换成别的），只需要重写这一层；
  想给业务逻辑写单元测试，也不需要启动 HTTP 服务。
"""
from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings
from app.domain.providers import PROVIDERS, requires_key
from app.schemas.chat import ChatRequest, ChatResponse, ProviderInfo, Usage
from app.services.llm import LLMError, call_chat

router = APIRouter(prefix="/api", tags=["对话"])


@router.get("/providers", response_model=list[ProviderInfo], summary="列出可用的 LLM 后端")
def list_providers(settings: Settings = Depends(get_settings)) -> list[ProviderInfo]:
    """
    告诉前端有哪些后端可选、哪些已经配好了 key。

    前端据此渲染选择列表，并把没配 key 的置灰——
    这样用户不会选了之后才发现用不了。

    注意这里【不返回】任何 key 本身，只返回「配没配」这个布尔值。
    """
    return [
        ProviderInfo(
            id=p.id,
            label=p.label,
            default_model=p.default_model,
            configured=(not requires_key(p.id)) or bool(settings.key_for(p.id)),
            note=p.note,
        )
        for p in PROVIDERS.values()
    ]


@router.post("/chat", response_model=ChatResponse, summary="调用 LLM 对话补全")
async def chat(req: ChatRequest, settings: Settings = Depends(get_settings)) -> ChatResponse:
    """
    代理一次 LLM 调用。

    这是整个后端最重要的端点——它的存在让 API key 不必下发到浏览器。

    前端原本直接 fetch('https://api.deepseek.com/...', {Authorization: key})，
    现在改成 fetch('/api/chat', {...})，key 留在服务端。
    """
    try:
        result = await call_chat(
            settings=settings,
            provider_id=req.provider,
            model=req.model,
            messages=[m.model_dump() for m in req.messages],
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
    except LLMError as exc:
        # 把业务异常翻译成 HTTP 响应。
        # detail 用结构化的 dict，前端可以按 code 分支处理，而不是解析错误文本。
        raise HTTPException(
            status_code=exc.status,
            detail={"code": exc.code, "message": exc.message, "retryable": exc.retryable},
        ) from exc

    return ChatResponse(
        content=result.content,
        provider=result.provider,
        model=result.model,
        usage=Usage(
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
        ),
        retries=result.retries,
    )
