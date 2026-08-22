"""
路由层 · 写手后处理
===================
模型没按契约交货时的两道补救题。它们的提示词和写手契约描述的是同一套边界，
所以留在后端和 prompt_builder 做邻居。

只出题，不阅卷：这两题的结果解析要用到前端本来就有的选项解析器
（主权检测也在用），搬过去等于两边各存一份。
"""
from fastapi import APIRouter

from app.schemas.writer import (
    AgencyGuardIn, AgencyGuardOut, OptionRepairIn, OptionRepairOut,
)
from app.services.writer_guard import (
    OPTION_MAX_TOKENS, OPTION_TEMPERATURE, REWRITE_MAX_TOKENS,
    build_agency_guard, build_option_repair,
)

router = APIRouter(prefix="/api/writer", tags=["写手后处理"])


@router.post("/agency-guard", response_model=AgencyGuardOut,
             summary="生成主权纠错指令")
def agency_guard(req: AgencyGuardIn) -> AgencyGuardOut:
    return AgencyGuardOut(
        guard=build_agency_guard(req.codes), max_tokens=REWRITE_MAX_TOKENS,
    )


@router.post("/option-repair", response_model=OptionRepairOut,
             summary="生成选项补全题")
def option_repair(req: OptionRepairIn) -> OptionRepairOut:
    return OptionRepairOut(
        prompt=build_option_repair(draft=req.draft, player_input=req.player_input),
        temperature=OPTION_TEMPERATURE,
        max_tokens=OPTION_MAX_TOKENS,
    )
