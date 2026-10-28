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


@app.get("/__test__/identity", include_in_schema=False)
def identity():
    return {"token": args.token, "isolated": True}


@app.middleware("http")
async def block_real_model_requests(request, call_next):
    if request.url.path.startswith("/api/chat"):
        return JSONResponse({"detail": "Real model calls disabled in browser tests"}, status_code=403)
    return await call_next(request)


sock = socket.socket()
sock.bind(("127.0.0.1", 0))
sock.listen(128)
print(json.dumps({"port": sock.getsockname()[1]}), flush=True)
uvicorn.Server(uvicorn.Config(app, log_level="warning")).run(sockets=[sock])
