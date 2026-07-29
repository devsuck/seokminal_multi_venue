"""Model Management 검증 (P43) — 체인·중복·모델 생애주기·버전 계보·검증·성능·계보·재현. 읽기전용."""
from __future__ import annotations

from jarvis.model_management import ledger
from jarvis.model_management import models as M
from jarvis.model_management.models import GENESIS, content_hash, detect_cycle_check


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


def model_lifecycle_integrity() -> dict:
    issues: list = []
    for mid, evs in sorted(_group(ledger.read_model_events(), "model_id").items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != M.M_REGISTERED:
                    issues.append(f"bad_initial:{mid}:{to}")
            elif not M.can_model_transition(prev, to):
                issues.append(f"invalid_transition:{mid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    issues: list = []
    seen: set = set()
    for ev in ledger.read_model_events():
        if ev.get("from_state") == GENESIS:
            mid = ev.get("model_id")
            if mid in seen:
                issues.append(f"duplicate_model:{mid}")
            seen.add(mid)
    for records, idf, label in ((ledger.read_versions(), "version_id", "version"),
                                (ledger.read_reports(), "report_id", "report")):
        s2: set = set()
        for r in records:
            rid = r.get(idf)
            if rid in s2:
                issues.append(f"duplicate_{label}:{rid}")
            s2.add(rid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def version_lineage_integrity() -> dict:
    issues: list = []
    mdl_ids = set(ledger.model_ids())
    vids = {v.get("version_id") for v in ledger.read_versions()}
    edges = []
    for v in ledger.read_versions():
        if v.get("model_id") not in mdl_ids:
            issues.append(f"orphan_version:{v.get('version_id')}")
        parent = v.get("parent_version")
        if parent:
            if parent not in vids:
                issues.append(f"missing_parent_version:{v.get('version_id')}")
            edges.append((v.get("version_id"), parent))
    if detect_cycle_check(edges):
        issues.append("cycle_version")
    return {"ok": not issues, "issues": sorted(set(issues))}


def validation_integrity() -> dict:
    issues: list = []
    mdl_ids = set(ledger.model_ids())
    for v in ledger.read_validations():
        if v.get("check") not in M.VALIDATION_CHECKS:
            issues.append(f"invalid_check:{v.get('validation_id')}")
        if v.get("model_id") not in mdl_ids:
            issues.append(f"orphan_validation:{v.get('validation_id')}")
    for p in ledger.read_performance():
        if p.get("model_id") not in mdl_ids:
            issues.append(f"orphan_performance:{p.get('performance_id')}")
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
    model = model_lifecycle_integrity()
    duplicate = duplicate_integrity()
    version = version_lineage_integrity()
    validation = validation_integrity()
    lineage = lineage_integrity()
    ok = (ok and model["ok"] and duplicate["ok"] and version["ok"] and validation["ok"]
          and lineage["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "model_lifecycle": model,
            "duplicate": duplicate, "version_lineage": version, "validation": validation,
            "lineage": lineage}


def replay(engine, now="") -> dict:
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    p1 = engine.generate_report("SYSTEM", now, commit=False)
    p2 = engine.generate_report("SYSTEM", now, commit=False)
    return {"deterministic": r1.to_dict() == r2.to_dict() and p1.to_dict() == p2.to_dict(),
            "model_count": r1.model_count, "version_count": r1.version_count}
