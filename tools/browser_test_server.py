"""Browser tests run against a fresh database and configuration in a private process."""
import argparse
import json
import os
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
parser = argparse.ArgumentParser()
parser.add_argument("--data-dir", required=True)
parser.add_argument("--token", required=True)
args = parser.parse_args()
data_dir = Path(args.data_dir).resolve()
if data_dir == (ROOT / "backend/data").resolve() or (data_dir / "wuji.db").exists():
    raise SystemExit("Browser tests require a fresh isolated database directory")
os.environ["WUJI_DATA_DIR"] = str(data_dir)
for key in ("DEEPSEEK_API_KEY", "ZHIPU_API_KEY", "SILICONFLOW_API_KEY", "OPENROUTER_API_KEY"):
    os.environ[key] = ""

from app import config  # noqa: E402

config.ENV_FILE = data_dir / ".env"
config.Settings.model_config["env_file"] = str(config.ENV_FILE)
config.get_settings.cache_clear()

from app.main import app  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
import uvicorn  # noqa: E402

# Explicit opt-in, test process only. Exercise the REAL novel orchestration and
# HTTP routes with deterministic model responses, never with a player's keys.
if os.environ.get("RPG_TEST_NOVEL_FIXTURE") == "1":
    from app.services import novel_engine
    from app.services.llm import LLMResult

    async def fixture_chat(**kwargs):
        last = kwargs["messages"][-1]["content"]
        if last == novel_engine.PLAN_PROMPT:
            result = {"nodes": [{"id": "tea", "actor": "掌柜", "intent": "完成交易", "evidence": ["掌柜正在擦桌"],
                                 "development": "掌柜确认干粮和送信的委托。"}]}
            text = json.dumps(result, ensure_ascii=False)
        elif last.startswith("【本回合写法】"):
            text = ('掌柜把一包干粮放在柜台上，点头确认明日送信的委托。你刚才练习的基础剑法已有些进展。\n'
                    '1. 询问送信地点\n2. 收好干粮等候\n或输入任何你想做的事\n'
                    '【STATE】{"inv_add":[{"name":"干粮","qty":1}],"skill_upsert":[{"name":"基础剑法","proficiency":5}]}【/STATE】')
        else:
            drafts = json.loads(last)["drafts"]
            text = json.dumps({"reviews": [{"id": int(i), "agency_ok": True, "facts_ok": True, "knowledge_ok": True,
                                          "causal": .8, "character": .8, "prose": .8, "pacing": .8} for i in drafts]})
        return LLMResult(text, "", "ollama", "isolated-fixture", total_tokens=10)

    novel_engine.call_chat = fixture_chat


@app.get("/__test__/identity", include_in_schema=False)
def identity():
    return {"token": args.token, "isolated": True}


@app.middleware("http")
async def block_real_model_requests(request, call_next):
    if request.url.path.startswith("/api/chat") or (request.url.path.startswith("/api/novel") and os.environ.get("RPG_TEST_NOVEL_FIXTURE") != "1"):
        return JSONResponse({"detail": "Real model calls disabled in browser tests"}, status_code=403)
    return await call_next(request)


sock = socket.socket()
sock.bind(("127.0.0.1", 0))
sock.listen(128)
print(json.dumps({"port": sock.getsockname()[1]}), flush=True)
uvicorn.Server(uvicorn.Config(app, log_level="warning")).run(sockets=[sock])
