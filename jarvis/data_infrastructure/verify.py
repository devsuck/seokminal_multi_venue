"""Data Infrastructure 검증 (P41) — 체인·중복·데이터셋 생애주기·버전 계보·품질·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조) + id 중복. 데이터셋 생애주기(CREATED 시작). 중복 데이터셋(genesis
유일). 버전 계보(parent_version)·품질 차원 유효. 아티팩트 계보. **변경 없음.**
"""
from __future__ import annotations

from jarvis.data_infrastructure import ledger
from jarvis.data_infrastructure import models as M
from jarvis.data_infrastructure.models import GENESIS, content_hash, detect_cycle_check


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


def dataset_lifecycle_integrity() -> dict:
    issues: list = []
    for did, evs in sorted(_group(ledger.read_dataset_events(), "dataset_id").items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != M.D_CREATED:
                    issues.append(f"bad_initial:{did}:{to}")
            elif not M.can_dataset_transition(prev, to):
                issues.append(f"invalid_transition:{did}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    issues: list = []
    seen: set = set()
    for ev in ledger.read_dataset_events():
        if ev.get("from_state") == GENESIS:
            did = ev.get("dataset_id")
            if did in seen:
                issues.append(f"duplicate_dataset:{did}")
            seen.add(did)
    for records, idf, label in ((ledger.read_sources(), "source_id", "source"),
                                (ledger.read_versions(), "version_id", "version"),
                                (ledger.read_reports(), "report_id", "report")):
        s2: set = set()
        for r in records:
            rid = r.get(idf)
            if rid in s2:
                issues.append(f"duplicate_{label}:{rid}")
            s2.add(rid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def version_lineage_integrity() -> dict:
    """버전 계보: parent_version 이 알려진 버전·순환 없음 + 데이터셋 참조."""
    issues: list = []
    ds_ids = set(ledger.dataset_ids())
    vids = {v.get("version_id") for v in ledger.read_versions()}
    edges = []
    for v in ledger.read_versions():
        if v.get("dataset_id") not in ds_ids:
            issues.append(f"orphan_version:{v.get('version_id')}")
        parent = v.get("parent_version")
        if parent:
            if parent not in vids:
                issues.append(f"missing_parent_version:{v.get('version_id')}")
            edges.append((v.get("version_id"), parent))
    if detect_cycle_check(edges):
        issues.append("cycle_version")
    return {"ok": not issues, "issues": sorted(set(issues))}


def quality_integrity() -> dict:
    """품질 무결성: 차원 유효 + 알려진 데이터셋 참조."""
    issues: list = []
    ds_ids = set(ledger.dataset_ids())
    for q in ledger.read_quality():
        if q.get("dimension") not in M.QUALITY_DIMENSIONS:
            issues.append(f"invalid_dimension:{q.get('quality_id')}")
        if q.get("dataset_id") not in ds_ids:
            issues.append(f"orphan_quality:{q.get('quality_id')}")
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
    dataset = dataset_lifecycle_integrity()
    duplicate = duplicate_integrity()
    version = version_lineage_integrity()
    quality = quality_integrity()
    lineage = lineage_integrity()
    ok = (ok and dataset["ok"] and duplicate["ok"] and version["ok"] and quality["ok"]
          and lineage["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "dataset_lifecycle": dataset,
            "duplicate": duplicate, "version_lineage": version, "quality": quality,
            "lineage": lineage}


def replay(engine, now="") -> dict:
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    p1 = engine.generate_report("SYSTEM", now, commit=False)
    p2 = engine.generate_report("SYSTEM", now, commit=False)
    return {"deterministic": r1.to_dict() == r2.to_dict() and p1.to_dict() == p2.to_dict(),
            "dataset_count": r1.dataset_count, "version_count": r1.version_count}
