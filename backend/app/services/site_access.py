"""Owner-only website access. Disabled for existing local/Android installations."""
import base64
import hashlib
import hmac
import html
import json
import os
from pathlib import Path
import secrets
import time
from urllib.parse import parse_qs, urlsplit

COOKIE = "wuji_site"
MAX_AGE = 30 * 86400


def login_page(error=""):
    return ('''<!doctype html><html lang="zh"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#102626"><link rel="manifest" href="/web/manifest.webmanifest">
<link rel="apple-touch-icon" href="/web/icons/wuji-180.png"><title>登录无界 RPG</title>
<style>*{box-sizing:border-box}body{margin:0;background:#0a1919;color:#eadcc1;font:16px system-ui;min-height:100dvh;display:grid;place-items:center;padding:24px}
main{width:min(100%,380px)}h1{font-size:30px;color:#d8bc7f;letter-spacing:5px}p{line-height:1.7;color:#a99d87}input,button{width:100%;font:inherit;border-radius:10px;padding:14px;margin-top:12px}input{background:#142d2d;color:#fff;border:1px solid #706348}button{background:#d8bc7f;color:#132222;border:0;font-weight:600}.error{color:#efac9b}</style>
<main><h1>无界 RPG</h1><p>你的世界，接着上次的旅程。</p><form action="/_site/login" method="post">
<label for="password">网站密码</label><input id="password" name="password" type="password" autocomplete="current-password" required maxlength="256">
<button type="submit">进入游戏</button></form><p class="error">''' + html.escape(error) + "</p><p>这是站主的私人游戏空间。</p></main></html>").encode()


class SiteAccess:
    def __init__(self, app, settings, data_dir):
        self.app = app
        self.enabled = settings.site_auth_enabled
        self.secure = settings.site_secure_cookies
        self.failures = {}
        self.key = b""
        self.password_hash = b""
        if self.enabled:
            password = settings.site_password.get_secret_value()
            if len(password) < 12 or len(password) > 256:
                raise RuntimeError("启用网站登录时，WUJI_SITE_PASSWORD 必须为 12–256 个字符")
            self.password_hash = hashlib.sha256(password.encode()).digest()
            path = Path(data_dir) / ".site-secret"
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                secret = path.read_bytes()
            else:
                with os.fdopen(fd, "wb") as target:
                    secret = secrets.token_bytes(32)
                    target.write(secret)
            if len(secret) != 32:
                raise RuntimeError("网站登录签名文件损坏，请恢复持久化存储备份")
            self.key = hmac.digest(secret, self.password_hash, "sha256")

    def issue(self):
        payload = str(int(time.time())) + "." + secrets.token_urlsafe(18)
        signature = base64.urlsafe_b64encode(hmac.digest(self.key, payload.encode(), "sha256")).decode().rstrip("=")
        return payload + "." + signature

    def valid(self, token):
        try:
            issued, nonce, signature = token.split(".")
            age = time.time() - int(issued)
            expected = base64.urlsafe_b64encode(hmac.digest(self.key, (issued + "." + nonce).encode(), "sha256")).decode().rstrip("=")
            return 0 <= age <= MAX_AGE and hmac.compare_digest(signature, expected)
        except (ValueError, TypeError, UnicodeError):
            return False

    @staticmethod
    async def respond(send, status, body=b"", headers=None):
        await send({"type": "http.response.start", "status": status, "headers": [
            (b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff"),
            (b"referrer-policy", b"same-origin"), (b"x-frame-options", b"DENY"),
        ] + (headers or [])})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if not self.enabled or scope["type"] != "http":
            return await self.app(scope, receive, send)
        path, method = scope["path"], scope["method"]
        if path == "/health" and method in {"GET", "HEAD"} or path.startswith("/web/") or path == "/service-worker.js":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        origin = headers.get(b"origin", b"").decode("latin-1")
        if method not in {"GET", "HEAD", "OPTIONS"} and origin:
            try:
                source = urlsplit(origin)
                valid_origin = source.scheme == scope.get("scheme", "http") and source.netloc.lower() == headers.get(b"host", b"").decode("latin-1").lower()
            except ValueError:
                valid_origin = False
            if not valid_origin:
                return await self.respond(send, 403, b'{"detail":"Invalid request origin"}', [(b"content-type", b"application/json")])
        token = ""
        for item in headers.get(b"cookie", b"").decode("latin-1").split(";"):
            if item.strip().startswith(COOKIE + "="):
                token = item.strip().split("=", 1)[1]
        authenticated = self.valid(token)
        if path == "/_site/login":
            if method == "GET":
                if authenticated:
                    return await self.respond(send, 303, headers=[(b"location", b"/")])
                return await self.respond(send, 200, login_page(), [(b"content-type", b"text/html; charset=utf-8")])
            if method != "POST":
                return await self.respond(send, 405)
            peer = (scope.get("client") or ("unknown",))[0]
            now = time.monotonic()
            self.failures = {ip: row for ip, row in self.failures.items() if now - row[0] < 600}
            row = self.failures.get(peer, (now, 0))
            if row[1] >= 10 or len(self.failures) >= 2048 and peer not in self.failures:
                return await self.respond(send, 429, login_page("尝试过于频繁，请十分钟后再试。"), [(b"content-type", b"text/html; charset=utf-8")])
            body = b""
            while True:
                event = await receive()
                if event["type"] == "http.disconnect":
                    return
                body += event.get("body", b"")
                if len(body) > 4096:
                    return await self.respond(send, 413)
                if not event.get("more_body"):
                    break
            try:
                candidate = parse_qs(body.decode("utf-8")).get("password", [""])[0]
            except UnicodeError:
                candidate = ""
            if not hmac.compare_digest(hashlib.sha256(candidate.encode()).digest(), self.password_hash):
                self.failures[peer] = (row[0], row[1] + 1)
                return await self.respond(send, 401, login_page("密码不正确。"), [(b"content-type", b"text/html; charset=utf-8")])
            self.failures.pop(peer, None)
            cookie = f"{COOKIE}={self.issue()}; HttpOnly; SameSite=Lax; Path=/; Max-Age={MAX_AGE}"
            if self.secure:
                cookie += "; Secure"
            return await self.respond(send, 303, headers=[(b"location", b"/"), (b"set-cookie", cookie.encode())])
        if path == "/_site/logout" and method == "POST" and authenticated:
            cookie = f"{COOKIE}=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0" + ("; Secure" if self.secure else "")
            return await self.respond(send, 303, headers=[(b"location", b"/_site/login"), (b"set-cookie", cookie.encode())])
        if not authenticated:
            if path.startswith("/api/"):
                body = json.dumps({"detail": {"code": "site_login_required", "message": "登录已过期，请刷新页面重新登录"}}, ensure_ascii=False).encode()
                return await self.respond(send, 401, body, [(b"content-type", b"application/json")])
            return await self.respond(send, 303, headers=[(b"location", b"/_site/login")])
        scope.setdefault("state", {})["site_authenticated"] = True

        async def private_send(event):
            if event["type"] == "http.response.start":
                event = dict(event)
                event["headers"] = [(k, v) for k, v in event.get("headers", []) if k.lower() != b"cache-control"] + [
                    (b"cache-control", b"no-store"), (b"x-frame-options", b"DENY"), (b"x-content-type-options", b"nosniff"),
                ]
            await send(event)
        return await self.app(scope, receive, private_send)
