"""Research Ingestion 검증 (P53) — 수집 감사 체인·중복·재현. 읽기전용."""
from __future__ import annotations

from jarvis.research_ingestion import ledger
from jarvis.research_ingestion.models import GENESIS, OUTCOMES, content_hash


def _verify_records(records, id_field) -> dict:
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


def outcome_integrity() -> dict:
    issues = []
    for r in ledger.read_ingestions():
        if r.get("outcome") not in OUTCOMES:
            issues.append(f"bad_outcome:{r.get('ingestion_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def verify_chain() -> dict:
    chain = _verify_records(ledger.read_ingestions(), "ingestion_id")
    outcome = outcome_integrity()
    ok = chain["ok"] and outcome["ok"]
    return {"ok": ok, "n": chain.get("n", 0), "ledgers": {"ring_ingestions.jsonl": chain},
            "outcome": outcome}


def replay(engine, now="") -> dict:
    s1 = engine.summary(now)
    s2 = engine.summary(now)
    return {"deterministic": s1.to_dict() == s2.to_dict(), "ingestion_count": s1.ingestion_count}
