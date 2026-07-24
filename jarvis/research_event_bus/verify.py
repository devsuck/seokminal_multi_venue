"""Research Event Bus 검증 (P11.11) — 체인·변조·중복·생애주기·부모·라우팅·소스 권한·계보·재현. 읽기전용.

각 원장: previous_hash 링크 + record_hash 재계산(변조·페이로드 변조) + id 중복. 이벤트 생애주기 전이 합법성
(CREATED 시작). 중복 이벤트 탐지(같은 event_id 의 CREATED 이벤트는 유일). 부모 이벤트 무결성(dangling). 라우팅
무결성(라우팅 규칙의 유형·구독자 등록 여부). 소스 권한(미인가 소스 발행 탐지). 계보(dangling·순환). **변경/실행/
승인/수정 없음.**
"""
from __future__ import annotations

from jarvis.research_event_bus import ledger
from jarvis.research_event_bus.models import (
    E_CREATED,
    GENESIS,
    can_transition,
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


def lifecycle_integrity() -> dict:
    """이벤트별 생애주기 전이 합법성(순차, CREATED 시작)."""
    issues: list = []
    by_event: dict = {}
    for ev in ledger.read_events():
        by_event.setdefault(ev.get("event_id"), []).append(ev)
    for eid, evs in sorted(by_event.items()):
        prev = None
        for ev in evs:
            to = ev.get("to_state")
            if prev is None:
                if to != E_CREATED:
                    issues.append(f"bad_initial:{eid}:{to}")
            elif not can_transition(prev, to):
                issues.append(f"illegal:{eid}:{prev}->{to}")
            prev = to
    return {"ok": not issues, "issues": sorted(set(issues))}


def duplicate_integrity() -> dict:
    """중복 이벤트 탐지: 같은 event_id 의 CREATED(genesis) 생애주기 레코드는 유일해야 한다."""
    issues: list = []
    genesis_seen: set = set()
    for ev in ledger.read_events():
        if ev.get("from_state") == GENESIS:
            eid = ev.get("event_id")
            if eid in genesis_seen:
                issues.append(f"duplicate_event:{eid}")
            genesis_seen.add(eid)
    return {"ok": not issues, "issues": sorted(set(issues))}


def parent_integrity() -> dict:
    """부모 이벤트 무결성: 계보/이벤트의 parent_event 가 알려진 event_id 인지(dangling 탐지)."""
    issues: list = []
    ids = set(ledger.event_ids())
    for lr in ledger.read_lineage():
        parent = lr.get("parent_event")
        if parent and parent not in ids:
            issues.append(f"missing_parent:{lr.get('event_id')}->{parent}")
    for ev in ledger.read_events():
        if ev.get("from_state") == GENESIS:
            parent = ev.get("parent_event")
            if parent and parent not in ids:
                issues.append(f"missing_parent_event:{ev.get('event_id')}->{parent}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def routing_integrity() -> dict:
    """라우팅 무결성: 규칙의 이벤트 유형·대상 구독자가 등록되어 있고 유형이 일치하는지."""
    issues: list = []
    known_types = {t.get("event_type") for t in ledger.read_types()}
    subs = {s.get("subscriber_id"): s for s in ledger.read_subscribers()}
    for r in ledger.read_routes():
        et = r.get("event_type")
        tgt = r.get("target_subscriber")
        if et not in known_types:
            issues.append(f"unknown_type_route:{r.get('route_id')}")
        if tgt not in subs:
            issues.append(f"unknown_subscriber_route:{r.get('route_id')}")
        elif subs[tgt].get("event_type") != et:
            issues.append(f"type_mismatch_route:{r.get('route_id')}")
    # 소비/전달 레코드의 이벤트·구독자 참조 무결성
    ids = set(ledger.event_ids())
    for c in ledger.read_consumers():
        if c.get("event_id") not in ids:
            issues.append(f"dangling_consumer_event:{c.get('consumer_record_id')}")
        if c.get("subscriber") not in subs:
            issues.append(f"dangling_consumer_subscriber:{c.get('consumer_record_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def source_integrity() -> dict:
    """소스 권한: 발행된 이벤트 소스가 인가(상위 계층 또는 등록 소스)되었는지."""
    issues: list = []
    for ev in ledger.read_events():
        if ev.get("from_state") == GENESIS and not ev.get("authorized"):
            issues.append(f"unauthorized_source:{ev.get('event_id')}")
    return {"ok": not issues, "issues": sorted(set(issues))}


def lineage_integrity() -> dict:
    """이벤트 계보(parent) 순환 + 아티팩트 계보 dangling·순환."""
    issues: list = []
    edges = [(r.get("event_id"), r.get("parent_event")) for r in ledger.read_lineage()
             if r.get("parent_event")]
    cyc = detect_cycle(edges)
    if cyc:
        issues.append("cycle_event:" + "->".join(cyc))
    arts = ledger.read_artifacts()
    aids = {a.get("artifact_id") for a in arts}
    aedges: list = []
    for a in arts:
        parent = a.get("parent_artifact")
        if parent:
            if parent not in aids:
                issues.append(f"dangling_artifact:{a.get('artifact_id')}")
            aedges.append((a.get("artifact_id"), parent))
    acyc = detect_cycle(aedges)
    if acyc:
        issues.append("cycle_artifact:" + "->".join(acyc))
    return {"ok": not issues, "issues": sorted(set(issues))}


def verify_chain(check_source: bool = True) -> dict:
    results = {}
    ok = True
    for which in ledger.ALL_LEDGERS:
        res = verify_ledger(which)
        results[which[0]] = res
        ok = ok and res["ok"]
    lifecycle = lifecycle_integrity()
    duplicate = duplicate_integrity()
    parent = parent_integrity()
    routing = routing_integrity()
    source = source_integrity()
    lineage = lineage_integrity()
    ok = (ok and lifecycle["ok"] and duplicate["ok"] and parent["ok"] and routing["ok"]
          and lineage["ok"])
    if check_source:
        ok = ok and source["ok"]
    total = sum(r.get("n", 0) for r in results.values())
    return {"ok": ok, "n": total, "ledgers": results, "lifecycle": lifecycle,
            "duplicate": duplicate, "parent": parent, "routing": routing, "source": source,
            "lineage": lineage}


def replay(engine, now: str = "") -> dict:
    """동일 상태 요약 두 번 → 동일 산출(결정성). commit 없음."""
    r1 = engine.summary(now)
    r2 = engine.summary(now)
    return {"deterministic": r1.to_dict() == r2.to_dict(),
            "event_lifecycle_count": r1.event_lifecycle_count,
            "subscriber_count": r1.subscriber_count,
            "route_count": r1.route_count}
