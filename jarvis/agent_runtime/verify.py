"""Agent Runtime 검증 (P45) — 체인·중복·에이전트 생애주기·배정·산출물 안전·능력·메모리 참조·계보·재현. 읽기전용."""
from __future__ import annotations

from jarvis.agent_runtime import ledger
from jarvis.agent_runtime import models as M
from jarvis.agent_runtime.models import GENESIS, content_hash, detect_cycle_check


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


def agent_lifecycle_integrity() -> dict:
    issues: list = []
    for aid, evs in sorted(_group(ledger.read_agent_events(), "agent_id").items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != M.A_CREATED:
                    issues.append(f"bad_initial:{aid}:{to}")
            elif not M.can_agent_transition(prev, to):
                issues.append(f"invalid_transition:{aid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def capability_integrity() -> dict:
    """모든 에이전트 능력은 허용목록 안이어야 하고 금지 능력이 없어야 한다(무제한 접근 금지)."""
    issues: list = []
    for ev in ledger.read_agent_events():
        if ev.get("from_state") != GENESIS:
            continue
        for cap in ev.get("capabilities", []) or []:
            c = (cap or "").strip().upper()
            if M.is_forbidden_capability(c):
                issues.append(f"forbidden_capability:{ev.get('agent_id')}:{c}")
            elif c not in M.ALLOWED_CAPABILITIES:
                issues.append(f"unlisted_capability:{ev.get('agent_id')}:{c}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def output_safety_integrity() -> dict:
    """산출물은 항상 is_binding=False·is_executed=False 이어야 한다(자동 실행 없음)."""
    issues: list = []
    agent_ids = set(ledger.agent_ids())
    for o in ledger.read_outputs():
        if o.get("is_binding") is not False:
            issues.append(f"binding_output:{o.get('output_id')}")
        if o.get("is_executed") is not False:
            issues.append(f"executed_output:{o.get('output_id')}")
        if o.get("agent_id") not in agent_ids:
            issues.append(f"orphan_output:{o.get('output_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def assignment_integrity() -> dict:
    issues: list = []
    agent_ids = set(ledger.agent_ids())
    seen: set = set()
    for a in ledger.read_assignments():
        tid = a.get("task_id")
        if tid in seen:
            issues.append(f"duplicate_assignment:{tid}")
        seen.add(tid)
        if a.get("agent_id") not in agent_ids:
            issues.append(f"orphan_assignment:{tid}")
        if a.get("is_binding") is not False:
            issues.append(f"binding_assignment:{tid}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def memory_reference_integrity() -> dict:
    """메모리 참조는 항상 READ ONLY 이어야 한다."""
    issues: list = []
    agent_ids = set(ledger.agent_ids())
    for r in ledger.read_memory_refs():
        if r.get("is_read_only") is not True:
            issues.append(f"mutable_memref:{r.get('memref_id')}")
        if r.get("agent_id") not in agent_ids:
            issues.append(f"orphan_memref:{r.get('memref_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    issues: list = []
    seen: set = set()
    for ev in ledger.read_agent_events():
        if ev.get("from_state") == GENESIS:
            aid = ev.get("agent_id")
            if aid in seen:
                issues.append(f"duplicate_agent:{aid}")
            seen.add(aid)
    for records, idf, label in ((ledger.read_outputs(), "output_id", "output"),
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
    agent = agent_lifecycle_integrity()
    capability = capability_integrity()
    output = output_safety_integrity()
    assignment = assignment_integrity()
    memory = memory_reference_integrity()
    duplicate = duplicate_integrity()
    lineage = lineage_integrity()
    ok = (ok and agent["ok"] and capability["ok"] and output["ok"] and assignment["ok"]
          and memory["ok"] and duplicate["ok"] and lineage["ok"])
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "agent_lifecycle": agent,
            "capability": capability, "output_safety": output, "assignment": assignment,
            "memory_reference": memory, "duplicate": duplicate, "lineage": lineage}


def replay(engine, now="") -> dict:
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    p1 = engine.generate_agent_report("SYSTEM", now, commit=False)
    p2 = engine.generate_agent_report("SYSTEM", now, commit=False)
    return {"deterministic": r1.to_dict() == r2.to_dict() and p1.to_dict() == p2.to_dict(),
            "agent_count": r1.agent_count, "output_count": r1.output_count}
