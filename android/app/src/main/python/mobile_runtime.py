"""Process-local phone backend, protected by an unguessable capability cookie."""
import asyncio
import hmac
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import secrets
import socket
import threading
from urllib.parse import parse_qs


class CapabilityGate:
    def __init__(self, app, token):
        self.app, self.token, self.used = app, token, False

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        jar = SimpleCookie()
        try:
            jar.load(headers.get(b"cookie", b"").decode("latin-1"))
        except Exception:
            pass
        cookie = jar.get("wuji_phone")
        authenticated = bool(cookie and hmac.compare_digest(cookie.value, self.token))
        if scope["path"] == "/_mobile/bootstrap":
            supplied = parse_qs(scope.get("query_string", b"").decode("ascii", "ignore")).get("token", [""])[0]
            if authenticated or (not self.used and hmac.compare_digest(supplied, self.token)):
                self.used = True
                await send({"type": "http.response.start", "status": 303, "headers": [
                    (b"location", b"/"), (b"cache-control", b"no-store"),
                    (b"set-cookie", f"wuji_phone={self.token}; Path=/; HttpOnly; SameSite=Strict".encode("ascii")),
                ]})
                return await send({"type": "http.response.body", "body": b""})
        if not authenticated:
            await send({"type": "http.response.start", "status": 403, "headers": [(b"content-type", b"text/plain")]})
            return await send({"type": "http.response.body", "body": b"This backend belongs to Wuji RPG."})
        return await self.app(scope, receive, send)


_server = None
_info = None
_thread = None


def start(data_dir, resource_dir, preferred_port=0):
    global _server, _info, _thread
    if _thread and _thread.is_alive():
        return json.dumps(_info)
    data = Path(data_dir).resolve()
    resources = Path(resource_dir).resolve()
    if not (resources / "index.html").is_file() or not (resources / "data/worlds/catalog.json").is_file():
        raise RuntimeError("游戏资源不完整，请重新安装 APK；不会删除现有存档")
    data.mkdir(parents=True, exist_ok=True)
    os.environ["WUJI_DATA_DIR"] = str(data)
    os.environ["WUJI_CONFIG_FILE"] = str(data / ".env")
    os.environ["WUJI_RESOURCE_DIR"] = str(resources)
    # Android does not provide a usable process signal handler on worker threads.
    import uvicorn
    from app.main import app
    from fastapi.responses import FileResponse

    @app.get("/mobile-shell.js", include_in_schema=False)
    def mobile_shell():
        return FileResponse(resources / "mobile-shell.js", media_type="application/javascript")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", int(preferred_port)))
        sock.listen(128)
    except OSError as exc:
        sock.close()
        raise RuntimeError("本机游戏端口被占用，请关闭其他无界进程或重启手机；现有存档保留") from exc
    port = sock.getsockname()[1]
    token = secrets.token_urlsafe(32)
    gate = CapabilityGate(app, token)
    _server = uvicorn.Server(uvicorn.Config(gate, host="127.0.0.1", port=port,
        loop="asyncio", http="h11", ws="none", access_log=False, log_level="warning"))

    def run():
        try:
            _server.run(sockets=[sock])
        finally:
            sock.close()

    _thread = threading.Thread(target=run, name="wuji-local-game", daemon=True)
    _thread.start()
    _info = {"port": port, "url": f"http://127.0.0.1:{port}/_mobile/bootstrap?token={token}"}
    return json.dumps(_info)
