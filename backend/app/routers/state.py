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

from app.schemas.state import StateApplyIn, StateApplyOut
from app.services.game_state import apply_patch

router = APIRouter(prefix="/api", tags=["状态"])


@router.post("/state/apply", response_model=StateApplyOut, summary="结算一次状态变化")
def apply_state(req: StateApplyIn) -> StateApplyOut:
    before = len((req.state or {}).get("ledger") or [])
    new_state = apply_patch(req.state, req.patch, world_id=req.world_id, turn=req.turn)
    return StateApplyOut(
        state=new_state,
        ledger_added=(new_state.get("ledger") or [])[before:],
    )
