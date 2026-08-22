"""
路由层 · GM 裁定
================
裁判只判定、不写剧情；写手只按判定叙事、不得改判。
合在一起做的话，模型会一边编故事一边为故事的需要放宽判定。
"""
from fastapi import APIRouter

from app.schemas.director import (
    DirectorPromptIn, DirectorPromptOut, DirectorResultIn, DirectorResultOut,
)
from app.services.director import (
    DIRECTOR_MAX_TOKENS, DIRECTOR_TEMPERATURE, build_director_prompt, parse_ruling,
)

router = APIRouter(prefix="/api", tags=["GM 裁定"])


@router.post("/director/prompt", response_model=DirectorPromptOut,
             summary="出一道裁定题")
def director_prompt(req: DirectorPromptIn) -> DirectorPromptOut:
    return DirectorPromptOut(
        prompt=build_director_prompt(
            player_input=req.player_input, game_state=req.game_state,
            story_tone=req.story_tone, story_dna=req.story_dna,
            outline=req.outline, player_canon=req.player_canon,
            premise_state=req.premise_state, prefs=req.prefs,
            recent_messages=req.recent_messages,
        ),
        temperature=DIRECTOR_TEMPERATURE,
        max_tokens=DIRECTOR_MAX_TOKENS,
    )


@router.post("/director/result", response_model=DirectorResultOut,
             summary="交卷：解析裁定结果")
def director_result(req: DirectorResultIn) -> DirectorResultOut:
    ruling = parse_ruling(req.raw)
    return DirectorResultOut(ruling=ruling, ok=ruling is not None)
