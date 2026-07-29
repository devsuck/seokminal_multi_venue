"""Research OS Core 검증 (P10.30) — 체인·변조·중복·도메인 의존성 무결성·결정적 재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 도메인 의존성 DAG: 미지 노드·순환.
**변경/실행/거래/배포/할당/변경 없음.**
"""
from __future__ import annotations

from jarvis.research_os_core import ledger
from jarvis.research_os_core.models import (
    DOMAIN_DEPS,
    DOMAINS,
    GENESIS,
    content_hash,
    dependency_issues,
)


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


def domain_dependency_integrity() -> dict:
    """도메인 데이터 흐름 DAG 무결성: 미지 노드·순환 탐지."""
    issues = dependency_issues(list(DOMAIN_DEPS), list(DOMAINS))
    return {"ok": not issues, "issues": issues, "node_count": len(DOMAINS),
            "edge_count": len(DOMAIN_DEPS)}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    dep = domain_dependency_integrity()
    ok = ok and dep["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "dependency": dep}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "module_count": r1.module_count, "snapshot_count": r1.snapshot_count,
            "report_count": r1.report_count}
