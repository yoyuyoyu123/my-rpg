"""Buffered selection + SSE progress. Disconnect cancels all upstream work."""
import asyncio
import contextlib
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.config import Settings, get_settings
from app.schemas.novel import NovelRequest
from app.services.llm import LLMError
from app.services.novel_engine import generate_turn

router = APIRouter(prefix="/api/novel", tags=["游戏叙事"])


def frame(value) -> str:
    return "data: " + json.dumps(value, ensure_ascii=False) + "\n\n"


@router.post("/turn/stream")
async def novel_turn(req: NovelRequest, settings: Settings = Depends(get_settings)):
    async def events():
        progress = asyncio.Queue(maxsize=32)

        async def emit(stage):
            await progress.put(stage)

        async def bounded():
            async with asyncio.timeout(600):
                return await generate_turn(req, settings, emit)

        task = asyncio.create_task(bounded())
        pending = None
        try:
            yield frame({"novel_stage": "准备当前行动的反馈；比较完成后显示正文"})
            while not task.done():
                pending = asyncio.create_task(progress.get())
                done, _ = await asyncio.wait({task, pending}, timeout=5, return_when=asyncio.FIRST_COMPLETED)
                if pending in done:
                    yield frame({"novel_stage": pending.result()})
                else:
                    pending.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await pending
                    yield ": keep-alive\n\n"
            result = await task
            yield frame({"novel_meta": result["meta"]})
            # This is display streaming AFTER selection, not upstream first-token streaming.
            for pos in range(0, len(result["content"]), 96):
                yield frame({"choices": [{"delta": {"content": result["content"][pos:pos + 96]}}]})
                await asyncio.sleep(0)
            yield frame({"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": result["usage"]})
            yield "data: [DONE]\n\n"
        except LLMError as exc:
            yield frame({"error": {"code": exc.code, "message": exc.message}})
        except TimeoutError:
            yield frame({"error": {"code": "novel_timeout", "message": "本回合等待超时，未提交游戏进度"}})
        except Exception:
            yield frame({"error": {"code": "novel_failed", "message": "本回合生成失败，未提交游戏进度"}})
        finally:
            if pending and not pending.done():
                pending.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await pending
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    return StreamingResponse(events(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
    })
