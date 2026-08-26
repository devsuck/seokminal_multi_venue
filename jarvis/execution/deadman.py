"""데드맨 스위치 — 사람이 DEADMAN_DAYS(기본 7일) 이상 응답 없으면 신규 진입 차단.

헌법 v2 원칙 "무응답 = 아무 것도 안 함"의 구현체. heartbeat가 한 번도 없거나
너무 오래됐으면 fail-safe로 만료 취급(진입 차단) — 서버 재시작은 heartbeat를
자동 갱신하지 않는다(그러면 재시작마다 타이머가 리셋돼 안전장치가 무력화됨).
사람이 POST /steward/heartbeat로 직접(또는 Phase 5 steward가 건강 확인 후)
갱신해야 함. 청산(route_close)은 이 모듈을 거치지 않음 — 매도는 항상 허용.
"""
from __future__ import annotations

import datetime as _dt
import json
import os

from jarvis.config import state_path

_HEARTBEAT_FILE = "deadman_heartbeat.json"


def deadman_days() -> int:
    return int(os.environ.get("DEADMAN_DAYS", "7"))


def record_heartbeat() -> _dt.datetime:
    now = _dt.datetime.now(_dt.timezone.utc)
    with open(state_path(_HEARTBEAT_FILE), "w") as f:
        json.dump({"ts": now.isoformat()}, f)
    return now


def last_heartbeat() -> _dt.datetime | None:
    try:
        with open(state_path(_HEARTBEAT_FILE)) as f:
            return _dt.datetime.fromisoformat(json.load(f)["ts"])
    except (FileNotFoundError, KeyError, ValueError):
        return None


def is_expired() -> bool:
    hb = last_heartbeat()
    if hb is None:
        return True
    return _dt.datetime.now(_dt.timezone.utc) - hb > _dt.timedelta(days=deadman_days())
