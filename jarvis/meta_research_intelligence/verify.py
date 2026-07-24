"""Meta Research Intelligence 검증 (P30) — 체인·중복·지표(관찰만)·기회(적용금지)·품질·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 지표 무결성(is_observation=True). 기회 무결성
(is_applied=False). 품질/관찰 무결성(차원·측면 유효). 아티팩트 계보. **변경 없음.**
"""
from __future__ import annotations

from jarvis.meta_research_intelligence import ledger
from jarvis.meta_research_intelligence import models as M
from jarvis.meta_research_intelligence.models import GENESIS, content_hash, detect_cycle_check


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


def metric_integrity() -> dict:
    """지표 무결성: 모든 메타 지표 is_observation=True(관찰만·자동 최적화 금지)."""
    issues: list = []
    for m in ledger.read_meta_metrics():
        if m.get("is_observation") is not True:
            issues.append(f"non_observation_metric:{m.get('metric_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def opportunity_integrity() -> dict:
    """기회 무결성: 모든 최적화 기회 is_applied=False(기록만·자동 적용 금지) + 영역 유효."""
    issues: list = []
    for o in ledger.read_opportunities():
        if o.get("is_applied") is not False:
            issues.append(f"applied_opportunity:{o.get('opportunity_id')}")
        if o.get("area") not in M.OPPORTUNITY_AREAS:
            issues.append(f"invalid_area:{o.get('opportunity_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def quality_integrity() -> dict:
    """품질/관찰 무결성: 차원·측면 유효."""
    issues: list = []
    for q in ledger.read_quality_records():
        if q.get("dimension") not in M.QUALITY_DIMENSIONS:
            issues.append(f"invalid_dimension:{q.get('quality_id')}")
    for o in ledger.read_observations():
        if o.get("aspect") not in M.OBSERVATION_ASPECTS:
            issues.append(f"invalid_aspect:{o.get('observation_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    """중복 방지: 품질/기회/관찰/리포트 id 유일."""
    issues: list = []
    for records, idf, label in ((ledger.read_quality_records(), "quality_id", "quality"),
                                (ledger.read_opportunities(), "opportunity_id", "opportunity"),
                                (ledger.read_observations(), "observation_id", "observation"),
                                (ledger.read_reports(), "report_id", "report")):
        s2: set = set()
        for r in records:
            rid = r.get(idf)
            if rid in s2:
                issues.append(f"duplicate_{label}:{rid}")
            s2.add(rid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def lineage_integrity() -> dict:
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
    metric = metric_integrity()
    opportunity = opportunity_integrity()
    quality = quality_integrity()
    duplicate = duplicate_integrity()
    lineage = lineage_integrity()
    ok = (ok and metric["ok"] and opportunity["ok"] and quality["ok"] and duplicate["ok"]
          and lineage["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "metric": metric, "opportunity": opportunity,
            "quality": quality, "duplicate": duplicate, "lineage": lineage}


def replay(engine, now="") -> dict:
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    m1 = engine.compute_meta_metrics(now, commit=False)
    m2 = engine.compute_meta_metrics(now, commit=False)
    return {"deterministic": r1.to_dict() == r2.to_dict() and m1 == m2,
            "metric_count": r1.metric_count, "opportunity_count": r1.opportunity_count}
