"""Research Strategy Generation 검증 (P29) — 체인·중복·세션/후보 생애주기·후보(선택금지)·신규성·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 세션/후보 생애주기(CREATED/PROPOSED 시작). 중복
genesis 유일. 후보 무결성(is_selected=False). 신규성/증거 무결성(알려진 후보 참조·유형 유효). 아티팩트 계보. **변경 없음.**
"""
from __future__ import annotations

from jarvis.research_strategy_generation import ledger
from jarvis.research_strategy_generation import models as M
from jarvis.research_strategy_generation.models import GENESIS, content_hash, detect_cycle_check


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


def session_lifecycle_integrity() -> dict:
    issues: list = []
    for sid, evs in sorted(_group(ledger.read_session_events(), "session_id").items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != M.S_CREATED:
                    issues.append(f"bad_initial:{sid}:{to}")
            elif not M.can_session_transition(prev, to):
                issues.append(f"invalid_transition:{sid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def candidate_lifecycle_integrity() -> dict:
    issues: list = []
    for cid, evs in sorted(_group(ledger.read_candidate_events(), "candidate_id").items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != M.C_PROPOSED:
                    issues.append(f"bad_initial:{cid}:{to}")
            elif not M.can_candidate_transition(prev, to):
                issues.append(f"invalid_transition:{cid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    issues: list = []
    for records, key, glabel in ((ledger.read_session_events(), "session_id", "session"),
                                 (ledger.read_candidate_events(), "candidate_id", "candidate")):
        seen: set = set()
        for ev in records:
            if ev.get("from_state") == GENESIS:
                gid = ev.get(key)
                if gid in seen:
                    issues.append(f"duplicate_{glabel}:{gid}")
                seen.add(gid)
    for records, idf, label in ((ledger.read_hypotheses(), "hypothesis_id", "hypothesis"),
                                (ledger.read_reports(), "report_id", "report")):
        s2: set = set()
        for r in records:
            rid = r.get(idf)
            if rid in s2:
                issues.append(f"duplicate_{label}:{rid}")
            s2.add(rid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def candidate_selection_integrity() -> dict:
    """후보 선택 방지: 모든 후보 이벤트 is_selected=False(생성만·자동 선택 금지)."""
    issues: list = []
    for ev in ledger.read_candidate_events():
        if ev.get("is_selected") is not False:
            issues.append(f"selected_candidate:{ev.get('candidate_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def reference_integrity() -> dict:
    """신규성/증거 무결성: 알려진 후보 참조 + 증거 유형 유효."""
    issues: list = []
    cand_ids = set(ledger.candidate_ids())
    for n in ledger.read_novelty():
        if n.get("candidate_id") not in cand_ids:
            issues.append(f"orphan_novelty:{n.get('novelty_id')}")
    for e in ledger.read_evidence():
        if e.get("candidate_id") not in cand_ids:
            issues.append(f"orphan_evidence:{e.get('evidence_id')}")
        if e.get("evidence_type") not in M.EVIDENCE_TYPES:
            issues.append(f"invalid_evidence_type:{e.get('evidence_id')}")
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
    session = session_lifecycle_integrity()
    candidate = candidate_lifecycle_integrity()
    duplicate = duplicate_integrity()
    selection = candidate_selection_integrity()
    reference = reference_integrity()
    lineage = lineage_integrity()
    ok = (ok and session["ok"] and candidate["ok"] and duplicate["ok"] and selection["ok"]
          and reference["ok"] and lineage["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "session_lifecycle": session,
            "candidate_lifecycle": candidate, "duplicate": duplicate, "selection": selection,
            "reference": reference, "lineage": lineage}


def replay(engine, now="") -> dict:
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    p1 = engine.generate_report("SYSTEM", now, commit=False)
    p2 = engine.generate_report("SYSTEM", now, commit=False)
    return {"deterministic": r1.to_dict() == r2.to_dict() and p1.to_dict() == p2.to_dict(),
            "candidate_count": r1.candidate_count, "novelty_count": r1.novelty_count}
