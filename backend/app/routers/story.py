"""剧情规划 Agent 的提示词生成与结果校验接口。"""
from fastapi import APIRouter, HTTPException

from app.schemas.story import (
    StoryPlanContext, StoryPlanPromptOut, StoryPlanResultIn, StoryPlanResultOut,
)
from app.services.story_planner import build_story_plan_prompt, parse_story_runtime

router = APIRouter(prefix="/api/story", tags=["剧情规划"])


@router.post("/plan/prompt", response_model=StoryPlanPromptOut, summary="生成规划 Agent 提示词")
def plan_prompt(ctx: StoryPlanContext) -> StoryPlanPromptOut:
    try:
        return StoryPlanPromptOut(prompt=build_story_plan_prompt(ctx))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/plan/result", response_model=StoryPlanResultOut, summary="校验规划 Agent 结果")
def plan_result(body: StoryPlanResultIn) -> StoryPlanResultOut:
    try:
        runtime, warnings = parse_story_runtime(
            body.raw, body.previous_runtime, body.turn, body.reason, body.premise_state,
            body.pace,
        )
        return StoryPlanResultOut(runtime=runtime, warnings=warnings)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
