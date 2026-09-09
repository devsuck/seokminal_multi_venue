"""세션 로그인(api_server/auth.py) + 원격 요청 게이트(main._require_key_for_remote) 테스트."""
from fastapi.testclient import TestClient

import api_server.auth as auth_module
import api_server.main as main_module
from api_server.main import app

# 원격(비-loopback) 취급 클라이언트 — 게이트가 실제로 걸리는지 확인하려면 필요.
remote_client = TestClient(app, client=("203.0.113.5", 1))
local_client = TestClient(app, client=("127.0.0.1", 1))


def test_verify_session_accepts_freshly_signed_cookie(monkeypatch):
    monkeypatch.setattr(auth_module, "_SESSION_SECRET", "test-secret")
    import time
    cookie = auth_module._sign(int(time.time()) + 3600)
    assert auth_module.verify_session(cookie) is True


def test_verify_session_rejects_tampered_cookie(monkeypatch):
    monkeypatch.setattr(auth_module, "_SESSION_SECRET", "test-secret")
    import time
    payload, _, _sig = auth_module._sign(int(time.time()) + 3600).partition(".")
    assert auth_module.verify_session(f"{payload}.deadbeef") is False


def test_verify_session_rejects_expired_cookie(monkeypatch):
    monkeypatch.setattr(auth_module, "_SESSION_SECRET", "test-secret")
    cookie = auth_module._sign(0)  # 1970년 만료
    assert auth_module.verify_session(cookie) is False


def test_verify_session_rejects_missing_cookie():
    assert auth_module.verify_session(None) is False


def test_login_rejects_wrong_password(monkeypatch):
    monkeypatch.setattr(auth_module, "_ADMIN_PASSWORD", "correct-horse")
    r = local_client.post("/auth/login", json={"password": "wrong"})
    assert r.status_code == 401


def test_login_rejects_when_admin_password_unset(monkeypatch):
    monkeypatch.setattr(auth_module, "_ADMIN_PASSWORD", "")
    r = local_client.post("/auth/login", json={"password": "anything"})
    assert r.status_code == 401


def test_login_succeeds_and_sets_cookie(monkeypatch):
    monkeypatch.setattr(auth_module, "_ADMIN_PASSWORD", "correct-horse")
    r = local_client.post("/auth/login", json={"password": "correct-horse"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert auth_module.SESSION_COOKIE_NAME in r.cookies


def test_remote_request_without_credentials_is_rejected(monkeypatch):
    monkeypatch.setattr(main_module, "_MOBILE_API_KEY", "")
    r = remote_client.get("/health")
    assert r.status_code == 401


def test_remote_request_with_valid_session_cookie_is_allowed(monkeypatch):
    monkeypatch.setattr(auth_module, "_ADMIN_PASSWORD", "correct-horse")
    monkeypatch.setattr(main_module, "_MOBILE_API_KEY", "")
    login = remote_client.post("/auth/login", json={"password": "correct-horse"})
    assert login.status_code == 200
    r = remote_client.get("/health")
    assert r.status_code == 200
