"""Operations 검증 (P9.2) — 해시체인 무결성·변조 탐지·중복 탐지·리플레이 일치. 읽기전용.

각 원장에 대해: previous_hash 링크(직전 record_hash) + record_hash 재계산(콘텐츠 변조 탐지) +
id 중복 탐지. replay: 동일 (report, now) 재처리 → 동일 산출(결정성). **변경/집행 없음.**
"""
from __future__ import annotations

from jarvis.operations import ledger
from jarvis.operations.models import GENESIS, content_hash


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
    """단일 원장 검증. which = ledger.ALERTS/INCIDENTS/... (파일명, id필드) 튜플."""
    filename, id_field = which
    from jarvis.operations.ledger import _read  # noqa: PLC0415
    return _verify_records(_read(filename), id_field)


def verify_chain() -> dict:
    """전 원장 검증. 하나라도 깨지면 실패(어느 원장인지 포함)."""
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results}


def replay(engine, report, now: str = "") -> dict:
    """동일 (report, now) 두 번 처리 → 동일 산출(결정성 확인). commit 없음(관측만)."""
    r1 = engine.process(report, now, commit=False)
    r2 = engine.process(report, now, commit=False)
    same = (r1["alerts"] == r2["alerts"]
            and [i["record_hash"] for i in r1["incidents_opened"]]
            == [i["record_hash"] for i in r2["incidents_opened"]]
            and [e["record_hash"] for e in r1["escalations"]]
            == [e["record_hash"] for e in r2["escalations"]])
    return {"deterministic": same,
            "n_alerts": len(r1["alerts"]),
            "alert_hashes": [a["record_hash"] for a in r1["alerts"]]}
