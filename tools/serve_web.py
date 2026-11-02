"""Production personal website entry point; refuses an unprotected deployment."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
data = Path(os.environ.get("WUJI_DATA_DIR", ROOT / "backend/data")).resolve()
os.umask(0o077)
os.environ.setdefault("WUJI_SITE_AUTH_ENABLED", "true")
os.environ.setdefault("WUJI_CONFIG_FILE", str(data / "runtime.env"))
os.environ.setdefault("CORS_ORIGINS", os.environ.get("RENDER_EXTERNAL_URL", ""))
sys.path.insert(0, str(ROOT / "backend"))

if __name__ == "__main__":
    from app.config import get_settings
    import uvicorn
    settings = get_settings()
    if not settings.site_auth_enabled or len(settings.site_password.get_secret_value()) < 12:
        raise SystemExit("网站启动失败：请设置 WUJI_SITE_PASSWORD（至少 12 字符），并启用网站登录")
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")),
                workers=1, loop="asyncio", http="h11", ws="none", proxy_headers=True,
                forwarded_allow_ips="*", access_log=False, timeout_graceful_shutdown=120)
