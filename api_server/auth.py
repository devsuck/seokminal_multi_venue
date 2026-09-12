"""단일 유저 세션 로그인 — 클라우드 배포 대비, MOBILE_API_KEY(공유 정적 키, JS 번들에
그대로 노출) 대체용. 유저 테이블/DB 없음: 비번 1개(env) + HMAC 서명 쿠키.

ponytail: SESSION_SECRET 미설정 시 프로세스 기동마다 랜덤 생성 — 재시작하면 기존
세션 전부 무효(재로그인 필요). 단일 유저라 재로그인 비용이 낮아 별도 env 설정
강제 안 함. 영속 세션 원하면 SESSION_SECRET env로 고정값 지정.
"""
from __future__ import annotations

import hmac
import os
import secrets
import time

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_COOKIE_NAME = "seokminal_session"
_SESSION_MAX_AGE_SEC = 30 * 24 * 3600  # 30일

_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
_SESSION_SECRET = os.environ.get("SESSION_SECRET") or secrets.token_hex(32)
_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "").lower() in ("1", "true", "yes")
# 로컬은 기본 lax(같은 사이트). 클라우드에서 api.<도메인>/app.<도메인> 서브도메인
# 분리하면 cross-site 취급이라 Lax 쿠키가 credentials:include fetch에 안 실림 —
# COOKIE_SAMESITE=none으로 오버라이드(브라우저 스펙상 Secure 필수라 COOKIE_SECURE=true도 같이).
_COOKIE_SAMESITE = os.environ.get("COOKIE_SAMESITE", "lax")


def _sign(exp: int) -> str:
    payload = str(exp)
    sig = hmac.new(_SESSION_SECRET.encode(), payload.encode(), "sha256").hexdigest()
    return f"{payload}.{sig}"


def verify_session(cookie_value: str | None) -> bool:
    if not cookie_value or "." not in cookie_value:
        return False
    payload, _, sig = cookie_value.partition(".")
    expected = hmac.new(_SESSION_SECRET.encode(), payload.encode(), "sha256").hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        return int(payload) > time.time()
    except ValueError:
        return False


class LoginRequest(BaseModel):
    password: str


@router.post("/login")
def login(body: LoginRequest, response: Response):
    if not _ADMIN_PASSWORD or not hmac.compare_digest(body.password, _ADMIN_PASSWORD):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="invalid password")
    exp = int(time.time()) + _SESSION_MAX_AGE_SEC
    response.set_cookie(
        SESSION_COOKIE_NAME,
        _sign(exp),
        max_age=_SESSION_MAX_AGE_SEC,
        httponly=True,
        samesite=_COOKIE_SAMESITE,
        secure=_COOKIE_SECURE,
    )
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    return {"authenticated": verify_session(request.cookies.get(SESSION_COOKIE_NAME))}
