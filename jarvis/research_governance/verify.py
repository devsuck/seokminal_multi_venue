"""Research Governance 검증 (P10.2) — 체인 무결성·변조·중복·리플레이·아티팩트 계보. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 아티팩트: 부모 존재·사이클 없음.
replay: 동일 상태 리포트 재계산 → 동일 산출(결정성). **변경/실행/거래 없음.**
"""
from __future__ import annotations

from jarvis.research_governance import ledger
from jarvis.research_governance.models import GENESIS, content_hash


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
    return _verify_records(ledger.read_jsonl(filename), id_field)


def artifact_linkage() -> dict:
    """아티팩트 계보 무결성: 부모 존재·사이클 없음."""
    arts = ledger.read_artifacts()
    ids = {a.get("artifact_id") for a in arts}
    parent_of = {a.get("artifact_id"): a.get("parent_artifact") for a in arts}
    for aid, parent in parent_of.items():
        if parent and parent not in ids:
            return {"ok": False, "reason": "dangling_parent", "artifact": aid, "parent": parent}
    # 사이클 검사(부모 체인)
    for aid in sorted(ids):
        seen = set()
        cur = aid
        while cur:
            if cur in seen:
                return {"ok": False, "reason": "cycle", "artifact": aid}
            seen.add(cur)
            cur = parent_of.get(cur, "")
    return {"ok": True, "reason": "linkage_intact", "n_artifacts": len(arts)}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    link = artifact_linkage()
    ok = ok and link["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "artifact_linkage": link}


def replay(engine, now: str = "") -> dict:
    """동일 상태 연구 리포트 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.generate_research_report(now)
    r2 = engine.generate_research_report(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "strategy_count": r1.strategy_count, "state_distribution": r1.state_distribution}
