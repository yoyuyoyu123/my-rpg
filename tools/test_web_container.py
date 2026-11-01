"""Exercise the production image and a disposable volume; never call a model."""
import http.cookiejar
import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def main():
    suffix = uuid.uuid4().hex[:12]
    container, volume = "wuji-smoke-" + suffix, "wuji-smoke-data-" + suffix
    password = "fixture-container-password-12345"
    docker("volume", "create", volume)
    try:
        docker("run", "--detach", "--name", container, "--publish", "127.0.0.1::8000",
               "--mount", f"type=volume,source={volume},target=/data",
               "--env", "WUJI_SITE_PASSWORD=" + password,
               "--env", "WUJI_SITE_SECURE_COOKIES=false", "wuji-web:test")
        port = docker("port", container, "8000/tcp").rsplit(":", 1)[-1]
        base = "http://127.0.0.1:" + port
        cookies = http.cookiejar.CookieJar()
        client = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(cookies))

        def request(path, method="GET", payload=None, form=False):
            body = None
            headers = {}
            if payload is not None:
                body = (urllib.parse.urlencode(payload) if form else json.dumps(payload)).encode()
                headers["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
            req = urllib.request.Request(base + path, data=body, headers=headers, method=method)
            try:
                with client.open(req, timeout=3) as response:
                    raw = response.read()
                    if "application/json" in response.headers.get("Content-Type", ""):
                        return response.status, json.loads(raw)
                    return response.status, raw
            except urllib.error.HTTPError as error:
                return error.code, error.read()

        def wait_for_health():
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                try:
                    if request("/health")[0] == 200:
                        return
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(.2)
            raise AssertionError("Production image did not start")

        wait_for_health()
        assert request("/api/saves")[0] == 401
        assert request("/_site/login", "POST", {"password": password}, form=True)[0] == 200
        assert request("/api/config", "POST", {"gemini_api_key": "fixture-container-google"})[0] == 200
        payload = {"schema_version": 2, "history": [{"role": "user", "content": "容器重启后继续游戏"}], "gstate": {}}
        assert request("/api/saves/auto", "PUT", {"payload": payload})[0] == 200
        assert request("/web/manifest.webmanifest")[0] == 200
        # Verify the application process, not merely the image declaration.
        uid = docker("exec", container, "sh", "-c", "awk '/^Uid:/{print $2}' /proc/1/status")
        assert uid == "10001", uid
        docker("restart", "--time", "5", container)
        wait_for_health()
        status, saved = request("/api/saves/auto")
        assert status == 200 and saved["payload"]["history"] == payload["history"]
        status, configured = request("/api/config")
        assert status == 200 and next(p for p in configured["providers"] if p["id"] == "gemini")["configured"]
        status, body = request("/_site/logout", "POST")
        assert status == 200 and request("/api/saves")[0] == 401
        print("Production image: non-root startup, private login, config/save/session persistence across restart, PWA and logout passed")
    except BaseException:
        subprocess.run(["docker", "logs", "--tail", "60", container], check=False)
        raise
    finally:
        subprocess.run(["docker", "rm", "--force", container], check=False, stdout=subprocess.DEVNULL)
        subprocess.run(["docker", "volume", "rm", volume], check=False, stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
