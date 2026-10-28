from fastapi import APIRouter

from app.schemas.rules import RuleActionIn, RuleActionOut, RuleCheckIn, RuleCheckOut
from app.services.rules_engine import resolve_action, resolve_check

router = APIRouter(prefix="/api/rules", tags=["纯程序规则"])


@router.post("/check", response_model=RuleCheckOut, summary="结算一次风险检定")
def check(req: RuleCheckIn) -> RuleCheckOut:
    return resolve_check(req)


@router.post("/action", response_model=RuleActionOut, summary="结算移动、交易或任务动作")
def action(req: RuleActionIn) -> RuleActionOut:
    return resolve_action(req)
