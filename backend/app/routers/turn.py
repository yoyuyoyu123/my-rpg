"""
路由层 · 回合
=============
把提示词编译暴露成接口。

这一步之后，index.html 里不再有任何世界包正文与规则常量 ——
`/api/worlds` 不下发 prompt 的设计到这里才真正生效。
"""
from fastapi import APIRouter

from app.schemas.turn import TurnContext, TurnPromptOut
from app.services.prompt_builder import (
    active_rule_packs, build_system_prompt, debug_hash, turn_mandate,
)

router = APIRouter(prefix="/api", tags=["回合"])


@router.post("/turn/prompt", response_model=TurnPromptOut, summary="编译本回合的系统提示词")
def compile_prompt(ctx: TurnContext) -> TurnPromptOut:
    """
    前端传运行时状态，后端返回组装好的 system prompt。

    这一步只搬「编译」，不碰状态所有权：
    调模型、流式渲染、落状态仍在前端。这样每一步做完游戏都能玩，
    而不是等一次大重构全部落地才敢跑。
    """
    sp = build_system_prompt(ctx)
    packs = active_rule_packs(ctx)
    return TurnPromptOut(
        system_prompt=sp, turn_mandate=turn_mandate(ctx),
        chars=len(sp), hash=debug_hash(sp),
        rule_packs=[label for _, label, _ in packs],
        rules_hash=debug_hash("\n\n".join(text for _, _, text in packs)),
    )
