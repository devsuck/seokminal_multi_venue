"""Research Validation 검증 (P10.9) — 체인 무결성·변조·중복·리플레이·계보 검증. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 계보: dangling reference·아티팩트
dangling parent·순환 탐지. replay: 동일 상태 감사 요약 재계산 → 동일 산출. **변경/실행/배포/승인 없음.**
"""
from __future__ import annotations

from jarvis.research_validation import ledger
from jarvis.research_validation.models import GENESIS, content_hash, detect_cycle, output_hash


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


def lineage_validation() -> dict:
    """Target→Validation→Checklist/Evidence/Replay/Lineage/Score 계보 검증.

    dangling checklist/evidence/replay/score(미존재 검증)·아티팩트 dangling parent·순환 탐지.
    """
    issues: list = []
    validation_ids = {v.get("validation_id") for v in ledger.distinct_validations()}

    def _check(records, id_field, label):
        for r in records:
            if r.get("validation_id") and r.get("validation_id") not in validation_ids:
                issues.append(f"dangling_{label}:{r.get(id_field)}")

    _check(ledger.read_checklists(), "checklist_id", "checklist")
    _check(ledger.read_evidence(), "evidence_id", "evidence")
    _check(ledger.read_replay_reports(), "replay_id", "replay")
    _check(ledger.read_lineage_reports(), "lineage_report_id", "lineage_report")
    _check(ledger.read_scores(), "score_id", "score")

    arts = ledger.read_artifacts()
    ids = {a.get("artifact_id") for a in arts}
    edges = []
    for a in arts:
        parent = a.get("parent_artifact")
        if parent:
            if parent not in ids:
                issues.append(f"broken_lineage:{a.get('artifact_id')}->{parent}")
            edges.append((a.get("artifact_id"), parent))
    cycle = detect_cycle(edges)
    if cycle:
        issues.append("circular_dependency:" + "->".join(cycle))
    return {"ok": not issues, "issues": sorted(set(issues)), "n_artifacts": len(arts)}


def replay_consistency() -> dict:
    """기록된 리플레이 리포트의 REPRODUCIBLE 판정이 해시 일치와 일관되는지 검증(변조 탐지)."""
    issues: list = []
    for r in ledger.read_replay_reports():
        same = r.get("original_output_hash") == r.get("replay_output_hash")
        declared = r.get("result") == "REPRODUCIBLE"
        if same != declared:
            issues.append(f"inconsistent_replay:{r.get('replay_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def verify_chain() -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    lineage = lineage_validation()
    replay = replay_consistency()
    ok = ok and lineage["ok"] and replay["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lineage": lineage, "replay": replay}


def replay(engine, now: str = "") -> dict:
    """동일 상태 감사 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.generate_audit_summary(now)
    r2 = engine.generate_audit_summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "validation_count": r1.validation_count, "mean_score": r1.mean_score,
            "non_reproducible_count": r1.non_reproducible_count}
