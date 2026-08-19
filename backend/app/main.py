"""
应用入口
========
职责：把各部分组装起来，配好中间件，暴露给 uvicorn。

启动（在 backend 目录下）：
    .venv/Scripts/python.exe -m uvicorn app.main:app --reload

想让手机也能玩（同一 WiFi）：
    .venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
    然后手机浏览器访问 http://<你电脑的局域网IP>:8000/
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db.session import init_db
from app.routers import chat as chat_router
from app.routers import memory as memory_router
from app.routers import saves as saves_router
from app.routers import worlds as worlds_router
from app.schemas.chat import ErrorDetail  # noqa: F401  (让它出现在 OpenAPI 文档里)

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    生命周期钩子：yield 之前是启动，之后是关闭。

    建表放这里——表已存在时是空操作，可以安全重复执行。
    （旧写法 @app.on_event("startup") 已被 FastAPI 弃用。）
    """
    await init_db()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="无界·叙事引擎 API",
    description=(
        "AI 驱动的叙事 RPG 后端。\n\n"
        "**当前阶段**：对话代理（API key 收归服务端）。\n"
        "后续会陆续接管提示词组装、状态结算与存档持久化。"
    ),
    version="0.1.0",
)

# ── CORS ────────────────────────────────────────────────────────
# 浏览器的同源策略：网页只能请求「同一个源」（协议+域名+端口都相同）的资源。
# 前端如果不是由这个服务提供的（比如你用别的端口开着旧的 index.html），
# 请求就会被浏览器拦截——除非服务端明确说「我允许」，就是下面这段。
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router.router)
app.include_router(worlds_router.router)
app.include_router(memory_router.router)
app.include_router(saves_router.router)


@app.get("/health", tags=["系统"], summary="健康检查")
def health() -> dict:
    """部署平台和监控靠它判断服务是否存活。"""
    return {"status": "ok", "version": app.version}


# ── 托管前端 ────────────────────────────────────────────────────
# 让同一个服务既提供 API 又提供网页，好处：
#   1. 前端和后端同源，不用操心 CORS
#   2. 手机只要访问一个地址就能玩
#   3. 部署时只有一个服务要管
#
# 这也是 SillyTavern 的做法。
FRONTEND_DIR = Path(__file__).resolve().parents[2]  # 仓库根目录


@app.get("/", include_in_schema=False)
def serve_index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


# research/ 下的数据文件也要能被前端取到
research_dir = FRONTEND_DIR / "research"
if research_dir.is_dir():
    app.mount("/research", StaticFiles(directory=research_dir), name="research")
