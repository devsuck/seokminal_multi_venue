"""Research Insight Intelligence 검증 (P28) — 체인·중복·통찰 생애주기·해석·증거·공백·관계·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 통찰 생애주기(CREATED 시작). 중복 통찰(genesis
유일). 해석/증거 무결성(알려진 통찰 참조·증거 유형 유효). 공백/관계 무결성(유형 유효). 아티팩트 계보(missing parent·broken
reference·순환). **변경 없음.**
"""
from __future__ import annotations

from jarvis.research_insight_intelligence import ledger
from jarvis.research_insight_intelligence import models as M
from jarvis.research_insight_intelligence.models import GENESIS, content_hash, detect_cycle_check


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


def verify_ledger(which) -> dict:
    filename, id_field = which
    return _verify_records(ledger.read_jsonl(filename), id_field)


def _group(records, key) -> dict:
    out: dict = {}
    for r in records:
        out.setdefault(r.get(key), []).append(r)
    return out


def insight_lifecycle_integrity() -> dict:
    """통찰 생애주기 전이 합법성(CREATED 시작)."""
    issues: list = []
    for iid, evs in sorted(_group(ledger.read_insight_events(), "insight_id").items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != M.I_CREATED:
                    issues.append(f"bad_initial:{iid}:{to}")
            elif not M.can_insight_transition(prev, to):
                issues.append(f"invalid_transition:{iid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    """중복 방지: 통찰 genesis 유일 + 맥락/공백/관계/리포트 id 유일."""
    issues: list = []
    seen: set = set()
    for ev in ledger.read_insight_events():
        if ev.get("from_state") == GENESIS:
            iid = ev.get("insight_id")
            if iid in seen:
                issues.append(f"duplicate_insight:{iid}")
            seen.add(iid)
    for records, idf, label in ((ledger.read_contexts(), "context_id", "context"),
                                (ledger.read_research_gaps(), "gap_id", "gap"),
                                (ledger.read_relationships(), "relationship_id", "relationship"),
                                (ledger.read_reports(), "report_id", "report")):
        s2: set = set()
        for r in records:
            rid = r.get(idf)
            if rid in s2:
                issues.append(f"duplicate_{label}:{rid}")
            s2.add(rid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def interpretation_integrity() -> dict:
    """해석/증거 무결성: 알려진 통찰 참조 + 증거 유형 유효."""
    issues: list = []
    ins_ids = set(ledger.insight_ids())
    for it in ledger.read_interpretations():
        if it.get("insight_id") not in ins_ids:
            issues.append(f"orphan_interpretation:{it.get('interpretation_id')}")
    for el in ledger.read_evidence_links():
        if el.get("insight_id") not in ins_ids:
            issues.append(f"orphan_evidence:{el.get('evidence_link_id')}")
        if el.get("evidence_type") not in M.EVIDENCE_TYPES:
            issues.append(f"invalid_evidence_type:{el.get('evidence_link_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def gap_integrity() -> dict:
    """공백 무결성: 공백 유형 유효."""
    issues: list = []
    for g in ledger.read_research_gaps():
        if g.get("gap_type") not in M.GAP_TYPES:
            issues.append(f"invalid_gap_type:{g.get('gap_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def relationship_integrity() -> dict:
    """관계 무결성: 관계 유형 유효 + 알려진 통찰 참조."""
    issues: list = []
    ins_ids = set(ledger.insight_ids())
    for r in ledger.read_relationships():
        if r.get("relation_type") not in M.RELATION_TYPES:
            issues.append(f"invalid_relation_type:{r.get('relationship_id')}")
        if r.get("source") not in ins_ids:
            issues.append(f"orphan_relationship_source:{r.get('relationship_id')}")
        if r.get("target") not in ins_ids:
            issues.append(f"orphan_relationship_target:{r.get('relationship_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def lineage_integrity() -> dict:
    """아티팩트 계보(parent): missing parent·broken reference·순환. Context→Insight→Interpretation/Relationship."""
    issues: list = []
    arts = ledger.read_artifacts()
    aids = {a.get("artifact_id") for a in arts}
    edges: list = []
    for a in arts:
        parent = a.get("parent_artifact")
        if parent:
            if parent not in aids:
                issues.append(f"missing_parent:{a.get('artifact_id')}")
            edges.append((a.get("artifact_id"), parent))
    if detect_cycle_check(edges):
        issues.append("cycle_artifact")
    return {"ok": not issues, "issues": sorted(set(issues))}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    insight = insight_lifecycle_integrity()
    duplicate = duplicate_integrity()
    interpretation = interpretation_integrity()
    gap = gap_integrity()
    relationship = relationship_integrity()
    lineage = lineage_integrity()
    ok = (ok and insight["ok"] and duplicate["ok"] and interpretation["ok"] and gap["ok"]
          and relationship["ok"] and lineage["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "insight_lifecycle": insight,
            "duplicate": duplicate, "interpretation": interpretation, "gap": gap,
            "relationship": relationship, "lineage": lineage}


def replay(engine, now="") -> dict:
    """동일 상태 요약/리포트 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    p1 = engine.generate_report("SYSTEM", now, commit=False)
    p2 = engine.generate_report("SYSTEM", now, commit=False)
    return {"deterministic": r1.to_dict() == r2.to_dict() and p1.to_dict() == p2.to_dict(),
            "insight_count": r1.insight_count, "gap_count": r1.gap_count}
