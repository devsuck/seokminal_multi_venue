"""P13 Autonomous Research OS 통합 테스트. **관찰·분석·기록 전용.**

OS 생애주기(INITIALIZED→CONNECTED→OBSERVING→ANALYZING→REPORTING→ARCHIVED)·모든 하위 계층 연결(READ ONLY)·에피소드·
지식 뷰·시스템 스냅샷(결정적)·운영 리포트(is_binding=False)·verify(체인/변조/중복/생애주기/참조/binding/계보)·replay·
하위 원장 쓰기 없음·모든 계층 연결·계보·READ ONLY 강제·금지 능력 스캔·CLI·보안(금지import·금지동사·삭제 API 없음·불변·
OS≠EXECUTION·aros_ 격리·모델ID 미노출).

패키지 내부 tests/ — 상위 conftest 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.autonomous_research_os import ledger
from jarvis.autonomous_research_os import models as M
from jarvis.autonomous_research_os.engine import AutonomousResearchOSEngine
from jarvis.autonomous_research_os.models import (
    ALLOWED_TRANSITIONS,
    FORBIDDEN_VERBS,
    GENESIS,
    OS_ANALYZING,
    OS_ARCHIVED,
    OS_CONNECTED,
    OS_INITIALIZED,
    OS_OBSERVING,
    OS_REPORTING,
    OS_STATES,
    IllegalOSTransition,
    UnknownOSError,
    can_transition,
    content_hash,
    detect_cycle_check,
    is_forbidden_verb,
)
from jarvis.autonomous_research_os.verify import (
    binding_integrity,
    duplicate_integrity,
    lifecycle_integrity,
    lineage_integrity,
    reference_integrity,
    replay,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]

ALL_LAYERS = sorted(ledger.SOURCE_LAYERS)


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.autonomous_research_os.ledger.state_path", sp)
    return sp


def _eng():
    return AutonomousResearchOSEngine()


def _os(e, name="research-os", now=T[0]):
    return e.initialize_os(name, now, commit=True).os_id


def _observing(e, name="research-os"):
    oid = _os(e, name)
    e.connect(oid, T[1], commit=True)
    e.collect_research_state(oid, "research_manager", "n", T[2], commit=True)
    return oid


def _seed_source(sp, layer, n=3):
    """하위 소스 원장에 더미 레코드 기록(READ ONLY 대상 시뮬레이션)."""
    fname = ledger.SOURCE_LAYERS[layer][0]
    idf = ledger.SOURCE_LAYERS[layer][1]
    p = sp(fname)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        for i in range(n):
            f.write(json.dumps({idf: f"{layer}:{i}"}) + "\n")


# ═══════════════ initialize_os ═══════════════
def test_init_returns_initialized(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().initialize_os("os", T[0], commit=True)
    assert ev.to_state == OS_INITIALIZED
    assert ev.from_state == GENESIS


def test_init_id_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().initialize_os("os", T[0], commit=True).os_id.startswith("AOG:")


def test_os_event_id_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().initialize_os("os", T[0], commit=True).os_event_id.startswith("AOR:")


def test_init_persists(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _os(e)
    assert len(ledger.read_os_events()) == 1


def test_init_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().initialize_os("os", T[0], commit=False)
    assert ledger.read_os_events() == []


def test_init_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _eng().initialize_os("os", T[0], commit=False).os_id
    b = _eng().initialize_os("os", T[5], commit=False).os_id
    assert a == b


def test_init_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.initialize_os("os", T[0], commit=True).os_id
    b = e.initialize_os("os", T[1], commit=True).os_id
    assert a == b
    assert len(ledger.os_events(a)) == 1


def test_init_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _os(e)
    assert len(ledger.read_artifacts()) == 1


def test_init_default_name(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().initialize_os(now=T[0], commit=True)
    assert ev.name == "research-os"


# ═══════════════ connect ═══════════════
def test_connect_transitions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _os(e)
    ev = e.connect(oid, T[1], commit=True)
    assert ev.to_state == OS_CONNECTED


def test_connect_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownOSError):
        _eng().connect("AOG:nope", T[1], commit=True)


def test_connect_before_init_via_wrong_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    # OBSERVING → CONNECTED illegal
    with pytest.raises(IllegalOSTransition):
        e.connect(oid, T[5], commit=True)


# ═══════════════ collect_research_state ═══════════════
def test_collect_transitions_observing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _os(e)
    e.connect(oid, T[1], commit=True)
    e.collect_research_state(oid, "research_manager", "n", T[2], commit=True)
    assert e.current_state(oid) == OS_OBSERVING


def test_collect_episode_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _os(e)
    e.connect(oid, T[1], commit=True)
    ep = e.collect_research_state(oid, "research_manager", "n", T[2], commit=True)
    assert ep.episode_id.startswith("AOE:")


def test_collect_records_source_file(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _os(e)
    e.connect(oid, T[1], commit=True)
    ep = e.collect_research_state(oid, "research_control", "n", T[2], commit=True)
    assert ep.source_file == "rctl_states.jsonl"


def test_collect_reads_source_count(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "research_manager", 4)
    e = _eng()
    oid = _os(e)
    e.connect(oid, T[1], commit=True)
    ep = e.collect_research_state(oid, "research_manager", "n", T[2], commit=True)
    assert ep.observed_count == 4


def test_collect_unknown_os(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownOSError):
        _eng().collect_research_state("AOG:nope", "research_manager", "n", T[2], commit=True)


def test_collect_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _os(e)
    e.connect(oid, T[1], commit=True)
    e.collect_research_state(oid, "research_manager", "n", T[2], commit=False)
    assert ledger.read_episodes() == []


def test_collect_multiple_layers(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _os(e)
    e.connect(oid, T[1], commit=True)
    e.collect_research_state(oid, "research_manager", "n", T[2], commit=True)
    e.collect_research_state(oid, "research_control", "n", T[3], commit=True)
    assert len(ledger.os_episodes(oid)) == 2


def test_collect_archived_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    e.create_snapshot(oid, T[3], commit=True)
    e.generate_os_report(oid, "OS", T[4], commit=True)
    e.archive_os(oid, T[5], commit=True)
    with pytest.raises(IllegalOSTransition):
        e.collect_research_state(oid, "research_manager", "n", T[6], commit=True)


# ═══════════════ READ ONLY 강제: 하위 원장 쓰기 없음 ═══════════════
@pytest.mark.parametrize("layer", ALL_LAYERS)
def test_collect_does_not_write_source(tmp_path, monkeypatch, layer):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, layer, 2)
    src_file = ledger.SOURCE_LAYERS[layer][0]
    before = open(sp(src_file)).read()
    e = _eng()
    oid = _os(e)
    e.connect(oid, T[1], commit=True)
    e.collect_research_state(oid, layer, "n", T[2], commit=True)
    after = open(sp(src_file)).read()
    assert before == after  # 소스 원장 불변(READ ONLY)


def test_no_source_file_created_when_absent(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _os(e)
    e.connect(oid, T[1], commit=True)
    e.collect_research_state(oid, "research_manager", "n", T[2], commit=True)
    # OS 는 하위 원장을 생성하지 않는다
    assert not os.path.exists(sp("rmgr_plans.jsonl"))


def test_snapshot_does_not_write_source(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "research_control", 2)
    before = open(sp("rctl_states.jsonl")).read()
    e = _eng()
    oid = _observing(e)
    e.create_snapshot(oid, T[3], commit=True)
    assert open(sp("rctl_states.jsonl")).read() == before


# ═══════════════ 모든 계층 연결 ═══════════════
def test_connect_all_layers(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _os(e)
    e.connect(oid, T[1], commit=True)
    for i, layer in enumerate(ALL_LAYERS):
        e.collect_research_state(oid, layer, "n", T[2 + i], commit=True)
    assert set(e.connected_layers(oid)) == set(ALL_LAYERS)


def test_layer_counts_covers_all(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    counts = e.layer_counts()
    assert set(counts) == set(ALL_LAYERS)


def test_source_layers_include_p12_series(tmp_path, monkeypatch):
    for layer in ("autonomous_research_pipeline", "autonomous_experiment_scheduler",
                  "research_agent_coordinator", "adaptive_research_loop",
                  "autonomous_research_evaluation", "research_optimization_engine",
                  "research_experience_memory", "research_learning", "research_manager",
                  "research_control"):
        assert layer in ledger.SOURCE_LAYERS


def test_source_layers_include_p10(tmp_path, monkeypatch):
    assert "decision_intelligence" in ledger.SOURCE_LAYERS


# ═══════════════ build_research_view ═══════════════
def test_view_not_binding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    v = e.build_research_view(oid, "LAYER_COUNTS", T[5], commit=True)
    assert v.is_binding is False


def test_view_id_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    v = e.build_research_view(oid, "LAYER_COUNTS", T[5], commit=True)
    assert v.view_id.startswith("AOV:")


def test_view_layer_counts(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "research_manager", 5)
    _seed_source(sp, "research_control", 3)
    e = _eng()
    oid = _observing(e)
    v = e.build_research_view(oid, "LAYER_COUNTS", T[5], commit=True)
    assert v.layer_counts["research_manager"] == 5
    assert v.layer_counts["research_control"] == 3
    assert v.total_records >= 8


def test_view_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    v1 = e.build_research_view(oid, "LAYER_COUNTS", T[5], commit=False)
    v2 = e.build_research_view(oid, "LAYER_COUNTS", T[5], commit=False)
    assert v1.to_dict() == v2.to_dict()


def test_view_unknown_os(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownOSError):
        _eng().build_research_view("AOG:nope", "LAYER_COUNTS", T[5], commit=True)


def test_view_all_layers_present(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    v = e.build_research_view(oid, "LAYER_COUNTS", T[5], commit=True)
    assert set(v.layer_counts) == set(ALL_LAYERS)


# ═══════════════ create_snapshot ═══════════════
def test_snapshot_transitions_analyzing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    e.create_snapshot(oid, T[5], commit=True)
    assert e.current_state(oid) == OS_ANALYZING


def test_snapshot_id_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    s = e.create_snapshot(oid, T[5], commit=True)
    assert s.snapshot_id.startswith("AOS:")


def test_snapshot_not_binding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    assert e.create_snapshot(oid, T[5], commit=True).is_binding is False


def test_snapshot_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    s1 = e.create_snapshot(oid, T[5], commit=False)
    s2 = e.create_snapshot(oid, T[5], commit=False)
    assert s1.to_dict() == s2.to_dict()


def test_snapshot_episode_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _os(e)
    e.connect(oid, T[1], commit=True)
    e.collect_research_state(oid, "research_manager", "n", T[2], commit=True)
    e.collect_research_state(oid, "research_control", "n", T[3], commit=True)
    s = e.create_snapshot(oid, T[5], commit=True)
    assert s.episode_count == 2


def test_snapshot_unknown_os(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownOSError):
        _eng().create_snapshot("AOG:nope", T[5], commit=True)


def test_snapshot_total_records(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "research_manager", 7)
    e = _eng()
    oid = _observing(e)
    s = e.create_snapshot(oid, T[5], commit=True)
    assert s.total_records >= 7


# ═══════════════ generate_os_report ═══════════════
def test_report_not_binding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    e.create_snapshot(oid, T[5], commit=True)
    r = e.generate_os_report(oid, "OS", T[6], commit=True)
    assert r.is_binding is False


def test_report_id_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    e.create_snapshot(oid, T[5], commit=True)
    r = e.generate_os_report(oid, "OS", T[6], commit=True)
    assert r.report_id.startswith("AON:")


def test_report_transitions_reporting(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    e.create_snapshot(oid, T[5], commit=True)  # → ANALYZING
    e.generate_os_report(oid, "OS", T[6], commit=True)
    assert e.current_state(oid) == OS_REPORTING


def test_report_connected_layers(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _os(e)
    e.connect(oid, T[1], commit=True)
    e.collect_research_state(oid, "research_manager", "n", T[2], commit=True)
    e.collect_research_state(oid, "research_control", "n", T[3], commit=True)
    e.create_snapshot(oid, T[5], commit=True)
    r = e.generate_os_report(oid, "OS", T[6], commit=True)
    assert r.connected_layers == 2


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    e.create_snapshot(oid, T[5], commit=True)
    r = e.generate_os_report(oid, "OS", T[6], commit=True)
    assert "DEPLOYMENT" in r.disclaimer


def test_report_unknown_os(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownOSError):
        _eng().generate_os_report("AOG:nope", "OS", T[6], commit=True)


def test_report_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    e.create_snapshot(oid, T[5], commit=True)
    r1 = e.generate_os_report(oid, "OS", T[6], commit=True).report_id
    r2 = e.generate_os_report(oid, "OS", T[6], commit=True).report_id
    assert r1 == r2
    assert len(ledger.read_reports()) == 1


# ═══════════════ archive ═══════════════
def test_archive(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    e.create_snapshot(oid, T[5], commit=True)
    e.generate_os_report(oid, "OS", T[6], commit=True)
    ev = e.archive_os(oid, T[7], commit=True)
    assert ev.to_state == OS_ARCHIVED


def test_archive_before_report_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    e.create_snapshot(oid, T[5], commit=True)  # ANALYZING
    with pytest.raises(IllegalOSTransition):
        e.archive_os(oid, T[7], commit=True)


def test_archived_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    e.create_snapshot(oid, T[5], commit=True)
    e.generate_os_report(oid, "OS", T[6], commit=True)
    e.archive_os(oid, T[7], commit=True)
    with pytest.raises(IllegalOSTransition):
        e.create_snapshot(oid, T[8], commit=True)


# ═══════════════ full lifecycle ordering ═══════════════
def test_lifecycle_states_ordered(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _os(e)
    e.connect(oid, T[1], commit=True)
    e.collect_research_state(oid, "research_manager", "n", T[2], commit=True)
    e.create_snapshot(oid, T[3], commit=True)
    e.generate_os_report(oid, "OS", T[4], commit=True)
    e.archive_os(oid, T[5], commit=True)
    states = [x["to_state"] for x in ledger.os_events(oid)]
    assert states == [OS_INITIALIZED, OS_CONNECTED, OS_OBSERVING, OS_ANALYZING, OS_REPORTING,
                      OS_ARCHIVED]


# ═══════════════ 조회 / Summary ═══════════════
def test_list_os(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _os(e, "a")
    _os(e, "b")
    assert len(e.list_os()) == 2


def test_os_meta(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _os(e, "myos")
    m = e.os_meta(oid)
    assert m["name"] == "myos"
    assert m["state"] == OS_INITIALIZED


def test_os_meta_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownOSError):
        _eng().os_meta("AOG:nope")


def test_current_state_none(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().current_state("AOG:nope") is None


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    e.create_snapshot(oid, T[3], commit=True)
    s = e.summary(T[9])
    assert s.episode_count == 1
    assert s.snapshot_count == 1


def test_summary_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().summary(T[0])
    assert s.os_event_count == 0
    assert s.artifact_count == 0


# ═══════════════ verify ═══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_verify_after_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    e.create_snapshot(oid, T[3], commit=True)
    e.generate_os_report(oid, "OS", T[4], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_integrity_engine(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _observing(e)
    assert e.verify_system_integrity()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _os(e)
    p = sp("aros_registry.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["name"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _os(e, "a")
    _os(e, "b")
    p = sp("aros_registry.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _os(e)
    p = sp("aros_registry.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    with open(p, "a") as f:
        f.write(json.dumps(rows[0]) + "\n")
    assert verify_chain()["ok"] is False


def test_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _observing(e)
    assert lifecycle_integrity()["ok"] is True


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _os(e, "a")
    _os(e, "b")
    assert duplicate_integrity()["ok"] is True


def test_reference_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    e.create_snapshot(oid, T[3], commit=True)
    assert reference_integrity()["ok"] is True


def test_binding_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    e.build_research_view(oid, "LAYER_COUNTS", T[3], commit=True)
    e.create_snapshot(oid, T[4], commit=True)
    e.generate_os_report(oid, "OS", T[5], commit=True)
    assert binding_integrity()["ok"] is True


def test_binding_integrity_detects_binding_view(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    e.build_research_view(oid, "LAYER_COUNTS", T[3], commit=True)
    p = sp("aros_views.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["is_binding"] = True
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert binding_integrity()["ok"] is False


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _observing(e)
    assert lineage_integrity()["ok"] is True


def test_reference_integrity_detects_orphan(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    p = sp("aros_episodes.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["os_id"] = "AOG:ghost"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert reference_integrity()["ok"] is False


# ═══════════════ replay 결정성 ═══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    assert replay(e, oid, T[9])["deterministic"] is True


def test_snapshot_determinism_across_engines(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    s1 = e.create_snapshot(oid, T[5], commit=False)
    s2 = _eng().create_snapshot(oid, T[5], commit=False)
    assert s1.to_dict() == s2.to_dict()


# ═══════════════ can_transition matrix ═══════════════
@pytest.mark.parametrize("frm,to,ok", [
    (OS_INITIALIZED, OS_CONNECTED, True),
    (OS_INITIALIZED, OS_OBSERVING, False),
    (OS_CONNECTED, OS_OBSERVING, True),
    (OS_CONNECTED, OS_ANALYZING, False),
    (OS_OBSERVING, OS_OBSERVING, True),
    (OS_OBSERVING, OS_ANALYZING, True),
    (OS_OBSERVING, OS_REPORTING, False),
    (OS_ANALYZING, OS_REPORTING, True),
    (OS_ANALYZING, OS_OBSERVING, True),
    (OS_ANALYZING, OS_ANALYZING, True),
    (OS_ANALYZING, OS_ARCHIVED, False),
    (OS_REPORTING, OS_ARCHIVED, True),
    (OS_REPORTING, OS_OBSERVING, True),
    (OS_ARCHIVED, OS_OBSERVING, False),
    (OS_ARCHIVED, OS_REPORTING, False),
])
def test_can_transition_matrix(frm, to, ok):
    assert can_transition(frm, to) is ok


@pytest.mark.parametrize("state", OS_STATES)
def test_states_present(state):
    assert state in OS_STATES


@pytest.mark.parametrize("state", OS_STATES)
def test_transition_map_has_state(state):
    assert state in ALLOWED_TRANSITIONS


def test_archived_no_transitions():
    assert ALLOWED_TRANSITIONS[OS_ARCHIVED] == set()


def test_six_states():
    assert len(OS_STATES) == 6


# ═══════════════ 절대 금지 능력 스캔 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb_detected(verb):
    assert is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["OBSERVE", "CONNECT", "ANALYZE", "REPORT", "SNAPSHOT", "RECORD"])
def test_allowed_verb_not_forbidden(verb):
    assert is_forbidden_verb(verb) is False


@pytest.mark.parametrize("verb", ["execute_trade", "Place_Order", "  deploy_strategy  ",
                                   "PROMOTE_MODEL", "change_permission", "allocate_capital"])
def test_forbidden_verb_normalized(verb):
    assert is_forbidden_verb(verb) is True


def test_forbidden_verb_empty():
    assert is_forbidden_verb("") is False
    assert is_forbidden_verb(None) is False


@pytest.mark.parametrize("v", ["EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL",
                                "DEPLOY_STRATEGY", "PROMOTE_MODEL", "CHANGE_PERMISSION"])
def test_forbidden_membership(v):
    assert v in FORBIDDEN_VERBS


def test_all_spec_forbidden_capabilities_present():
    # P13 스펙 절대 금지 능력이 모두 탐지 집합에 존재
    for cap in ("EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY",
                "PROMOTE_MODEL", "CHANGE_PERMISSION"):
        assert is_forbidden_verb(cap)


# ═══════════════ detect_cycle_check ═══════════════
def test_cycle_check_true():
    assert detect_cycle_check([("a", "b"), ("b", "a")]) is True


def test_cycle_check_self():
    assert detect_cycle_check([("a", "a")]) is True


def test_cycle_check_false():
    assert detect_cycle_check([("a", "b"), ("b", "c")]) is False


def test_cycle_check_empty():
    assert detect_cycle_check([]) is False


# ═══════════════ ID 결정성/구별 ═══════════════
def test_ids_distinct():
    assert M.os_id("x") != M.episode_id("x", "l", 0)
    assert M.snapshot_id("o", "t") != M.view_id("o", "k", "t")


@pytest.mark.parametrize("fn,args,prefix", [
    (M.os_id, ("n",), "AOG:"),
    (M.os_event_id, ("o", "S", 0), "AOR:"),
    (M.episode_id, ("o", "l", 0), "AOE:"),
    (M.snapshot_id, ("o", "t"), "AOS:"),
    (M.view_id, ("o", "k", "t"), "AOV:"),
    (M.report_id, ("o", "s", "t"), "AON:"),
    (M.artifact_id, ("OS", "r"), "AOF:"),
])
def test_id_prefixes(fn, args, prefix):
    assert fn(*args).startswith(prefix)


def test_content_hash_excludes_meta():
    r1 = {"a": 1, "previous_hash": "x", "record_hash": "y"}
    r2 = {"a": 1, "previous_hash": "DIFF", "record_hash": "DIFF"}
    assert content_hash(r1) == content_hash(r2)


def test_content_hash_changes():
    assert content_hash({"a": 1}) != content_hash({"a": 2})


# ═══════════════ 소스 READ ONLY 헬퍼 ═══════════════
def test_source_count_missing_layer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert ledger.source_count("nope") == 0


def test_source_count_missing_file(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert ledger.source_count("research_manager") == 0


def test_source_count_reads(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "research_learning", 6)
    assert ledger.source_count("research_learning") == 6


def test_source_ref_exists(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "research_manager", 2)
    assert ledger.source_ref_exists("research_manager", "research_manager:0") is True
    assert ledger.source_ref_exists("research_manager", "nope") is False


def test_all_layer_counts_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert ledger.all_layer_counts() == ledger.all_layer_counts()


# ═══════════════ 보안: 소스 스캔 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN_IMPORTS = (
    "jarvis.execution", "jarvis.broker", "jarvis.portfolio", "jarvis.risk",
    "jarvis.permission", "jarvis.deployment", "jarvis.live", "jarvis.order",
    "jarvis.capital_allocation", "jarvis.live_trading", "jarvis.risk_controller",
    "jarvis.portfolio_execution",
)


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_imports(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(f) for f in _FORBIDDEN_IMPORTS), node.module
        if isinstance(node, ast.Import):
            for n in node.names:
                assert not any(n.name.startswith(f) for f in _FORBIDDEN_IMPORTS), n.name


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_method_defs(path):
    tree = ast.parse(open(path).read())
    bad = ("execute_trade", "place_order", "run_order", "start_trading", "deploy_model",
           "deploy_strategy", "allocate_capital", "promote_model", "change_permission",
           "grant_permission", "liquidate", "rebalance", "auto_recover", "auto_deploy")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()


@pytest.mark.parametrize("path", _SRC)
def test_no_delete_or_update_api(path):
    src = open(path).read()
    for bad in ("def delete_", "def update_", "def remove_", "def drop_", "def overwrite_"):
        assert bad not in src, bad


def test_ledger_append_only():
    src = open(os.path.join(_PKG, "ledger.py")).read()
    assert '"a"' in src
    assert '"r+"' not in src


def test_ledger_no_source_write():
    # ledger 의 쓰기 함수(_append)는 자기 원장(ALL_LEDGERS)에만 사용됨 — 소스 원장 쓰기 함수 없음
    src = open(os.path.join(_PKG, "ledger.py")).read()
    for name in ("append_os_event", "append_episode", "append_snapshot", "append_view",
                 "append_report", "append_artifact"):
        assert name in src
    # 소스 계층에 대한 write/append 함수는 존재하지 않는다
    assert "def append_source" not in src
    assert "def write_source" not in src


@pytest.mark.parametrize("path", _SRC)
def test_source_files_mention_research(path):
    src = open(path).read()
    assert "연구" in src or "Research" in src or "research" in src


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("aros_")


def test_six_ledgers():
    assert len(ledger.ALL_LEDGERS) == 6


# ═══════════════ CLI ═══════════════
def test_cli_init(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research_os.__main__ import main
    assert main(["init", "--name", "os", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["os"]["to_state"] == OS_INITIALIZED


def test_cli_full_flow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research_os.__main__ import main
    main(["init", "--name", "os", "--commit"])
    oid = json.loads(capsys.readouterr().out)["os"]["os_id"]
    main(["connect", "--os", oid, "--commit"])
    capsys.readouterr()
    main(["observe", "--os", oid, "--layer", "research_manager", "--commit"])
    capsys.readouterr()
    main(["view", "--os", oid, "--commit"])
    capsys.readouterr()
    main(["snapshot", "--os", oid, "--commit"])
    capsys.readouterr()
    main(["report", "--os", oid, "--commit"])
    capsys.readouterr()
    assert main(["archive", "--os", oid, "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["event"]["to_state"] == OS_ARCHIVED


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research_os.__main__ import main
    assert main(["verify"]) == 0


def test_cli_layers(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research_os.__main__ import main
    assert main(["layers"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out["layer_counts"]) == set(ALL_LAYERS)


def test_cli_list(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research_os.__main__ import main
    main(["init", "--name", "os", "--commit"])
    capsys.readouterr()
    assert main(["list"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["os"]) == 1


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research_os.__main__ import main
    assert main(["summary"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["os_event_count"] == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research_os.__main__ import main
    main(["init", "--name", "os", "--commit"])
    oid = json.loads(capsys.readouterr().out)["os"]["os_id"]
    main(["connect", "--os", oid, "--commit"])
    capsys.readouterr()
    main(["observe", "--os", oid, "--layer", "research_manager", "--commit"])
    capsys.readouterr()
    assert main(["replay", "--os", oid]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


# ═══════════════ 격리 / 불변 ═══════════════
def test_no_write_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.initialize_os("os", T[0], commit=False)
    assert not os.path.exists(os.path.join(tmp_path, "aros_registry.jsonl"))


def test_records_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = e.initialize_os("os", T[0], commit=True)
    with pytest.raises(Exception):
        ev.name = "x"


def test_two_os_independent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _os(e, "a")
    b = _os(e, "b")
    e.connect(a, T[1], commit=True)
    assert e.current_state(a) == OS_CONNECTED
    assert e.current_state(b) == OS_INITIALIZED


def test_os_artifact_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _os(e)
    arts = ledger.read_artifacts()
    assert arts[0]["artifact_type"] == "OS"


def test_episode_artifact_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _os(e)
    e.connect(oid, T[1], commit=True)
    e.collect_research_state(oid, "research_manager", "n", T[2], commit=True)
    ep_arts = [a for a in ledger.read_artifacts() if a["artifact_type"] == "EPISODE"]
    assert ep_arts and ep_arts[0]["parent_artifact"]


# ═══════════════ 추가: 계층별 파라미터화 (연결·에피소드·소스파일) ═══════════════
@pytest.mark.parametrize("layer", ALL_LAYERS)
def test_each_layer_source_file_recorded(tmp_path, monkeypatch, layer):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _os(e)
    e.connect(oid, T[1], commit=True)
    ep = e.collect_research_state(oid, layer, "n", T[2], commit=True)
    assert ep.source_file == ledger.SOURCE_LAYERS[layer][0]


@pytest.mark.parametrize("layer", ALL_LAYERS)
def test_each_layer_episode_prefix(tmp_path, monkeypatch, layer):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _os(e)
    e.connect(oid, T[1], commit=True)
    ep = e.collect_research_state(oid, layer, "n", T[2], commit=True)
    assert ep.episode_id.startswith("AOE:")


@pytest.mark.parametrize("layer", ALL_LAYERS)
def test_each_layer_in_view(tmp_path, monkeypatch, layer):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    v = e.build_research_view(oid, "LAYER_COUNTS", T[5], commit=True)
    assert layer in v.layer_counts


@pytest.mark.parametrize("layer", ALL_LAYERS)
def test_each_layer_count_seeded(tmp_path, monkeypatch, layer):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, layer, 2)
    assert ledger.source_count(layer) == 2


@pytest.mark.parametrize("layer", ALL_LAYERS)
def test_each_source_spec_has_two_fields(layer):
    spec = ledger.SOURCE_LAYERS[layer]
    assert len(spec) == 2
    assert spec[0].endswith(".jsonl")


@pytest.mark.parametrize("layer", ALL_LAYERS)
def test_each_layer_snapshot_included(tmp_path, monkeypatch, layer):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    s = e.create_snapshot(oid, T[5], commit=True)
    assert layer in s.layer_counts


# ═══════════════ 추가: 원장/레코드 필드 검증 ═══════════════
@pytest.mark.parametrize("which", ledger.ALL_LEDGERS)
def test_each_ledger_prefix_and_idfield(which):
    fname, idf = which
    assert fname.startswith("aros_")
    assert isinstance(idf, str) and idf


@pytest.mark.parametrize("which", ledger.ALL_LEDGERS)
def test_each_ledger_empty_read(tmp_path, monkeypatch, which):
    _iso(tmp_path, monkeypatch)
    assert ledger.read_jsonl(which[0]) == []


@pytest.mark.parametrize("which", ledger.ALL_LEDGERS)
def test_each_ledger_verify_empty(tmp_path, monkeypatch, which):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research_os.verify import verify_ledger
    assert verify_ledger(which)["ok"] is True


# ═══════════════ 추가: 스냅샷/뷰 필드 안정성 ═══════════════
def test_snapshot_os_state_field(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    s = e.create_snapshot(oid, T[5], commit=True)
    assert s.os_state == OS_ANALYZING


def test_view_total_matches_sum(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "research_manager", 3)
    _seed_source(sp, "research_learning", 2)
    e = _eng()
    oid = _observing(e)
    v = e.build_research_view(oid, "LAYER_COUNTS", T[5], commit=True)
    assert v.total_records == sum(v.layer_counts.values())


def test_snapshot_total_matches_sum(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "research_control", 4)
    e = _eng()
    oid = _observing(e)
    s = e.create_snapshot(oid, T[5], commit=True)
    assert s.total_records == sum(s.layer_counts.values())


def test_view_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    before = len(ledger.read_artifacts())
    e.build_research_view(oid, "LAYER_COUNTS", T[5], commit=True)
    assert len(ledger.read_artifacts()) == before + 1


def test_snapshot_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    before = len(ledger.read_artifacts())
    e.create_snapshot(oid, T[5], commit=True)
    assert len(ledger.read_artifacts()) == before + 1


def test_view_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    e.build_research_view(oid, "LAYER_COUNTS", T[5], commit=False)
    assert ledger.read_views() == []


def test_snapshot_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    e.create_snapshot(oid, T[5], commit=False)
    assert ledger.read_snapshots() == []


def test_report_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    e.create_snapshot(oid, T[5], commit=True)
    e.generate_os_report(oid, "OS", T[6], commit=False)
    assert ledger.read_reports() == []


# ═══════════════ 추가: 전이 거부 케이스 ═══════════════
def test_view_archived_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    e.create_snapshot(oid, T[3], commit=True)
    e.generate_os_report(oid, "OS", T[4], commit=True)
    e.archive_os(oid, T[5], commit=True)
    with pytest.raises(IllegalOSTransition):
        e.build_research_view(oid, "LAYER_COUNTS", T[6], commit=True)


def test_report_archived_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    e.create_snapshot(oid, T[3], commit=True)
    e.generate_os_report(oid, "OS", T[4], commit=True)
    e.archive_os(oid, T[5], commit=True)
    with pytest.raises(IllegalOSTransition):
        e.generate_os_report(oid, "OS", T[6], commit=True)


def test_reobserve_from_reporting(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    e.create_snapshot(oid, T[3], commit=True)
    e.generate_os_report(oid, "OS", T[4], commit=True)  # REPORTING
    e.collect_research_state(oid, "research_control", "n", T[5], commit=True)  # → OBSERVING
    assert e.current_state(oid) == OS_OBSERVING


def test_reobserve_from_analyzing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    e.create_snapshot(oid, T[3], commit=True)  # ANALYZING
    e.collect_research_state(oid, "research_control", "n", T[4], commit=True)  # → OBSERVING
    assert e.current_state(oid) == OS_OBSERVING


def test_snapshot_from_analyzing_selfloop(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    e.create_snapshot(oid, T[3], commit=True)  # ANALYZING
    e.create_snapshot(oid, T[4], commit=True)  # ANALYZING self-loop (no forced transition)
    assert e.current_state(oid) == OS_ANALYZING


# ═══════════════ 추가: 금지 능력 def 스캔(개별) ═══════════════
@pytest.mark.parametrize("cap", ["execute_trade", "place_order", "allocate_capital",
                                  "deploy_strategy", "promote_model", "change_permission",
                                  "grant_permission", "liquidate", "rebalance", "auto_recover"])
def test_no_such_method_anywhere(cap):
    for path in _SRC:
        tree = ast.parse(open(path).read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.name != cap


@pytest.mark.parametrize("path", _SRC)
def test_no_open_write_mode(path):
    src = open(path).read()
    # 소스 파일은 'w'/'r+' 쓰기 모드로 파일을 열지 않는다(원장은 append 전용)
    if path.endswith("ledger.py"):
        assert 'open(p, "w")' not in src
        assert 'open(p, "r+")' not in src


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_call_names(path):
    tree = ast.parse(open(path).read())
    bad = {"execute_trade", "place_order", "allocate_capital", "deploy_strategy", "promote_model",
           "change_permission"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in bad
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in bad


# ═══════════════ 추가: 결정성 확장 ═══════════════
@pytest.mark.parametrize("seed", list(range(10)))
def test_snapshot_repeatable(tmp_path, monkeypatch, seed):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    a = e.create_snapshot(oid, T[5], commit=False).to_dict()
    b = e.create_snapshot(oid, T[5], commit=False).to_dict()
    assert a == b


@pytest.mark.parametrize("seed", list(range(10)))
def test_view_repeatable(tmp_path, monkeypatch, seed):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    oid = _observing(e)
    a = e.build_research_view(oid, "LAYER_COUNTS", T[5], commit=False).to_dict()
    b = e.build_research_view(oid, "LAYER_COUNTS", T[5], commit=False).to_dict()
    assert a == b


@pytest.mark.parametrize("name", ["os-a", "os-b", "research-os", "quant-os", "x"])
def test_os_id_stable(name):
    assert M.os_id(name) == M.os_id(name)


# ═══════════════ 통합 End-to-end (모든 계층 연결) ═══════════════
def test_end_to_end_full_integration(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # 모든 하위 계층 소스 시드(READ ONLY 대상)
    for i, layer in enumerate(ALL_LAYERS):
        _seed_source(sp, layer, i + 1)
    e = _eng()
    oid = e.initialize_os("jarvis-research-os", T[0], commit=True).os_id
    assert e.current_state(oid) == OS_INITIALIZED
    e.connect(oid, T[1], commit=True)
    assert e.current_state(oid) == OS_CONNECTED
    # 모든 계층 관찰
    for i, layer in enumerate(ALL_LAYERS):
        ep = e.collect_research_state(oid, layer, "observe", T[2 + i], commit=True)
        assert ep.observed_count == i + 1
    assert e.current_state(oid) == OS_OBSERVING
    assert set(e.connected_layers(oid)) == set(ALL_LAYERS)
    # 지식 뷰
    v = e.build_research_view(oid, "LAYER_COUNTS", T[30], commit=True)
    assert set(v.layer_counts) == set(ALL_LAYERS)
    assert v.is_binding is False
    # 스냅샷
    snap = e.create_snapshot(oid, T[31], commit=True)
    assert e.current_state(oid) == OS_ANALYZING
    assert snap.episode_count == len(ALL_LAYERS)
    assert snap.is_binding is False
    # 리포트
    r = e.generate_os_report(oid, "OS", T[32], commit=True)
    assert e.current_state(oid) == OS_REPORTING
    assert r.connected_layers == len(ALL_LAYERS)
    assert r.is_binding is False
    # 보관
    e.archive_os(oid, T[33], commit=True)
    assert e.current_state(oid) == OS_ARCHIVED
    # 무결성 + 결정성
    res = verify_chain()
    assert res["ok"] is True
    assert res["binding"]["ok"] is True
    assert res["lineage"]["ok"] is True
    # 소스 원장은 변경되지 않았다(READ ONLY)
    for layer in ALL_LAYERS:
        assert ledger.source_count(layer) == ALL_LAYERS.index(layer) + 1
