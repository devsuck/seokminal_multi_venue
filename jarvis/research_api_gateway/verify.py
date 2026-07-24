"""Research API Gateway 검증 (P33) — 체인·중복·읽기전용·서비스유형·응답참조·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 읽기전용 무결성(모든 서비스/응답 is_readonly=True·
금지 서비스 유형 없음). 응답 무결성(알려진 질의 참조). 아티팩트 계보. **변경 없음.**
"""
from __future__ import annotations

from jarvis.research_api_gateway import ledger
from jarvis.research_api_gateway import models as M
from jarvis.research_api_gateway.models import GENESIS, content_hash, detect_cycle_check


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


def readonly_integrity() -> dict:
    """읽기전용 무결성: 모든 서비스/응답 is_readonly=True + 금지 서비스 유형 노출 없음."""
    issues: list = []
    for s in ledger.read_services():
        if s.get("is_readonly") is not True:
            issues.append(f"non_readonly_service:{s.get('service_id')}")
        if s.get("service_type") in M.FORBIDDEN_SERVICE_TYPES:
            issues.append(f"forbidden_service:{s.get('service_id')}")
        if s.get("service_type") not in M.SERVICE_TYPES:
            issues.append(f"invalid_service_type:{s.get('service_id')}")
    for r in ledger.read_responses():
        if r.get("is_readonly") is not True:
            issues.append(f"non_readonly_response:{r.get('response_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def response_integrity() -> dict:
    """응답 무결성: 알려진 질의 참조 + 서비스 유형 유효."""
    issues: list = []
    query_ids = {q.get("query_id") for q in ledger.read_queries()}
    for r in ledger.read_responses():
        if r.get("query_id") not in query_ids:
            issues.append(f"orphan_response:{r.get('response_id')}")
        if r.get("service_type") not in M.SERVICE_TYPES:
            issues.append(f"invalid_response_service:{r.get('response_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    issues: list = []
    for records, idf, label in ((ledger.read_services(), "service_id", "service"),
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
    readonly = readonly_integrity()
    response = response_integrity()
    duplicate = duplicate_integrity()
    lineage = lineage_integrity()
    ok = ok and readonly["ok"] and response["ok"] and duplicate["ok"] and lineage["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "readonly": readonly, "response": response,
            "duplicate": duplicate, "lineage": lineage}


def replay(engine, now="") -> dict:
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    s1 = engine.get_summary()
    s2 = engine.get_summary()
    return {"deterministic": r1.to_dict() == r2.to_dict() and s1 == s2,
            "service_count": r1.service_count, "query_count": r1.query_count}
