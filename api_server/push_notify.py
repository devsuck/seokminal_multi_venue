"""Web Push 알림 — VAPID 기반, PWA 구독자에게 alert 이벤트 전송.

lv6_notify.py(Telegram)와 동일 철학: 메인 스레드 절대 블로킹 안 함(daemon 스레드
발송), 구독 없거나 키 미설정이면 조용히 스킵. 구독 목록은 재시작 살아남게
jarvis/_state/push_subscriptions.json에 저장(watchdog.json과 동일한 단순
read-all/write-all 패턴 — 구독자 수가 개인용 규모라 락 불필요).
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

_log = logging.getLogger(__name__)

_STATE_DIR = Path(__file__).resolve().parent.parent / "jarvis" / "_state"
_SUBS_PATH = _STATE_DIR / "push_subscriptions.json"


def _load_subs() -> dict[str, dict]:
    if not _SUBS_PATH.exists():
        return {}
    try:
        return json.loads(_SUBS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_subs(subs: dict[str, dict]) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    _SUBS_PATH.write_text(json.dumps(subs, ensure_ascii=False, indent=2))


def add_subscription(sub: dict) -> None:
    subs = _load_subs()
    subs[sub["endpoint"]] = sub
    _save_subs(subs)


def remove_subscription(endpoint: str) -> None:
    subs = _load_subs()
    if subs.pop(endpoint, None) is not None:
        _save_subs(subs)


def get_vapid_public_key() -> str | None:
    return os.environ.get("VAPID_PUBLIC_KEY") or None


def _send_one(sub: dict, title: str, body: str) -> None:
    from pywebpush import webpush, WebPushException

    private_key = os.environ.get("VAPID_PRIVATE_KEY", "")
    subject = os.environ.get("VAPID_SUBJECT", "mailto:admin@seokminal.dev")
    if not private_key:
        _log.debug("[Push] VAPID_PRIVATE_KEY 미설정 — 스킵")
        return
    try:
        webpush(
            subscription_info=sub,
            data=json.dumps({"title": title, "body": body}),
            vapid_private_key=private_key,
            vapid_claims={"sub": subject},
        )
    except WebPushException as e:
        status = getattr(e.response, "status_code", None)
        if status in (404, 410):
            # 구독 만료/취소 — 죽은 구독 정리
            remove_subscription(sub["endpoint"])
        else:
            _log.warning("[Push] 전송 실패: %s", e)


def send(title: str, body: str) -> None:
    """비동기 전송(구독마다 daemon 스레드) — 등록된 전체 구독에 팬아웃."""
    for sub in _load_subs().values():
        threading.Thread(target=_send_one, args=(sub, title, body), daemon=True).start()
