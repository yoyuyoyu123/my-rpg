"""
路由层 · 状态结算
=================
把「结算」这件事收归服务端。

为什么是结算而不是整份状态的所有权：
    撤销回合的快照里除了 GAME_STATE 还捆着 10 个前端变量（任务、大纲、
    命名表、回合数……），而存档本身也已经带着一份状态。
    把 GAME_STATE 单独挪进 Session 表，等于让同一份数据有两个主人，
    这种一致性风险比它能换来的收益大。
    结算逻辑是纯计算，搬过来没有这个问题，而且正是下一步需要的部分。
"""
from fastapi import APIRouter

from app.schemas.state import (
    AuditPromptIn, AuditPromptOut, AuditResultIn, AuditResultOut,
    StateApplyIn, StateApplyOut,
)
from app.services.game_state import apply_patch
from app.services.state_audit import (
    AUDIT_MAX_TOKENS, AUDIT_TEMPERATURE, build_audit_prompt, parse_audit_result,
)

router = APIRouter(prefix="/api", tags=["状态"])


@router.post("/state/apply", response_model=StateApplyOut, summary="结算一次状态变化")
def apply_state(req: StateApplyIn) -> StateApplyOut:
    before = len((req.state or {}).get("ledger") or [])
    new_state = apply_patch(req.state, req.patch, world_id=req.world_id, turn=req.turn)
    return StateApplyOut(
        state=new_state,
        ledger_added=(new_state.get("ledger") or [])[before:],
    )


@router.post("/state/audit/prompt", response_model=AuditPromptOut,
             summary="出一道状态审计题")
def audit_prompt(req: AuditPromptIn) -> AuditPromptOut:
    """
    直连模式下 API key 在浏览器手里，后端调不动模型。
    所以拆成三步：后端出题 → 前端跑模型 → 后端阅卷（/state/audit/result）。
    提示词和清洗规则始终只有后端这一份。
    """
    return AuditPromptOut(
        prompt=build_audit_prompt(
            before=req.before, player_input=req.player_input,
            reply=req.reply, declared=req.declared,
        ),
        temperature=AUDIT_TEMPERATURE,
        max_tokens=AUDIT_MAX_TOKENS,
    )


@router.post("/state/audit/result", response_model=AuditResultOut,
             summary="交卷：解析审计结果")
def audit_result(req: AuditResultIn) -> AuditResultOut:
    patch = parse_audit_result(req.raw)
    return AuditResultOut(patch=patch, ok=patch is not None)
