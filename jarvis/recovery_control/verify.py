"""Recovery Control 검증 (P9.4) — 해시체인 무결성·변조 탐지·중복 탐지·리플레이 일치. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(콘텐츠 변조 탐지) + id 중복 탐지.
replay: 동일 입력 재평가 → 동일 준비도 산출(결정성). **변경/복구/집행 없음.**
"""
from __future__ import annotations

from jarvis.recovery_control import ledger
from jarvis.recovery_control.models import GENESIS, content_hash


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
    from jarvis.recovery_control.ledger import _read  # noqa: PLC0415
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


def replay(engine, now: str = "", **kw) -> dict:
    """동일 입력 두 번 평가 → 동일 산출(결정성). commit 없음(관측만)."""
    r1 = engine.assess(now, commit=False, **kw)
    r2 = engine.assess(now, commit=False, **kw)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "overall_status": r1.overall_status,
            "report_hash": r1.report_hash,
            "checklist_hash": r1.checklist_hash,
            "evidence_hash": r1.evidence_hash}
