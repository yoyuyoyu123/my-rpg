import sys
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from app.config import Settings
from app.services.site_access import SiteAccess, COOKIE, MAX_AGE

PASSWORD = "测试私人游戏-password-123"


def fixture_app(tmp_path, password=PASSWORD, secure=True):
    app = FastAPI()
    settings = Settings(site_auth_enabled=True, site_password=password, site_secure_cookies=secure)
    app.add_middleware(SiteAccess, settings=settings, data_dir=tmp_path)

    @app.get("/")
    @app.get("/api/saves")
    @app.post("/api/chat")
    def private(request: Request):
        return {"owner": request.state.site_authenticated, "secret": "saved game"}

    @app.get("/health")
    def health():
        return {"status": "ok"}
    return app


@pytest.mark.parametrize("path", ["/", "/docs", "/api/saves", "/research/research_db.json"])
def test_unauthenticated_visitors_cannot_read_game(tmp_path, path):
    with TestClient(fixture_app(tmp_path), base_url="https://game.test", follow_redirects=False) as c:
        result = c.get(path)
        assert result.status_code == (401 if path.startswith("/api/") else 303)
        assert "saved game" not in result.text


def test_login_cookie_and_owner_access(tmp_path):
    with TestClient(fixture_app(tmp_path), base_url="https://game.test", follow_redirects=False) as c:
        assert c.get("/health").status_code == 200
        assert c.get("/_site/login").status_code == 200
        result = c.post("/_site/login", data={"password": PASSWORD}, headers={"Origin": "https://game.test"})
        assert result.status_code == 303
        cookie = result.headers["set-cookie"]
        assert "HttpOnly" in cookie and "Secure" in cookie and "samesite=lax" in cookie.lower()
        assert PASSWORD not in cookie
        assert c.get("/api/saves").json()["owner"] is True
        assert c.post("/api/chat", json={}).status_code == 200
        assert c.get("/api/saves").headers["cache-control"] == "no-store"


def test_tampering_expiry_and_password_rotation(tmp_path, monkeypatch):
    settings = Settings(site_auth_enabled=True, site_password=PASSWORD)
    gate = SiteAccess(None, settings, tmp_path)
    token = gate.issue()
    assert gate.valid(token)
    assert not gate.valid(token + "a")
    assert not gate.valid("invalid")
    rotated = SiteAccess(None, Settings(site_auth_enabled=True, site_password="a-new-private-password"), tmp_path)
    assert not rotated.valid(token)
    original = time.time()
    monkeypatch.setattr(time, "time", lambda: original + MAX_AGE + 2)
    assert not gate.valid(token)


def test_cross_site_writes_and_forged_owner_header_are_rejected(tmp_path):
    with TestClient(fixture_app(tmp_path), base_url="https://game.test", follow_redirects=False) as c:
        assert c.post("/api/chat", headers={"X-Site-Authenticated": "true"}).status_code == 401
        assert c.post("/_site/login", data={"password": PASSWORD}, headers={"Origin": "https://attacker.test"}).status_code == 403
        c.post("/_site/login", data={"password": PASSWORD})
        assert c.post("/api/chat", json={}, headers={"Origin": "https://attacker.test"}).status_code == 403
        assert c.post("/api/chat", json={}, headers={"Origin": "https://game.test"}).status_code == 200
        assert c.post("/_site/logout", headers={"Origin": "https://game.test"}).status_code == 303
        assert c.get("/api/saves").status_code == 401


def test_login_attempts_and_large_bodies_are_bounded(tmp_path):
    with TestClient(fixture_app(tmp_path), base_url="https://game.test", follow_redirects=False) as c:
        assert c.post("/_site/login", content=b"x" * 5000).status_code == 413
        for _ in range(10):
            assert c.post("/_site/login", data={"password": "wrong"}).status_code == 401
        assert c.post("/_site/login", data={"password": PASSWORD}).status_code == 429


def test_public_website_refuses_empty_password(tmp_path):
    with pytest.raises(RuntimeError, match="12"):
        SiteAccess(None, Settings(site_auth_enabled=True, site_password=""), tmp_path)


def test_cloud_config_requires_verified_owner_and_local_policy_is_preserved(tmp_path, monkeypatch):
    from app.routers import config
    monkeypatch.setattr(config, "get_settings", lambda: Settings(site_auth_enabled=True, site_password=PASSWORD))
    scope = {"type": "http", "client": ("203.0.113.2", 1234), "headers": [], "state": {"site_authenticated": True}}
    config._require_local_request(Request(scope))
    scope["state"] = {}
    with pytest.raises(HTTPException) as exc:
        config._require_local_request(Request(scope))
    assert exc.value.status_code == 403
    monkeypatch.setattr(config, "get_settings", lambda: Settings(site_auth_enabled=False))
    scope["state"] = {"site_authenticated": True}
    with pytest.raises(HTTPException):
        config._require_local_request(Request(scope))
