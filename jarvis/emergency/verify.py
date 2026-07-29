"""Emergency 검증 (P9.3) — 해시체인 무결성·변조 탐지·중복 탐지·리플레이 일치. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(콘텐츠 변조 탐지) + id 중복 탐지.
replay: 동일 입력 재판정 → 동일 산출(결정성). **변경/집행/킬스위치 작동 없음.**
"""
from __future__ import annotations

from jarvis.emergency import ledger
from jarvis.emergency.models import GENESIS, content_hash


def _verify_records(records: list, id_field: str) -> dict:
    if not records:
        return {"ok": True, "n": 0, "reason": "empty"}
    prev = GENESIS
    seen = set()
    for i, r in enumerate(records):
        if r.get("previous_hash") != prev:
            return {"ok": False, "broken_at": i, "reason": "previous_hash_broken"}
        if not r.get("record_hash"):
            return {"ok": False, "broken_at": i, "reason": "missing_record_hash"}
        rid = r.get(id_field)
        if rid in seen:
            return {"ok": False, "broken_at": i, "reason": "duplicate_id"}
        if content_hash(r) != r.get("record_hash"):
            return {"ok": False, "broken_at": i, "reason": "record_hash_mismatch"}
        seen.add(rid)
        prev = r["record_hash"]
    return {"ok": True, "n": len(records), "reason": "chain_intact"}


def verify_ledger(which) -> dict:
    filename, id_field = which
    from jarvis.emergency.ledger import _read  # noqa: PLC0415
    return _verify_records(_read(filename), id_field)


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results}


def replay(engine, *, health=None, risk=None, incidents=None, escalations=None,
           now: str = "") -> dict:
    """동일 입력 두 번 판정 → 동일 산출(결정성). commit 없음(관측만)."""
    d1 = engine.assess(health=health, risk=risk, incidents=incidents,
                       escalations=escalations, now=now, commit=False)
    d2 = engine.assess(health=health, risk=risk, incidents=incidents,
                       escalations=escalations, now=now, commit=False)
    return {"deterministic": d1.to_dict() == d2.to_dict(),
            "emergency_state": d1.emergency_state,
            "record_hash": d1.record_hash}
