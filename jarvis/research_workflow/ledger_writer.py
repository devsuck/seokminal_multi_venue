"""Writer Authority Protocol (P202-seed) — 원장 쓰기 권한 계약. **계약만, 인프라 확장 없음.**

목적: "한 번에 하나의 활성 writer"를 보장하는 최소 리스(lease) 계약. 특정 머신에 고정하지 않고,
**writer 추상화**를 둔다 → 저장 백엔드(JSONL 지금 → SQLite/PG 나중)는 교체 가능.

**의도적으로 최소**: 쿠버네티스급 분산 운영이 아님. 파일 기반 리스(`writer_lock.json`) + 인터페이스만.
현재 Jarvis(단일 사용자·JSONL·서버 아님)에 맞춘 규모. 계약은 다중노드 대비, 구현은 지금 필요만큼.

원칙(§Constitution): 통합·조율만 · 결정적(리스 파일은 상태, 원장 아님) · 새 DB/원장 없음 · 거래·집행 없음.
"""
from __future__ import annotations

import json

LOCK_FILE = "writer_lock.json"
DEFAULT_TTL_SECONDS = 3600


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _lock_path():
    from jarvis.config import state_path
    return state_path(LOCK_FILE)


# ── 백엔드 교체 가능 드라이버(현재 JSONL/파일; 나중 SQLite/PG로 교체) ──
class _FileDriver:
    """writer_lock.json 읽기/쓰기 — 저장 백엔드 추상화(교체 가능)."""

    def read(self) -> dict:
        try:
            with open(_lock_path(), encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def write(self, lease: dict) -> None:
        from jarvis.config import ensure_state_dir
        ensure_state_dir()
        with open(_lock_path(), "w", encoding="utf-8") as f:
            json.dump(lease, f, ensure_ascii=False, indent=2)

    def clear(self) -> None:
        lease = self.read()
        self.write({"active_writer": None, "released_from": lease.get("active_writer"),
                    "released_at": lease.get("acquired_at")})


class WriterAuthority:
    """원장 쓰기 권한 계약 — 유효 리스 보유자만 append 가능. 백엔드 교체 가능. 실행 권한 없음."""

    def __init__(self, driver=None) -> None:
        self._driver = driver or _FileDriver()

    def current_lease(self) -> dict:
        return self._driver.read()

    def _valid(self, lease: dict, now: str) -> bool:
        """리스가 살아있는지(만료 전) — now 는 호출자가 주입(결정적 테스트 가능)."""
        if not lease or not lease.get("active_writer"):
            return False
        exp = str(lease.get("lease_expiry", ""))
        return not (exp and now and now > exp)

    def has_authority(self, node_id: str, *, now: str) -> bool:
        lease = self.current_lease()
        return bool(self._valid(lease, now) and lease.get("active_writer") == node_id)

    def acquire(self, node_id: str, session_id: str = "", *, now: str,
                lease_expiry: str = "", ttl_seconds: int = DEFAULT_TTL_SECONDS) -> dict:
        """쓰기 권한 획득. 다른 노드가 유효 리스 보유 중이면 거부(rejected). 결정적(now 주입)."""
        lease = self.current_lease()
        if self._valid(lease, now) and lease.get("active_writer") not in (None, node_id):
            return {"acquired": False, "rejected": True,
                    "reason": f"active writer '{lease.get('active_writer')}' holds a valid lease",
                    "current": lease, "is_advisory": True, "is_decision": False}
        new = {"active_writer": node_id, "node_id": node_id, "session_id": session_id,
               "acquired_at": now, "lease_expiry": lease_expiry or _expiry(now, ttl_seconds)}
        self._driver.write(new)
        return {"acquired": True, "rejected": False, "lease": new,
                "is_advisory": True, "is_decision": False}

    def release(self, node_id: str) -> dict:
        lease = self.current_lease()
        if lease.get("active_writer") not in (None, node_id):
            return {"released": False, "reason": "not lease holder", "is_decision": False}
        self._driver.clear()
        return {"released": True, "is_advisory": True, "is_decision": False}

    def guarded_append(self, node_id: str, append_fn, *, now: str):
        """유효 권한 보유 시에만 append_fn() 실행. 아니면 거부(원장 무변경). 계약 강제."""
        if not self.has_authority(node_id, now=now):
            return {"rejected": True, "reason": "no valid write authority (acquire lease first)",
                    "is_advisory": True, "is_decision": False}
        result = append_fn()
        return {"rejected": False, "result": result, "is_advisory": True, "is_decision": False}


def _expiry(now: str, ttl_seconds: int) -> str:
    """now(ISO Z) + ttl → 만료 ISO. now 파싱 실패 시 빈 문자열(만료 없음)."""
    from datetime import datetime, timedelta, timezone
    try:
        dt = datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return (dt + timedelta(seconds=ttl_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return ""


def default_authority() -> WriterAuthority:
    return WriterAuthority()
