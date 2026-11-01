"""Run the exact phone bootstrap against isolated storage. No real AI requests."""
import asyncio
from http.cookiejar import CookieJar
import importlib.util
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
spec = importlib.util.spec_from_file_location("mobile_runtime", ROOT / "android/app/src/main/python/mobile_runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def main():
    for key in ("DEEPSEEK_API_KEY", "ZHIPU_API_KEY", "SILICONFLOW_API_KEY", "OPENROUTER_API_KEY"):
        os.environ[key] = ""
    with TemporaryDirectory(prefix="wuji-phone-test-") as temporary:
        info = json.loads(runtime.start(temporary, str(ROOT)))
        origin = "http://127.0.0.1:" + str(info["port"])
        cookie = CookieJar()
        client = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(cookie))

        def get(path, data=None, method=None):
            payload = None if data is None else json.dumps(data).encode()
            req = urllib.request.Request(origin + path, data=payload, method=method,
                                         headers={"Content-Type": "application/json"} if payload else {})
            with client.open(req, timeout=10) as r:
                return r.status, r.read(), r.headers

        try:
            for _ in range(100):
                try:
                    get("/health")
                except urllib.error.HTTPError as exc:
                    assert exc.code == 403
                    break
                except OSError:
                    time.sleep(.05)
            else:
                raise AssertionError("phone backend did not start")
            with client.open(info["url"], timeout=10) as response:
                assert response.status == 200
                assert "文字".encode() in response.read()
                assert response.url == origin + "/"
            assert any(c.name == "wuji_phone" and "HttpOnly" in c._rest for c in cookie)
            assert get("/health")[0] == 200
            catalog = json.loads(get("/api/worlds")[1])
            assert catalog
            get("/api/config", {"deepseek_api_key": "phone-fixture-not-real"}, "POST")
            config_path = Path(temporary) / ".env"
            assert config_path.is_file() and "phone-fixture-not-real" in config_path.read_text()
            session = json.loads(get("/api/sessions", {"world_id": "wuxia", "title": "手机运行验收", "pace": "long"}, "POST")[1])
            save = {"schema_version": 2, "history": [{"role": "user", "content": "检查行囊"}],
                    "gstate": {"inv": [{"name": "干粮", "quantity": 1}]}, "world": "wuxia", "turns": 1,
                    "novelRuntime": {"excerpts": [{"turn": 1, "text": "原文记忆"}]}}
            assert get("/api/saves/sv_0", {"payload": save, "base_revision": 0}, "PUT")[0] == 200
            assert json.loads(get("/api/saves/sv_0")[1])["payload"]["novelRuntime"] == save["novelRuntime"]
            assert (Path(temporary) / "wuji.db").is_file()
            # A second client cannot replay the one-time startup URL or use APIs.
            stranger = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for url in [info["url"], origin + "/api/saves", origin + "/api/config", origin + "/"]:
                try:
                    stranger.open(url, timeout=5)
                    raise AssertionError("unauthenticated phone access was accepted")
                except urllib.error.HTTPError as exc:
                    assert exc.code == 403
            print("Android runtime: bootstrap cookie, API isolation, local configuration, 10 worlds, SQLite and narration save roundtrip passed")
        finally:
            runtime._server.should_exit = True
            runtime._thread.join(timeout=10)
            from app.db.session import engine
            asyncio.run(engine.dispose())


if __name__ == "__main__":
    main()
