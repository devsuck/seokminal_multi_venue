"""P11.11 Research Event Bus 테스트. **내부 연구 이벤트 통신 — 통신 인프라 전용.**

이벤트 유형 등록·인가 소스·스트림·이벤트 발행(CREATED→PUBLISHED→ROUTED→CONSUMED→ARCHIVED)·구독자·라우팅 규칙·
전달 추적·소비·이벤트 순서·계보(부모/순환)·스냅샷 결정성·리포트(is_binding=False)·verify(체인/변조/중복/생애주기/
부모누락/라우팅/소스권한/계보)·replay·CLI·보안(금지import·실행/배포/승인/수정 없음·삭제 API 없음·불변·
EVENT≠EXECUTION·PUBLISH≠DEPLOY·append-only·모델ID 미노출).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.research_event_bus import ledger
from jarvis.research_event_bus import models as M
from jarvis.research_event_bus.engine import ResearchEventBusEngine
from jarvis.research_event_bus.models import (
    ACT_CONSUMED,
    ACT_DELIVERED,
    E_ARCHIVED,
    E_CONSUMED,
    E_CREATED,
    E_PUBLISHED,
    E_ROUTED,
    EVENT_TYPES,
    CircularLineageError,
    IllegalEventTransition,
    ImmutableEventError,
    ImmutableStreamError,
    ImmutableSubscriberError,
    ImmutableTypeError,
    InvalidEventType,
    InvalidRoutingError,
    MissingParentError,
    UnauthorizedSourceError,
    UnknownEventError,
    UnknownStreamError,
    UnknownSubscriberError,
)
from jarvis.research_event_bus.verify import (
    duplicate_integrity,
    lifecycle_integrity,
    lineage_integrity,
    parent_integrity,
    replay,
    routing_integrity,
    source_integrity,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_event_bus.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchEventBusEngine()


def _type(e, et="RESEARCH_STARTED", now=T[0]):
    return e.register_event_type(et, "desc", "cat", now, commit=True).event_type


def _publish(e, et="RESEARCH_STARTED", layer="research_agents", sid="RPT1", payload=None,
             parent="", now=T[1]):
    if not ledger.type_exists(M.event_type_id(et)):
        e.register_event_type(et, "d", "c", T[0], commit=True)
    return e.publish_event(et, layer, sid, payload if payload is not None else {"k": sid},
                           parent, None, now, commit=True).event_id


def _subscriber(e, name="analyst", et="RESEARCH_STARTED", now=T[0]):
    if not ledger.type_exists(M.event_type_id(et)):
        e.register_event_type(et, "d", "c", T[0], commit=True)
    return e.register_subscriber(name, et, "", now, commit=True).subscriber_id


# ══════════════ Phase 0 / 접두사 / 소유 ══════════════
def test_prefix_all_ledgers_reb():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("reb_")


def test_eleven_owned_ledgers():
    assert len(ledger.ALL_LEDGERS) == 11


def test_source_ledgers_read_only_count():
    assert len(ledger.SOURCE_LEDGERS) == 17
    assert "research_improvement" in ledger.SOURCE_LEDGERS


def test_event_types_ten():
    assert len(EVENT_TYPES) == 10


def test_event_states_five():
    assert len(M.EVENT_STATES) == 5


# ══════════════ register_event_type ══════════════
def test_register_event_type_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.register_event_type("RESEARCH_STARTED", "d", "c", T[0], commit=True)
    b = e.register_event_type("RESEARCH_STARTED", "d", "c", T[1], commit=False)
    assert a.event_type_id == b.event_type_id
    assert a.event_type_id.startswith("RBT:")


def test_register_event_type_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_event_type("X", "d", "c", T[0], commit=True)
    e.register_event_type("X", "d", "c", T[1], commit=True)
    assert len(ledger.read_types()) == 1


def test_register_event_type_immutable_desc(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_event_type("X", "d1", "c", T[0], commit=True)
    with pytest.raises(ImmutableTypeError):
        e.register_event_type("X", "d2", "c", T[1], commit=True)


@pytest.mark.parametrize("et", list(EVENT_TYPES))
def test_register_all_standard_types(tmp_path, monkeypatch, et):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rec = e.register_event_type(et, "d", "c", T[0], commit=True)
    assert rec.event_type == et


# ══════════════ register_source ══════════════
def test_register_source_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    s = e.register_source("custom_layer", "SRC1", "note", T[0], commit=True)
    assert s.source_record_id.startswith("RBO:")
    assert ledger.source_registered("custom_layer", "SRC1")


def test_register_source_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_source("l", "s", "n", T[0], commit=True)
    e.register_source("l", "s", "n", T[1], commit=True)
    assert len(ledger.read_sources()) == 1


# ══════════════ build_event_stream ══════════════
def test_build_stream_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    s = e.build_event_stream("main", "RESEARCH_STARTED", "d", T[0], commit=True)
    assert s.stream_id.startswith("RBS:")


def test_build_stream_immutable_filter(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.build_event_stream("main", "A", "d", T[0], commit=True)
    with pytest.raises(ImmutableStreamError):
        e.build_event_stream("main", "B", "d", T[1], commit=True)


def test_stream_events_filter(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _type(e, "RESEARCH_STARTED")
    _type(e, "REVIEW_COMPLETED")
    e.build_event_stream("rs", "RESEARCH_STARTED", "d", T[0], commit=True)
    _publish(e, "RESEARCH_STARTED", sid="A")
    _publish(e, "REVIEW_COMPLETED", sid="B", now=T[2])
    evs = e.stream_events("rs")
    assert len(evs) == 1


def test_stream_events_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownStreamError):
        e.stream_events("nope")


# ══════════════ publish_event ══════════════
def test_publish_requires_registered_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(InvalidEventType):
        e.publish_event("UNREG", "research_agents", "S1", {}, now=T[1], commit=True)


def test_publish_reaches_published(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    eid = _publish(e)
    assert e.current_state(eid) == E_PUBLISHED
    assert eid.startswith("RBV:")


def test_publish_records_created_then_published(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    eid = _publish(e)
    states = [r["to_state"] for r in ledger.event_records(eid)]
    assert states == [E_CREATED, E_PUBLISHED]


def test_publish_stores_payload_hash_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    eid = _publish(e, payload={"secret": 123})
    meta = e.event_meta(eid)
    assert meta["payload_hash"].startswith("sha256:")
    # 원본 페이로드는 저장되지 않음
    for r in ledger.event_records(eid):
        assert "secret" not in json.dumps(r)


def test_publish_idempotent_same_payload(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_event_type("RESEARCH_STARTED", "d", "c", T[0], commit=True)
    a = e.publish_event("RESEARCH_STARTED", "research_agents", "S1", {"x": 1}, now=T[1], commit=True)
    b = e.publish_event("RESEARCH_STARTED", "research_agents", "S1", {"x": 1}, now=T[2], commit=True)
    assert a.event_id == b.event_id
    assert len(ledger.event_records(a.event_id)) == 2  # CREATED+PUBLISHED only once


def test_publish_metadata_required_fields(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_event_type("RESEARCH_STARTED", "d", "c", T[0], commit=True)
    ev = e.publish_event("RESEARCH_STARTED", "research_agents", "S1", {"x": 1},
                         metadata={"run": "r1"}, now=T[1], commit=True)
    # 필수 필드 존재
    d = ev.to_dict()
    for f in ("event_id", "event_type", "source_layer", "source_id", "payload_hash",
              "parent_event", "metadata", "occurred_at"):
        assert f in d
    assert ev.metadata == {"run": "r1"}


def test_publish_unauthorized_source_flagged(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_event_type("RESEARCH_STARTED", "d", "c", T[0], commit=True)
    ev = e.publish_event("RESEARCH_STARTED", "rogue_layer", "S1", {"x": 1}, now=T[1], commit=True)
    assert ev.authorized is False


def test_publish_require_source_raises(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_event_type("RESEARCH_STARTED", "d", "c", T[0], commit=True)
    with pytest.raises(UnauthorizedSourceError):
        e.publish_event("RESEARCH_STARTED", "rogue", "S1", {}, now=T[1], commit=True,
                        require_source=True)


def test_publish_authorized_known_upstream(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    eid = _publish(e, layer="research_agents")
    assert e.event_meta(eid)["authorized"] is True


def test_publish_authorized_registered_source(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_source("custom", "S1", "n", T[0], commit=True)
    e.register_event_type("RESEARCH_STARTED", "d", "c", T[0], commit=True)
    ev = e.publish_event("RESEARCH_STARTED", "custom", "S1", {}, now=T[1], commit=True)
    assert ev.authorized is True


# ══════════════ 부모/계보 ══════════════
def test_publish_missing_parent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_event_type("RESEARCH_STARTED", "d", "c", T[0], commit=True)
    with pytest.raises(MissingParentError):
        e.publish_event("RESEARCH_STARTED", "research_agents", "S1", {}, parent_event="RBV:ghost",
                        now=T[1], commit=True)


def test_publish_with_valid_parent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _publish(e, sid="P")
    c = _publish(e, sid="C", parent=p, now=T[3])
    assert p in e.trace_event_lineage(c)


def test_lineage_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _publish(e, sid="P")
    c = _publish(e, sid="C", parent=p, now=T[3])
    lin = [r for r in ledger.read_lineage() if r["event_id"] == c]
    assert lin and lin[0]["parent_event"] == p


def test_lineage_chain_three(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _publish(e, sid="A")
    b = _publish(e, sid="B", parent=a, now=T[3])
    c = _publish(e, sid="C", parent=b, now=T[4])
    anc = e.trace_event_lineage(c)
    assert a in anc and b in anc


def test_detect_cycle_pure():
    assert M.detect_cycle([("a", "b"), ("b", "a")]) != []
    assert M.detect_cycle([("a", "b")]) == []


# ══════════════ subscriber ══════════════
def test_register_subscriber_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _subscriber(e)
    assert sid.startswith("RBU:")


def test_register_subscriber_requires_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(InvalidEventType):
        e.register_subscriber("a", "UNREG", "", T[0], commit=True)


def test_register_subscriber_immutable_filter(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _type(e, "RESEARCH_STARTED")
    e.register_subscriber("a", "RESEARCH_STARTED", "f1", T[0], commit=True)
    with pytest.raises(ImmutableSubscriberError):
        e.register_subscriber("a", "RESEARCH_STARTED", "f2", T[1], commit=True)


def test_register_subscriber_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _type(e, "RESEARCH_STARTED")
    e.register_subscriber("a", "RESEARCH_STARTED", "", T[0], commit=True)
    e.register_subscriber("a", "RESEARCH_STARTED", "", T[1], commit=True)
    assert len(ledger.read_subscribers()) == 1


# ══════════════ routing ══════════════
def test_register_route_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _subscriber(e)
    r = e.register_route("RESEARCH_STARTED", sid, "", T[1], commit=True)
    assert r.route_id.startswith("RBR:")


def test_register_route_unknown_subscriber(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _type(e, "RESEARCH_STARTED")
    with pytest.raises(InvalidRoutingError):
        e.register_route("RESEARCH_STARTED", "RBU:ghost", "", T[1], commit=True)


def test_register_route_type_mismatch(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _type(e, "RESEARCH_STARTED")
    _type(e, "REVIEW_COMPLETED")
    sid = e.register_subscriber("a", "REVIEW_COMPLETED", "", T[0], commit=True).subscriber_id
    with pytest.raises(InvalidRoutingError):
        e.register_route("RESEARCH_STARTED", sid, "", T[1], commit=True)


def test_register_route_unregistered_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(InvalidEventType):
        e.register_route("UNREG", "RBU:x", "", T[1], commit=True)


# ══════════════ track_delivery ══════════════
def test_track_delivery_routes_event(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    eid = _publish(e)
    sid = _subscriber(e)
    e.track_delivery(eid, sid, "", T[3], commit=True)
    assert e.current_state(eid) == E_ROUTED


def test_track_delivery_records_consumer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    eid = _publish(e)
    sid = _subscriber(e)
    d = e.track_delivery(eid, sid, "", T[3], commit=True)
    assert d.activity == ACT_DELIVERED
    assert d.consumer_record_id.startswith("RBC:")


def test_track_delivery_unknown_event(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _subscriber(e)
    with pytest.raises(UnknownEventError):
        e.track_delivery("RBV:ghost", sid, "", T[3], commit=True)


def test_track_delivery_unknown_subscriber(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    eid = _publish(e)
    with pytest.raises(UnknownSubscriberError):
        e.track_delivery(eid, "RBU:ghost", "", T[3], commit=True)


def test_track_delivery_multiple_subscribers(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    eid = _publish(e)
    s1 = _subscriber(e, "a")
    s2 = _subscriber(e, "b")
    e.track_delivery(eid, s1, "", T[3], commit=True)
    e.track_delivery(eid, s2, "", T[4], commit=True)
    assert len(ledger.event_consumers(eid)) == 2


# ══════════════ consume_event ══════════════
def test_consume_event_reaches_consumed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    eid = _publish(e)
    sid = _subscriber(e)
    e.consume_event(eid, sid, "", T[3], commit=True)
    assert e.current_state(eid) == E_CONSUMED


def test_consume_from_published_directly(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    eid = _publish(e)
    sid = _subscriber(e)
    c = e.consume_event(eid, sid, "", T[3], commit=True)
    assert c.activity == ACT_CONSUMED


def test_consume_after_route(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    eid = _publish(e)
    sid = _subscriber(e)
    e.track_delivery(eid, sid, "", T[3], commit=True)
    e.consume_event(eid, sid, "", T[4], commit=True)
    assert e.current_state(eid) == E_CONSUMED


def test_consume_multiple_subscribers_reentry(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    eid = _publish(e)
    s1 = _subscriber(e, "a")
    s2 = _subscriber(e, "b")
    e.consume_event(eid, s1, "", T[3], commit=True)
    e.consume_event(eid, s2, "", T[4], commit=True)
    # CONSUMED 재진입 허용, 이벤트 id 유일
    ids = [r["event_lifecycle_id"] for r in ledger.event_records(eid)]
    assert len(ids) == len(set(ids))


def test_consume_after_archive_illegal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    eid = _publish(e)
    sid = _subscriber(e)
    e.consume_event(eid, sid, "", T[3], commit=True)
    e.archive_event(eid, T[4], commit=True)
    with pytest.raises(IllegalEventTransition):
        e.consume_event(eid, sid, "", T[5], commit=True)


# ══════════════ archive ══════════════
def test_archive_from_published(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    eid = _publish(e)
    e.archive_event(eid, T[3], commit=True)
    assert e.current_state(eid) == E_ARCHIVED


def test_archive_from_consumed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    eid = _publish(e)
    sid = _subscriber(e)
    e.consume_event(eid, sid, "", T[3], commit=True)
    e.archive_event(eid, T[4], commit=True)
    assert e.current_state(eid) == E_ARCHIVED


def test_archive_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    eid = _publish(e)
    e.archive_event(eid, T[3], commit=True)
    with pytest.raises(IllegalEventTransition):
        e.archive_event(eid, T[4], commit=True)


# ══════════════ event ordering ══════════════
def test_event_ordering_preserved(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _type(e, "RESEARCH_STARTED")
    ids = [_publish(e, sid=f"S{i}", now=T[i + 1]) for i in range(5)]
    genesis = [r["event_id"] for r in ledger.read_events() if r["from_state"] == M.GENESIS]
    assert genesis == ids


def test_list_events_by_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _type(e, "RESEARCH_STARTED")
    _type(e, "REVIEW_COMPLETED")
    _publish(e, "RESEARCH_STARTED", sid="A")
    _publish(e, "REVIEW_COMPLETED", sid="B", now=T[2])
    assert len(e.list_events("RESEARCH_STARTED")) == 1
    assert len(e.list_events()) == 2


def test_events_in_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    eid = _publish(e)
    assert eid in e.events_in_state(E_PUBLISHED)


# ══════════════ snapshot ══════════════
def test_snapshot_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _type(e, "RESEARCH_STARTED")
    e1 = _publish(e, sid="A")
    e2 = _publish(e, sid="B", now=T[2])
    sid = _subscriber(e)
    e.consume_event(e2, sid, "", T[3], commit=True)
    snap = e.snapshot_events("ALL", T[5], commit=True)
    assert snap.event_count == 2
    assert snap.state_distribution.get(E_PUBLISHED) == 1
    assert snap.state_distribution.get(E_CONSUMED) == 1


def test_snapshot_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _publish(e)
    a = e.snapshot_events("ALL", T[5], commit=False)
    b = e.snapshot_events("ALL", T[5], commit=False)
    assert a.snapshot_id == b.snapshot_id
    assert a.state_distribution == b.state_distribution


def test_snapshot_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _publish(e)
    snap = e.snapshot_events("ALL", T[5], commit=True)
    arts = [a for a in ledger.read_artifacts() if a["artifact_type"] == M.ART_SNAPSHOT]
    assert any(a["ref_id"] == snap.snapshot_id for a in arts)


# ══════════════ report ══════════════
def test_report_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _type(e, "RESEARCH_STARTED")
    e1 = _publish(e, sid="A")
    e2 = _publish(e, sid="B", now=T[2])
    sid = _subscriber(e)
    e.consume_event(e2, sid, "", T[3], commit=True)
    e.archive_event(e2, T[4], commit=True)
    rep = e.generate_report("ALL", T[6], commit=True)
    assert rep.event_count == 2
    assert rep.published_count == 2
    assert rep.consumed_count == 1
    assert rep.archived_count == 1


def test_report_not_binding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rep = e.generate_report("ALL", T[1], commit=True)
    assert rep.is_binding is False


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rep = e.generate_report("ALL", T[1], commit=True)
    assert "EVENT ≠ EXECUTION" in rep.disclaimer


def test_report_type_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _type(e, "RESEARCH_STARTED")
    _type(e, "REVIEW_COMPLETED")
    _publish(e, "RESEARCH_STARTED", sid="A")
    _publish(e, "REVIEW_COMPLETED", sid="B", now=T[2])
    rep = e.generate_report("ALL", T[3], commit=True)
    assert rep.type_distribution.get("RESEARCH_STARTED") == 1
    assert rep.type_distribution.get("REVIEW_COMPLETED") == 1


# ══════════════ hash chain & tamper ══════════════
def test_chain_intact_full_flow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    eid = _publish(e)
    sid = _subscriber(e)
    e.track_delivery(eid, sid, "", T[3], commit=True)
    e.consume_event(eid, sid, "", T[4], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tampered_payload(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    eid = _publish(e)
    p = ledger.state_path(ledger.EVENTS[0])
    recs = ledger.read_events()
    recs[0]["payload_hash"] = "sha256:tampered0000000"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _type(e, "RESEARCH_STARTED")
    _publish(e, sid="A")
    _publish(e, sid="B", now=T[2])
    p = ledger.state_path(ledger.EVENTS[0])
    recs = ledger.read_events()
    recs[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ledgers"][ledger.EVENTS[0]]["ok"] is False


def test_verify_detects_duplicate_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _publish(e)
    p = ledger.state_path(ledger.EVENTS[0])
    recs = ledger.read_events()
    with open(p, "a") as f:
        f.write(json.dumps(recs[0], ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ledgers"][ledger.EVENTS[0]]["ok"] is False


# ══════════════ verify sub-integrities ══════════════
def test_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    eid = _publish(e)
    sid = _subscriber(e)
    e.consume_event(eid, sid, "", T[3], commit=True)
    assert lifecycle_integrity()["ok"] is True


def test_lifecycle_integrity_bad_initial(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng()
    p = ledger.state_path(ledger.EVENTS[0])
    bad = {"event_lifecycle_id": "RBE:bad", "event_id": "RBV:bad", "event_type": "X",
           "from_state": M.GENESIS, "to_state": E_PUBLISHED, "previous_hash": M.GENESIS}
    bad["record_hash"] = M.content_hash(bad)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(json.dumps(bad, ensure_ascii=False) + "\n")
    assert lifecycle_integrity()["ok"] is False


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _publish(e)
    assert duplicate_integrity()["ok"] is True


def test_duplicate_integrity_detects(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    eid = _publish(e)
    p = ledger.state_path(ledger.EVENTS[0])
    g = [r for r in ledger.event_records(eid) if r["from_state"] == M.GENESIS][0]
    with open(p, "a") as f:
        f.write(json.dumps(g, ensure_ascii=False) + "\n")
    assert duplicate_integrity()["ok"] is False


def test_parent_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _publish(e, sid="P")
    _publish(e, sid="C", parent=p, now=T[3])
    assert parent_integrity()["ok"] is True


def test_parent_integrity_detects_dangling(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _publish(e, sid="P")
    c = _publish(e, sid="C", parent=p, now=T[3])
    # 계보의 부모를 유령으로 위조
    lp = ledger.state_path(ledger.LINEAGE[0])
    recs = ledger.read_lineage()
    for r in recs:
        if r["event_id"] == c:
            r["parent_event"] = "RBV:ghost"
    with open(lp, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert parent_integrity()["ok"] is False


def test_routing_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sid = _subscriber(e)
    e.register_route("RESEARCH_STARTED", sid, "", T[1], commit=True)
    assert routing_integrity()["ok"] is True


def test_routing_integrity_detects_dangling_consumer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    eid = _publish(e)
    sid = _subscriber(e)
    e.consume_event(eid, sid, "", T[3], commit=True)
    # 소비 레코드의 구독자를 유령으로 위조
    p = ledger.state_path(ledger.CONSUMERS[0])
    recs = ledger.read_consumers()
    recs[0]["subscriber"] = "RBU:ghost"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert routing_integrity()["ok"] is False


def test_source_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _publish(e, layer="research_agents")
    assert source_integrity()["ok"] is True


def test_source_integrity_detects_unauthorized(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_event_type("RESEARCH_STARTED", "d", "c", T[0], commit=True)
    e.publish_event("RESEARCH_STARTED", "rogue", "S1", {}, now=T[1], commit=True)
    assert source_integrity()["ok"] is False
    # 기본 verify_chain 은 소스 권한 포함
    assert verify_chain()["ok"] is False
    # check_source=False 시 통과
    assert verify_chain(check_source=False)["ok"] is True


def test_lineage_integrity_cycle_detect(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _publish(e, sid="A")
    b = _publish(e, sid="B", parent=a, now=T[3])
    # a 의 계보 부모를 b 로 위조 → 순환
    lp = ledger.state_path(ledger.LINEAGE[0])
    recs = ledger.read_lineage()
    for r in recs:
        if r["event_id"] == a:
            r["parent_event"] = b
    with open(lp, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert lineage_integrity()["ok"] is False


# ══════════════ replay / determinism ══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _publish(e)
    assert replay(e, T[9])["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _type(e, "RESEARCH_STARTED")
    _publish(e, sid="A")
    _subscriber(e)
    s = e.summary(T[9])
    assert s.type_count == 1
    assert s.subscriber_count == 1
    assert s.event_lifecycle_count == 2


def test_replay_reengine_equal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _publish(e)
    s1 = e.summary(T[9]).to_dict()
    s2 = _eng().summary(T[9]).to_dict()
    assert s1 == s2


def test_verify_integrity_wrapper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _publish(e)
    assert e.verify_integrity()["ok"] is True


def test_verify_chain_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = verify_chain()
    assert res["ok"] is True and res["n"] == 0


# ══════════════ can_transition matrix ══════════════
@pytest.mark.parametrize("frm,to,ok", [
    (E_CREATED, E_PUBLISHED, True),
    (E_PUBLISHED, E_ROUTED, True),
    (E_PUBLISHED, E_CONSUMED, True),
    (E_PUBLISHED, E_ARCHIVED, True),
    (E_ROUTED, E_CONSUMED, True),
    (E_ROUTED, E_ROUTED, True),
    (E_CONSUMED, E_CONSUMED, True),
    (E_CONSUMED, E_ARCHIVED, True),
    (E_CREATED, E_CONSUMED, False),
    (E_CREATED, E_ARCHIVED, False),
    (E_ARCHIVED, E_PUBLISHED, False),
    (E_CONSUMED, E_PUBLISHED, False),
    (E_ARCHIVED, E_CONSUMED, False),
])
def test_can_transition_matrix(frm, to, ok):
    assert M.can_transition(frm, to) is ok


# ══════════════ is_forbidden_verb ══════════════
@pytest.mark.parametrize("word", ["EXECUTE", "TRADE", "DEPLOY", "ALLOCATE", "PROMOTE_LIVE",
                                  "MODIFY_STRATEGY", "MODIFY_MODEL", "CHANGE_PERMISSION",
                                  "CHANGE_CONFIG", "approve", " deploy "])
def test_is_forbidden_verb_true(word):
    assert M.is_forbidden_verb(word) is True


@pytest.mark.parametrize("word", ["PUBLISH", "CONSUME", "ROUTE", "SUBSCRIBE", "OBSERVE", ""])
def test_is_forbidden_verb_false(word):
    assert M.is_forbidden_verb(word) is False


# ══════════════ ID 결정성 / prefixes ══════════════
def test_ids_deterministic():
    assert M.event_type_id("x") == M.event_type_id("x")
    assert M.event_id("l", "s", "t", "h") == M.event_id("l", "s", "t", "h")
    assert M.subscriber_id("a", "t") == M.subscriber_id("a", "t")


def test_ids_prefixes():
    assert M.event_type_id("x").startswith("RBT:")
    assert M.source_record_id("l", "s").startswith("RBO:")
    assert M.stream_id("n").startswith("RBS:")
    assert M.event_id("l", "s", "t", "h").startswith("RBV:")
    assert M.event_lifecycle_id("e", "s", 0).startswith("RBE:")
    assert M.subscriber_id("a", "t").startswith("RBU:")
    assert M.consumer_record_id("e", "s", "a", 0).startswith("RBC:")
    assert M.route_id("t", "s").startswith("RBR:")
    assert M.snapshot_id("s", "t").startswith("RBN:")
    assert M.report_id("s", "t").startswith("RBP:")
    assert M.artifact_id("t", "r").startswith("RBA:")
    assert M.lineage_id("e").startswith("RBL:")


def test_lifecycle_id_varies_with_seq():
    assert M.event_lifecycle_id("e", "ROUTED", 0) != M.event_lifecycle_id("e", "ROUTED", 1)


def test_payload_digest_deterministic():
    assert M.payload_digest({"a": 1}) == M.payload_digest({"a": 1})
    assert M.payload_digest({"a": 1}) != M.payload_digest({"a": 2})


def test_content_hash_excludes_hash_fields():
    a = {"x": 1, "previous_hash": "p", "record_hash": "r"}
    b = {"x": 1, "previous_hash": "q", "record_hash": "s"}
    assert M.content_hash(a) == M.content_hash(b)


# ══════════════ 보안: 금지 import AST 스캔 ══════════════
_PKG_DIR = os.path.dirname(os.path.dirname(__file__))
_FORBIDDEN_PREFIXES = (
    "jarvis.execution", "jarvis.broker", "jarvis.portfolio", "jarvis.risk",
    "jarvis.permission", "jarvis.deployment", "jarvis.live", "jarvis.order",
    "jarvis.capital_allocation", "jarvis.live_trading", "jarvis.risk_controller",
    "jarvis.portfolio_execution",
)


def _module_files():
    for fn in os.listdir(_PKG_DIR):
        if fn.endswith(".py"):
            yield os.path.join(_PKG_DIR, fn)


def test_no_forbidden_imports():
    for path in _module_files():
        with open(path) as f:
            tree = ast.parse(f.read(), filename=path)
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                for bad in _FORBIDDEN_PREFIXES:
                    assert not name.startswith(bad), f"{path}: {name}"


def test_no_forbidden_method_defs():
    forbidden = ("def execute", "def trade", "def deploy", "def allocate", "def promote_live",
                 "def modify_strategy", "def modify_model", "def change_permission",
                 "def change_config", "def place_order")
    for path in _module_files():
        with open(path) as f:
            src = f.read().lower()
        for bad in forbidden:
            assert bad not in src, f"{path}: {bad}"


def test_no_model_id_leak():
    for path in _module_files():
        with open(path) as f:
            assert "claude-opus" not in f.read().lower()


def test_ledger_no_delete_update_api():
    import jarvis.research_event_bus.ledger as L
    for name in dir(L):
        assert not name.startswith("delete_")
        assert not name.startswith("update_")
        assert not name.startswith("remove_")


def test_ledger_only_append_mode():
    with open(os.path.join(_PKG_DIR, "ledger.py")) as f:
        src = f.read()
    assert 'open(p, "a")' in src
    assert 'open(p, "w")' not in src


def test_all_written_files_have_reb_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    eid = _publish(e)
    sid = _subscriber(e)
    e.consume_event(eid, sid, "", T[3], commit=True)
    e.snapshot_events("ALL", T[4], commit=True)
    for fn in os.listdir(tmp_path):
        if fn.endswith(".jsonl"):
            assert fn.startswith("reb_"), fn


# ══════════════ 소스 참조 READ ONLY ══════════════
def test_source_ref_exists_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert ledger.source_ref_exists("research_agents", "x") is False


def test_source_ref_read_only_no_write(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = ledger.state_path("ragt_reports.jsonl")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(json.dumps({"report_id": "R1"}) + "\n")
    before = os.path.getmtime(p)
    assert ledger.source_ref_exists("research_agents", "R1") is True
    assert os.path.getmtime(p) == before


# ══════════════ CLI ══════════════
def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_event_bus.__main__ import main
    assert main(["summary"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "event_lifecycle_count" in out


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_event_bus.__main__ import main
    assert main(["verify"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_full_flow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_event_bus.__main__ import main
    main(["type", "--name", "RESEARCH_STARTED", "--commit"])
    capsys.readouterr()
    main(["publish", "--type", "RESEARCH_STARTED", "--layer", "research_agents",
          "--source-id", "S1", "--payload", '{"k":1}', "--commit"])
    eid = json.loads(capsys.readouterr().out)["event"]["event_id"]
    main(["subscriber", "--name", "a", "--type", "RESEARCH_STARTED", "--commit"])
    sid = json.loads(capsys.readouterr().out)["subscriber"]["subscriber_id"]
    assert main(["deliver", "--event", eid, "--subscriber", sid, "--commit"]) == 0
    capsys.readouterr()
    assert main(["consume", "--event", eid, "--subscriber", sid, "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["consumption"]["activity"] == ACT_CONSUMED


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_event_bus.__main__ import main
    assert main(["replay"]) == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_snapshot_and_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_event_bus.__main__ import main
    main(["type", "--name", "RESEARCH_STARTED", "--commit"])
    capsys.readouterr()
    main(["publish", "--type", "RESEARCH_STARTED", "--layer", "research_agents",
          "--source-id", "S1", "--commit"])
    capsys.readouterr()
    assert main(["snapshot", "--commit"]) == 0
    capsys.readouterr()
    assert main(["report", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["report"]["is_binding"] is False


def test_cli_events(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_event_bus.__main__ import main
    main(["type", "--name", "RESEARCH_STARTED", "--commit"])
    capsys.readouterr()
    main(["publish", "--type", "RESEARCH_STARTED", "--layer", "research_agents",
          "--source-id", "S1", "--commit"])
    capsys.readouterr()
    assert main(["events"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["events"]) == 1


def test_cli_stream(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_event_bus.__main__ import main
    assert main(["stream", "--name", "main", "--type-filter", "RESEARCH_STARTED", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["stream"]["stream_id"].startswith("RBS:")


def test_cli_source(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_event_bus.__main__ import main
    assert main(["source", "--layer", "custom", "--source-id", "S1", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["source"]["source_record_id"].startswith("RBO:")


def test_cli_route(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_event_bus.__main__ import main
    main(["type", "--name", "RESEARCH_STARTED", "--commit"])
    capsys.readouterr()
    main(["subscriber", "--name", "a", "--type", "RESEARCH_STARTED", "--commit"])
    sid = json.loads(capsys.readouterr().out)["subscriber"]["subscriber_id"]
    assert main(["route", "--type", "RESEARCH_STARTED", "--subscriber", sid, "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["route"]["route_id"].startswith("RBR:")


# ══════════════ 불변: 상이 페이로드 재발행 거부 ══════════════
def test_republish_diff_payload_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_event_type("RESEARCH_STARTED", "d", "c", T[0], commit=True)
    e.publish_event("RESEARCH_STARTED", "research_agents", "S1", {"x": 1}, now=T[1], commit=True)
    # 동일 (layer, source, type) 이지만 다른 payload → 다른 event_id (충돌 아님)
    ev2 = e.publish_event("RESEARCH_STARTED", "research_agents", "S1", {"x": 2}, now=T[2],
                          commit=True)
    assert ev2.event_id != M.event_id("research_agents", "S1", "RESEARCH_STARTED",
                                       M.payload_digest({"x": 1}))


def test_no_stray_writes_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_event_type("RESEARCH_STARTED", "d", "c", T[0], commit=False)
    assert ledger.read_types() == []


def test_full_lifecycle_states_sequence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    eid = _publish(e)
    sid = _subscriber(e)
    e.track_delivery(eid, sid, "", T[3], commit=True)
    e.consume_event(eid, sid, "", T[4], commit=True)
    e.archive_event(eid, T[5], commit=True)
    states = [r["to_state"] for r in ledger.event_records(eid)]
    assert states == [E_CREATED, E_PUBLISHED, E_ROUTED, E_CONSUMED, E_ARCHIVED]
