"""Research Dashboard Backend 검증 (P34) — 체인·중복·스냅샷(결정금지)·패널(읽기전용)·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 스냅샷 무결성(is_decision=False). 패널 무결성
(is_readonly=True·유형 유효). 아티팩트 계보. **변경 없음.**
"""
from __future__ import annotations

from jarvis.research_dashboard_backend import ledger
from jarvis.research_dashboard_backend import models as M
from jarvis.research_dashboard_backend.models import GENESIS, content_hash, detect_cycle_check


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


def snapshot_integrity() -> dict:
    """스냅샷 무결성: 모든 스냅샷 is_decision=False(집계만·결정 권한 없음) + 패널 유형 유효."""
    issues: list = []
    for s in ledger.read_snapshots():
        if s.get("is_decision") is not False:
            issues.append(f"decision_snapshot:{s.get('snapshot_id')}")
        if s.get("panel_type") not in M.PANEL_TYPES:
            issues.append(f"invalid_snapshot_panel:{s.get('snapshot_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def panel_integrity() -> dict:
    """패널 무결성: 모든 패널 is_readonly=True + 유형 유효 + 위젯 유형 유효."""
    issues: list = []
    for p in ledger.read_panels():
        if p.get("is_readonly") is not True:
            issues.append(f"non_readonly_panel:{p.get('panel_id')}")
        if p.get("panel_type") not in M.PANEL_TYPES:
            issues.append(f"invalid_panel_type:{p.get('panel_id')}")
    for w in ledger.read_widgets():
        if w.get("panel_type") not in M.PANEL_TYPES:
            issues.append(f"invalid_widget_panel:{w.get('widget_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    issues: list = []
    for records, idf, label in ((ledger.read_panels(), "panel_id", "panel"),
                                (ledger.read_snapshots(), "snapshot_id", "snapshot"),
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
    snapshot = snapshot_integrity()
    panel = panel_integrity()
    duplicate = duplicate_integrity()
    lineage = lineage_integrity()
    ok = ok and snapshot["ok"] and panel["ok"] and duplicate["ok"] and lineage["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "snapshot": snapshot, "panel": panel,
            "duplicate": duplicate, "lineage": lineage}


def replay(engine, now="") -> dict:
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    s1 = engine.create_snapshot("STATISTICS", now, commit=False)
    s2 = engine.create_snapshot("STATISTICS", now, commit=False)
    return {"deterministic": r1.to_dict() == r2.to_dict() and s1.to_dict() == s2.to_dict(),
            "panel_count": r1.panel_count, "snapshot_count": r1.snapshot_count}
