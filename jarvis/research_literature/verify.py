"""Research Literature 검증 (P11.3) — 체인·변조·중복·인용 그래프·계보·지식 무결성·결정적 재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 인용: dangling·자기인용. 개념 계보: dangling·
순환. 논문 중복(fingerprint) 후보. **변경/실행/전략 생성 없음.**
"""
from __future__ import annotations

from jarvis.research_literature import ledger
from jarvis.research_literature.models import (
    GENESIS,
    content_hash,
    detect_cycle,
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


def citation_graph_integrity() -> dict:
    """인용 그래프: dangling 참조·자기 인용 탐지."""
    issues: list = []
    pids = {p.get("paper_id") for p in ledger.read_papers()}
    for c in ledger.read_citations():
        if c.get("citing_paper") == c.get("cited_paper"):
            issues.append(f"self_citation:{c.get('citation_id')}")
        for f in ("citing_paper", "cited_paper"):
            if c.get(f) not in pids:
                issues.append(f"dangling:{c.get('citation_id')}:{c.get(f)}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def lineage_integrity() -> dict:
    """개념 계보(parent) 무결성: dangling·순환."""
    issues: list = []
    cids = {c.get("concept_id") for c in ledger.read_concepts()}
    pm = {c.get("concept_id"): c.get("parent_concept") for c in ledger.read_concepts()
          if c.get("parent_concept")}
    for cid, parent in sorted(pm.items()):
        if parent not in cids:
            issues.append(f"dangling:{cid}->{parent}")
    cyc = detect_cycle(list(pm.items()))
    if cyc:
        issues.append("cycle:" + "->".join(cyc))
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_papers() -> dict:
    """정규화 제목(fingerprint) 공유 논문 중복 후보."""
    by_fp: dict = {}
    for p in ledger.read_papers():
        by_fp.setdefault(p.get("fingerprint"), []).append(p.get("paper_id"))
    dups = [sorted(ids) for fp, ids in sorted(by_fp.items()) if len(ids) > 1]
    return {"ok": not dups, "duplicates": dups}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    citation = citation_graph_integrity()
    lineage = lineage_integrity()
    dup = duplicate_papers()
    ok = ok and citation["ok"] and lineage["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "citation": citation, "lineage": lineage,
            "duplicates": dup}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "paper_count": r1.paper_count, "concept_count": r1.concept_count,
            "citation_count": r1.citation_count}
