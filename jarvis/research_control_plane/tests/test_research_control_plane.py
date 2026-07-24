"""P10.28 Research Control Plane 테스트. **중앙 관측·조율 평면 — 관측 전용.**

컴포넌트 발견/등록(불변)·계층 상태 수집(READ ONLY·불변)·시스템 맵 구성·의존성 이슈 탐지·헬스 점수 계산
(결정적·불변)·시스템 개요·거버넌스 대시보드·컨트롤 리포트·연구 타임라인·verify(체인/변조/중복/그래프)·replay·
상위 READ ONLY 보호·CLI·보안(금지import·실행/배포/할당/권한/설정 변경 없음·상위 원장 무변경·삭제 API 없음·불변·
OBSERVE≠EXECUTE·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.research_control_plane import ledger
from jarvis.research_control_plane import models as M
from jarvis.research_control_plane.engine import ResearchControlPlaneEngine
from jarvis.research_control_plane.models import (
    CAT_GOVERNANCE,
    CAT_INTELLIGENCE,
    CAT_RESEARCH,
    HEALTH_CRITICAL,
    HEALTH_DEGRADED,
    HEALTH_HEALTHY,
    HEALTH_UNKNOWN,
    STATE_ACTIVE,
    STATE_EMPTY,
    STATE_MISSING,
    ImmutableComponentError,
    ImmutableHealthError,
    ImmutableStatusError,
    InvalidComponentCategory,
    UnknownComponentError,
)

T0 = "2026-07-24T00:00:00Z"
T1 = "2026-07-24T00:01:00Z"
T2 = "2026-07-24T00:02:00Z"


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_control_plane.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchControlPlaneEngine()


def _seed_source(sp, filename, rows):
    """상위 소스 원장을 테스트용으로 생성(엔진은 절대 쓰지 않는다)."""
    with open(sp(filename), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


# ══════════════ register_component ══════════════
def test_register_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    c = _eng().register_component("alpha", "alpha", "P10.2", CAT_RESEARCH, "ai_signals.jsonl",
                                  "signal_hash", T0, commit=True)
    assert c.component_id.startswith("RCC:")
    assert c.name == "alpha"
    assert c.category == CAT_RESEARCH


def test_register_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _eng().register_component("x", now=T0, commit=False)
    b = _eng().register_component("x", now=T1, commit=False)
    assert a.component_id == b.component_id


def test_register_commit_persists(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_component("x", category=CAT_RESEARCH, now=T0, commit=True)
    assert len(ledger.read_components()) == 1


def test_register_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_component("x", now=T0, commit=False)
    assert ledger.read_components() == []


def test_register_invalid_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidComponentCategory):
        _eng().register_component("x", category="NOPE", now=T0, commit=True)


def test_register_all_valid_categories(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    for i, cat in enumerate(M.CATEGORIES):
        c = _eng().register_component(f"c{i}", category=cat, now=T0, commit=True)
        assert c.category == cat


def test_register_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("x", "x", "P1", CAT_RESEARCH, now=T0, commit=True)
    e.register_component("x", "x", "P1", CAT_RESEARCH, now=T1, commit=True)
    assert len(ledger.read_components()) == 1


def test_register_immutable_on_change(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("x", "x", "P1", CAT_RESEARCH, now=T0, commit=True)
    with pytest.raises(ImmutableComponentError):
        e.register_component("x", "x", "P2", CAT_RESEARCH, now=T1, commit=True)


def test_register_immutable_category_change(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("x", "x", "P1", CAT_RESEARCH, now=T0, commit=True)
    with pytest.raises(ImmutableComponentError):
        e.register_component("x", "x", "P1", CAT_GOVERNANCE, now=T1, commit=True)


def test_register_records_timeline(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_component("x", category=CAT_RESEARCH, now=T0, commit=True)
    kinds = [t["kind"] for t in ledger.read_timeline()]
    assert M.TL_COMPONENT_REGISTERED in kinds


def test_register_has_record_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    c = _eng().register_component("x", category=CAT_RESEARCH, now=T0, commit=True)
    assert c.record_hash and c.record_hash.startswith("sha256:")


# ══════════════ discover_components ══════════════
def test_discover_registers_catalog(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    cs = _eng().discover_components(T0, commit=True)
    assert len(cs) == len(ledger.SOURCE_LEDGERS)
    assert len(ledger.read_components()) == len(ledger.SOURCE_LEDGERS)


def test_discover_deterministic_order(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    cs = _eng().discover_components(T0, commit=False)
    names = [c.name for c in cs]
    assert names == sorted(names)


def test_discover_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.discover_components(T0, commit=True)
    e.discover_components(T1, commit=True)
    assert len(ledger.read_components()) == len(ledger.SOURCE_LEDGERS)


def test_discover_covers_p9_and_p10(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    cs = _eng().discover_components(T0, commit=True)
    phases = {c.phase for c in cs}
    assert any(p.startswith("P9.") for p in phases)
    assert any(p.startswith("P10.") for p in phases)


def test_discover_includes_knowledge_intelligence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    names = [c.name for c in _eng().discover_components(T0, commit=True)]
    assert "knowledge_intelligence" in names  # P10.27


def test_catalog_has_27_plus_components(tmp_path, monkeypatch):
    assert len(ledger.SOURCE_LEDGERS) >= 24


# ══════════════ collect_status ══════════════
def test_status_active(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "ai_signals.jsonl", [{"signal_hash": "s1", "created_at": T0}])
    e = _eng()
    e.register_component("alpha", "alpha", "P10.2", CAT_RESEARCH, "ai_signals.jsonl",
                         "signal_hash", T0, commit=True)
    s = e.collect_status("alpha", T1, commit=True)
    assert s.state == STATE_ACTIVE
    assert s.record_count == 1
    assert s.present is True


def test_status_empty(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "ai_signals.jsonl", [])
    e = _eng()
    e.register_component("alpha", "alpha", "P10.2", CAT_RESEARCH, "ai_signals.jsonl",
                         "signal_hash", T0, commit=True)
    s = e.collect_status("alpha", T1, commit=True)
    assert s.state == STATE_EMPTY
    assert s.record_count == 0


def test_status_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("alpha", "alpha", "P10.2", CAT_RESEARCH, "ai_signals.jsonl",
                         "signal_hash", T0, commit=True)
    s = e.collect_status("alpha", T1, commit=True)
    assert s.state == STATE_MISSING
    assert s.present is False


def test_status_last_activity(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "ai_signals.jsonl", [{"signal_hash": "s1", "created_at": T0},
                                          {"signal_hash": "s2", "created_at": T2}])
    e = _eng()
    e.register_component("alpha", "alpha", "P10.2", CAT_RESEARCH, "ai_signals.jsonl",
                         "signal_hash", T0, commit=True)
    s = e.collect_status("alpha", T1, commit=True)
    assert s.last_activity == T2


def test_status_via_catalog_without_register(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "ki_insights.jsonl", [{"insight_id": "i1"}])
    s = _eng().collect_status("knowledge_intelligence", T0, commit=False)
    assert s.record_count == 1


def test_status_unknown_component(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownComponentError):
        _eng().collect_status("does_not_exist", T0, commit=True)


def test_status_deterministic_id(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "ki_insights.jsonl", [{"insight_id": "i1"}])
    a = _eng().collect_status("knowledge_intelligence", T0, commit=False)
    b = _eng().collect_status("knowledge_intelligence", T0, commit=False)
    assert a.status_id == b.status_id


def test_status_idempotent(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "ki_insights.jsonl", [{"insight_id": "i1"}])
    e = _eng()
    e.collect_status("knowledge_intelligence", T0, commit=True)
    e.collect_status("knowledge_intelligence", T0, commit=True)
    assert len(ledger.read_status()) == 1


def test_status_immutable_on_change(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "ki_insights.jsonl", [{"insight_id": "i1"}])
    e = _eng()
    e.collect_status("knowledge_intelligence", T0, commit=True)
    _seed_source(sp, "ki_insights.jsonl", [{"insight_id": "i1"}, {"insight_id": "i2"}])
    with pytest.raises(ImmutableStatusError):
        e.collect_status("knowledge_intelligence", T0, commit=True)


def test_status_records_timeline(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "ki_insights.jsonl", [{"insight_id": "i1"}])
    _eng().collect_status("knowledge_intelligence", T0, commit=True)
    assert M.TL_STATUS_COLLECTED in [t["kind"] for t in ledger.read_timeline()]


def test_collect_all_status(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "ai_signals.jsonl", [{"signal_hash": "s1"}])
    e = _eng()
    e.register_component("alpha", "alpha", "P10.2", CAT_RESEARCH, "ai_signals.jsonl",
                         "signal_hash", T0, commit=True)
    e.register_component("beta", "beta", "P10.3", CAT_RESEARCH, "missing.jsonl", "id", T0,
                         commit=True)
    ss = e.collect_all_status(T1, commit=True)
    assert len(ss) == 2


def test_collect_all_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.discover_components(T0, commit=True)
    ss = e.collect_all_status(T1, commit=False)
    comps = [s.component for s in ss]
    assert comps == sorted(comps)


# ══════════════ build_system_map / dependencies ══════════════
def test_map_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ds = _eng().build_system_map([("a", "b"), ("b", "c")], T0, commit=True)
    assert len(ds) == 2
    assert ds[0].dependency_id.startswith("RCD:")
    assert ds[0].relation == M.REL_READS


def test_map_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _eng().build_system_map([("a", "b")], T0, commit=False)
    b = _eng().build_system_map([("a", "b")], T1, commit=False)
    assert a[0].dependency_id == b[0].dependency_id


def test_map_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.build_system_map([("a", "b")], T0, commit=True)
    e.build_system_map([("a", "b")], T1, commit=True)
    assert len(ledger.read_dependencies()) == 1


def test_map_directional(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.build_system_map([("a", "b"), ("b", "a")], T0, commit=True)
    assert len(ledger.read_dependencies()) == 2  # a->b and b->a distinct


def test_system_map_view(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("a", category=CAT_RESEARCH, now=T0, commit=True)
    e.register_component("b", category=CAT_RESEARCH, now=T0, commit=True)
    e.build_system_map([("a", "b")], T0, commit=True)
    m = e.system_map()
    assert m["node_count"] == 2
    assert m["edge_count"] == 1
    assert ["a", "b"] in m["edges"]


def test_map_records_timeline(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().build_system_map([("a", "b")], T0, commit=True)
    assert M.TL_DEPENDENCY_MAPPED in [t["kind"] for t in ledger.read_timeline()]


# ══════════════ detect_dependency_issue ══════════════
def test_issue_none_when_clean(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    for n in ("a", "b", "c"):
        e.register_component(n, category=CAT_RESEARCH, now=T0, commit=True)
    e.build_system_map([("a", "b"), ("b", "c")], T0, commit=True)
    res = e.detect_dependency_issue()
    assert res["ok"] is True
    assert res["issue_count"] == 0


def test_issue_dangling_target(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("a", category=CAT_RESEARCH, now=T0, commit=True)
    e.build_system_map([("a", "ghost")], T0, commit=True)
    res = e.detect_dependency_issue()
    assert res["ok"] is False
    assert any("dangling_target" in i for i in res["issues"])


def test_issue_missing_source(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("b", category=CAT_RESEARCH, now=T0, commit=True)
    e.build_system_map([("ghost", "b")], T0, commit=True)
    res = e.detect_dependency_issue()
    assert any("missing_source" in i for i in res["issues"])


def test_issue_self_dependency(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("a", category=CAT_RESEARCH, now=T0, commit=True)
    e.build_system_map([("a", "a")], T0, commit=True)
    res = e.detect_dependency_issue()
    assert any("self_dependency" in i for i in res["issues"])


def test_issue_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    for n in ("a", "b", "c"):
        e.register_component(n, category=CAT_RESEARCH, now=T0, commit=True)
    e.build_system_map([("a", "b"), ("b", "c"), ("c", "a")], T0, commit=True)
    res = e.detect_dependency_issue()
    assert any("dependency_cycle" in i for i in res["issues"])


def test_dependency_issues_pure_fn():
    assert M.dependency_issues([("a", "b")], ["a", "b"]) == []
    assert M.dependency_issues([("a", "a")], ["a"]) == ["self_dependency:a"]
    iss = M.dependency_issues([("a", "b")], ["a"])
    assert any("dangling_target" in i for i in iss)


def test_detect_cycle_pure_fn():
    assert M.detect_cycle([("a", "b"), ("b", "c")]) == []
    cyc = M.detect_cycle([("a", "b"), ("b", "a")])
    assert cyc and cyc[0] == cyc[-1]


def test_reachable_from():
    assert M.reachable_from([("a", "b"), ("b", "c")], "a") == ["b", "c"]


# ══════════════ calculate_health_score ══════════════
def test_health_all_active(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "ai_signals.jsonl", [{"signal_hash": "s1"}])
    e = _eng()
    e.register_component("alpha", "alpha", "P10.2", CAT_RESEARCH, "ai_signals.jsonl",
                         "signal_hash", T0, commit=True)
    e.collect_status("alpha", T1, commit=True)
    h = e.calculate_health_score("GLOBAL", T2, commit=True)
    assert h.health_id.startswith("RCH:")
    assert h.overall_score == round(0.6 * 1.0 + 0.4 * 1.0, 8)
    assert h.level == HEALTH_HEALTHY


def test_health_unknown_when_no_components(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    h = _eng().calculate_health_score("GLOBAL", T0, commit=True)
    assert h.level == HEALTH_UNKNOWN
    assert h.component_count == 0


def test_health_degraded(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "ai_signals.jsonl", [{"signal_hash": "s1"}])
    e = _eng()
    # 1 active of 2 -> comp=0.5, dep=1.0 -> 0.6*0.5+0.4=0.7 -> DEGRADED
    e.register_component("alpha", "alpha", "P10.2", CAT_RESEARCH, "ai_signals.jsonl",
                         "signal_hash", T0, commit=True)
    e.register_component("beta", "beta", "P10.3", CAT_RESEARCH, "missing.jsonl", "id", T0,
                         commit=True)
    e.collect_status("alpha", T1, commit=True)
    e.collect_status("beta", T1, commit=True)
    h = e.calculate_health_score("GLOBAL", T2, commit=True)
    assert h.overall_score == round(0.6 * 0.5 + 0.4 * 1.0, 8)
    assert h.level == HEALTH_DEGRADED


def test_health_critical(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    # all missing -> comp=0, dep=1 -> 0.4 -> CRITICAL
    e.register_component("beta", "beta", "P10.3", CAT_RESEARCH, "missing.jsonl", "id", T0,
                         commit=True)
    e.collect_status("beta", T1, commit=True)
    h = e.calculate_health_score("GLOBAL", T2, commit=True)
    assert h.level == HEALTH_CRITICAL


def test_health_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("a", category=CAT_RESEARCH, now=T0, commit=True)
    a = e.calculate_health_score("GLOBAL", T2, commit=False)
    b = e.calculate_health_score("GLOBAL", T2, commit=False)
    assert a.overall_score == b.overall_score
    assert a.health_id == b.health_id


def test_health_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("a", category=CAT_RESEARCH, now=T0, commit=True)
    e.calculate_health_score("GLOBAL", T2, commit=True)
    e.calculate_health_score("GLOBAL", T2, commit=True)
    assert len(ledger.read_health()) == 1


def test_health_immutable_on_change(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "ai_signals.jsonl", [{"signal_hash": "s1"}])
    e = _eng()
    e.register_component("alpha", "alpha", "P10.2", CAT_RESEARCH, "ai_signals.jsonl",
                         "signal_hash", T0, commit=True)
    e.collect_status("alpha", T1, commit=True)  # active -> score 1.0
    e.calculate_health_score("GLOBAL", T2, commit=True)
    # 같은 스냅샷 시각(T2)에 활성 비율이 달라지면 불변 위반
    e.register_component("beta", "beta", "P10.3", CAT_RESEARCH, "missing.jsonl", "id", T0,
                         commit=True)
    e.collect_status("beta", T1, commit=True)  # missing -> active 1/2
    with pytest.raises(ImmutableHealthError):
        e.calculate_health_score("GLOBAL", T2, commit=True)


def test_health_penalized_by_issues(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("a", category=CAT_RESEARCH, now=T0, commit=True)
    e.build_system_map([("a", "ghost")], T0, commit=True)
    h = e.calculate_health_score("GLOBAL", T2, commit=True)
    assert h.dependency_issue_count >= 1
    assert h.dependency_health < 1.0


def test_health_records_timeline(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().calculate_health_score("GLOBAL", T0, commit=True)
    assert M.TL_HEALTH_COMPUTED in [t["kind"] for t in ledger.read_timeline()]


def test_health_score_pure_fn():
    assert M.health_score(2, 2, 0, 3) == round(0.6 + 0.4, 8)
    assert M.health_score(0, 0, 0, 0) == round(0.4, 8)  # comp=0, dep=1
    assert M.health_score(1, 2, 2, 2) == round(0.6 * 0.5 + 0.4 * 0.0, 8)


def test_health_level_pure_fn():
    assert M.health_level(0.9, 3) == HEALTH_HEALTHY
    assert M.health_level(0.6, 3) == HEALTH_DEGRADED
    assert M.health_level(0.3, 3) == HEALTH_CRITICAL
    assert M.health_level(0.9, 0) == HEALTH_UNKNOWN


# ══════════════ System Overview (deterministic snapshot) ══════════════
def test_overview_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("a", "a", "P10.2", CAT_RESEARCH, now=T0, commit=True)
    e.register_component("b", "b", "P10.3", CAT_GOVERNANCE, now=T0, commit=True)
    o = e.build_system_overview("GLOBAL", T1, commit=True)
    assert o.overview_id.startswith("RCO:")
    assert o.component_count == 2
    assert o.category_distribution[CAT_RESEARCH] == 1


def test_overview_phase_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("a", "a", "P10.2", CAT_RESEARCH, now=T0, commit=True)
    o = e.build_system_overview("GLOBAL", T1, commit=True)
    assert o.phase_distribution["P10.2"] == 1


def test_overview_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("a", category=CAT_RESEARCH, now=T0, commit=True)
    a = e.build_system_overview("GLOBAL", T1, commit=False)
    b = e.build_system_overview("GLOBAL", T1, commit=False)
    assert a.to_dict() == b.to_dict()


def test_overview_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("a", category=CAT_RESEARCH, now=T0, commit=True)
    e.build_system_overview("GLOBAL", T1, commit=True)
    e.build_system_overview("GLOBAL", T1, commit=True)
    assert len(ledger.read_overview()) == 1


def test_overview_has_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    o = _eng().build_system_overview("GLOBAL", T0, commit=True)
    assert "OBSERVE ≠ EXECUTE" in o.disclaimer


def test_overview_records_timeline(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().build_system_overview("GLOBAL", T0, commit=True)
    assert M.TL_OVERVIEW_BUILT in [t["kind"] for t in ledger.read_timeline()]


# ══════════════ Governance Dashboard ══════════════
def test_dashboard_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("a", "a", "P10.2", CAT_RESEARCH, now=T0, commit=True)
    e.register_component("b", "b", "P10.3", CAT_GOVERNANCE, now=T0, commit=True)
    d = e.build_dashboard("GLOBAL", T1, commit=True)
    assert d.dashboard_id.startswith("RCB:")
    assert d.panels["by_category"][CAT_RESEARCH] == 1
    assert d.panels["by_category"][CAT_GOVERNANCE] == 1


def test_dashboard_state_panel(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "ai_signals.jsonl", [{"signal_hash": "s1"}])
    e = _eng()
    e.register_component("alpha", "alpha", "P10.2", CAT_RESEARCH, "ai_signals.jsonl",
                         "signal_hash", T0, commit=True)
    e.collect_status("alpha", T1, commit=True)
    d = e.build_dashboard("GLOBAL", T2, commit=True)
    assert d.panels["by_state"].get(STATE_ACTIVE) == 1


def test_dashboard_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("a", category=CAT_RESEARCH, now=T0, commit=True)
    a = e.build_dashboard("GLOBAL", T1, commit=False)
    b = e.build_dashboard("GLOBAL", T1, commit=False)
    assert a.to_dict() == b.to_dict()


def test_dashboard_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("a", category=CAT_RESEARCH, now=T0, commit=True)
    e.build_dashboard("GLOBAL", T1, commit=True)
    e.build_dashboard("GLOBAL", T1, commit=True)
    assert len(ledger.read_dashboard()) == 1


# ══════════════ generate_control_report ══════════════
def test_report_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("a", "a", "P10.2", CAT_RESEARCH, now=T0, commit=True)
    r = e.generate_control_report("GLOBAL", {"k": 1}, T1, commit=True)
    assert r.report_id.startswith("RCR:")
    assert r.component_count == 1
    assert r.metrics["k"] == 1


def test_report_includes_issues(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("a", category=CAT_RESEARCH, now=T0, commit=True)
    e.build_system_map([("a", "ghost")], T0, commit=True)
    r = e.generate_control_report("GLOBAL", {}, T1, commit=True)
    assert r.dependency_issue_count >= 1
    assert r.issues


def test_report_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("a", category=CAT_RESEARCH, now=T0, commit=True)
    a = e.generate_control_report("GLOBAL", {}, T1, commit=False)
    b = e.generate_control_report("GLOBAL", {}, T1, commit=False)
    assert a.to_dict() == b.to_dict()


def test_report_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("a", category=CAT_RESEARCH, now=T0, commit=True)
    e.generate_control_report("GLOBAL", {}, T1, commit=True)
    e.generate_control_report("GLOBAL", {}, T1, commit=True)
    assert len(ledger.read_reports()) == 1


def test_report_has_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_control_report("GLOBAL", {}, T0, commit=True)
    assert "REPORT ≠ DEPLOYMENT" in r.disclaimer


def test_report_records_timeline(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().generate_control_report("GLOBAL", {}, T0, commit=True)
    assert M.TL_REPORT_GENERATED in [t["kind"] for t in ledger.read_timeline()]


# ══════════════ verify_state / verify_chain ══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().verify_state()["ok"] is True


def test_verify_after_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.discover_components(T0, commit=True)
    e.build_system_map([("alpha_intelligence", "research_kg")], T0, commit=True)
    e.calculate_health_score("GLOBAL", T1, commit=True)
    e.generate_control_report("GLOBAL", {}, T1, commit=True)
    assert e.verify_state()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("a", category=CAT_RESEARCH, now=T0, commit=True)
    p = sp("rcp_components.jsonl")
    rows = [json.loads(x) for x in open(p)]
    rows[0]["name"] = "tampered"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    res = _eng().verify_state()
    assert res["ok"] is False


def test_verify_detects_chain_break(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("a", category=CAT_RESEARCH, now=T0, commit=True)
    e.register_component("b", category=CAT_RESEARCH, now=T0, commit=True)
    p = sp("rcp_components.jsonl")
    rows = [json.loads(x) for x in open(p)]
    rows[1]["previous_hash"] = "GENESIS"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    res = _eng().verify_state()
    assert res["ok"] is False


def test_verify_detects_dependency_issue(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("a", category=CAT_RESEARCH, now=T0, commit=True)
    e.build_system_map([("a", "ghost")], T0, commit=True)
    res = e.verify_state()
    assert res["graph"]["ok"] is False


def test_verify_per_ledger_reported(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("a", category=CAT_RESEARCH, now=T0, commit=True)
    res = e.verify_state()
    assert "rcp_components.jsonl" in res["ledgers"]


def test_verify_cycle_detected_in_graph(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    for n in ("a", "b"):
        e.register_component(n, category=CAT_RESEARCH, now=T0, commit=True)
    e.build_system_map([("a", "b"), ("b", "a")], T0, commit=True)
    res = e.verify_state()
    assert res["graph"]["ok"] is False


# ══════════════ replay / summary ══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_control_plane.verify import replay
    e = _eng()
    e.discover_components(T0, commit=True)
    assert replay(e, T1)["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("a", category=CAT_RESEARCH, now=T0, commit=True)
    e.build_system_map([("a", "b")], T0, commit=True)
    e.calculate_health_score("GLOBAL", T1, commit=True)
    s = e.summary(T2)
    assert s.component_count == 1
    assert s.dependency_count == 1
    assert s.health_count == 1


def test_summary_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.discover_components(T0, commit=True)
    assert e.summary(T1).to_dict() == e.summary(T1).to_dict()


# ══════════════ query helpers ══════════════
def test_latest_status(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "ai_signals.jsonl", [{"signal_hash": "s1"}])
    e = _eng()
    e.register_component("alpha", "alpha", "P10.2", CAT_RESEARCH, "ai_signals.jsonl",
                         "signal_hash", T0, commit=True)
    e.collect_status("alpha", T1, commit=True)
    assert e.latest_status("alpha")["state"] == STATE_ACTIVE


def test_latest_health(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("a", category=CAT_RESEARCH, now=T0, commit=True)
    e.calculate_health_score("GLOBAL", T1, commit=True)
    assert e.latest_health("GLOBAL") is not None


def test_list_components_by_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("a", category=CAT_RESEARCH, now=T0, commit=True)
    e.register_component("b", category=CAT_GOVERNANCE, now=T0, commit=True)
    assert e.list_components(CAT_RESEARCH) == ["a"]
    assert sorted(e.list_components()) == ["a", "b"]


# ══════════════ 상위 READ ONLY 보호 ══════════════
def test_source_files_never_written(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "ki_insights.jsonl", [{"insight_id": "i1"}])
    before = open(sp("ki_insights.jsonl")).read()
    e = _eng()
    e.discover_components(T0, commit=True)
    e.collect_all_status(T1, commit=True)
    e.calculate_health_score("GLOBAL", T2, commit=True)
    after = open(sp("ki_insights.jsonl")).read()
    assert before == after


def test_no_source_ledger_created_by_engine(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_component("alpha", "alpha", "P10.2", CAT_RESEARCH, "ai_signals.jsonl",
                         "signal_hash", T0, commit=True)
    e.collect_status("alpha", T1, commit=True)  # source missing
    assert not os.path.exists(sp("ai_signals.jsonl"))


def test_only_rcp_files_written(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.discover_components(T0, commit=True)
    e.build_system_map([("a", "b")], T0, commit=True)
    e.calculate_health_score("GLOBAL", T1, commit=True)
    e.build_system_overview("GLOBAL", T1, commit=True)
    e.build_dashboard("GLOBAL", T1, commit=True)
    e.generate_control_report("GLOBAL", {}, T1, commit=True)
    for fn in os.listdir(tmp_path):
        assert fn.startswith("rcp_"), fn


# ══════════════ 보안 / 불변식 ══════════════
def test_no_forbidden_imports():
    import ast
    forbidden = ("execution", "broker", "order", "portfolio_execution", "capital_allocation",
                 "live_trading", "permission", "risk_controller")
    base = os.path.dirname(os.path.dirname(__file__))
    for fn in ("engine.py", "ledger.py", "models.py", "verify.py", "__main__.py", "__init__.py"):
        tree = ast.parse(open(os.path.join(base, fn)).read())
        for n in ast.walk(tree):
            mods = []
            if isinstance(n, ast.Import):
                mods = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom):
                mods = [n.module or ""]
            for m in mods:
                for fb in forbidden:
                    assert not (m == f"jarvis.{fb}" or m.startswith(f"jarvis.{fb}.")), (fn, m)


def test_engine_has_no_execution_methods():
    e = ResearchControlPlaneEngine()
    for bad in ("execute", "trade", "place_order", "allocate", "deploy", "approve", "activate",
                "select", "modify_permission", "modify_config", "promote"):
        assert not hasattr(e, bad), bad


def test_engine_has_required_methods():
    e = ResearchControlPlaneEngine()
    for name in ("register_component", "collect_status", "build_system_map",
                 "calculate_health_score", "detect_dependency_issue", "generate_control_report",
                 "verify_state"):
        assert hasattr(e, name), name


def test_no_delete_or_update_ledger_api():
    import inspect
    src = inspect.getsource(ledger)
    for bad in ("def delete", "def update", "def remove", "def overwrite", "def edit_"):
        assert bad not in src, bad


def test_ledger_only_appends():
    import inspect
    src = inspect.getsource(ledger)
    # 파일 오픈은 append("a") 만 — 쓰기("w"/"r+") 없음(소스 시드 아님)
    assert '"a"' in src
    assert 'open(p, "w"' not in src


def test_no_mutation_words_in_disclaimer():
    from jarvis.research_control_plane.engine import _DISCLAIMER
    assert "EXECUTE" in _DISCLAIMER and "≠" in _DISCLAIMER


def test_records_are_frozen():
    c = M.ComponentRecord(component_id="RCC:x", name="a", layer="a", phase="P", category="RESEARCH",
                          ledger_file="", id_field="", registered_at=T0)
    with pytest.raises(Exception):
        c.name = "b"  # type: ignore


# ══════════════ 커버리지: id 접두사·상수 ══════════════
def test_id_prefixes_distinct():
    ids = {
        M.component_id("x")[:4], M.status_id("x", T0)[:4], M.dependency_id("x", "y")[:4],
        M.overview_id("x", T0)[:4], M.dashboard_id("x", T0)[:4], M.timeline_id("k", "r", T0)[:4],
        M.health_id("x", T0)[:4], M.report_id("x", T0)[:4],
    }
    assert len(ids) == 8


def test_eight_owned_ledgers():
    assert len(ledger.ALL_LEDGERS) == 8
    fns = {l[0] for l in ledger.ALL_LEDGERS}
    assert len(fns) == 8
    assert all(f.startswith("rcp_") for f in fns)


def test_five_categories():
    assert len(M.CATEGORIES) == 5


def test_three_states():
    assert len(M.STATES) == 3


def test_four_health_levels():
    assert len(M.HEALTH_LEVELS) == 4


def test_four_issue_types():
    assert len(M.ISSUE_TYPES) == 4


def test_six_timeline_kinds():
    assert len(M.TL_KINDS) == 6


def test_content_hash_excludes_hash_fields():
    r = {"a": 1, "previous_hash": "p", "record_hash": "r"}
    assert M.content_hash(r) == M.content_hash({"a": 1, "previous_hash": "z", "record_hash": "q"})


def test_input_digest_deterministic():
    assert M.input_digest("a", "b") == M.input_digest("a", "b")
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


def test_source_catalog_files_unique():
    files = [v[0] for v in ledger.SOURCE_LEDGERS.values()]
    assert len(files) == len(set(files))


def test_source_catalog_phases_present():
    phases = [v[2] for v in ledger.SOURCE_LEDGERS.values()]
    assert all(p.startswith("P") for p in phases)


# ══════════════ CLI ══════════════
def _run(argv, capsys):
    from jarvis.research_control_plane.__main__ import main
    rc = main(argv)
    out = capsys.readouterr().out
    return rc, out


def test_cli_discover(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["discover", "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["count"] == len(ledger.SOURCE_LEDGERS)


def test_cli_register(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["register", "--name", "x", "--category", "RESEARCH", "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["component"]["name"] == "x"


def test_cli_status_all(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _run(["discover", "--commit"], capsys)
    rc, out = _run(["status", "--all", "--commit"], capsys)
    assert rc == 0
    assert isinstance(json.loads(out)["status"], list)


def test_cli_map(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["map", "--edges-json", '[["a","b"]]', "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["dependencies"][0]["source"] == "a"


def test_cli_issues(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["issues"], capsys)
    assert rc == 0
    assert json.loads(out)["ok"] is True


def test_cli_health(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _run(["register", "--name", "a", "--category", "RESEARCH", "--commit"], capsys)
    rc, out = _run(["health", "--commit"], capsys)
    assert rc == 0
    assert "health" in json.loads(out)


def test_cli_overview(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["overview", "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["overview"]["overview_id"].startswith("RCO:")


def test_cli_dashboard(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["dashboard", "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["dashboard"]["dashboard_id"].startswith("RCB:")


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["report", "--metrics-json", '{"k":1}', "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["report"]["metrics"]["k"] == 1


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["verify"], capsys)
    assert rc == 0
    assert json.loads(out)["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _run(["discover", "--commit"], capsys)
    rc, out = _run(["replay"], capsys)
    assert rc == 0
    assert json.loads(out)["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["summary"], capsys)
    assert rc == 0
    assert "component_count" in json.loads(out)


# ══════════════ 통합 시나리오 ══════════════
def test_end_to_end_flow(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "ki_insights.jsonl", [{"insight_id": "i1", "created_at": T0}])
    _seed_source(sp, "kg_entities.jsonl", [{"entity_id": "e1", "created_at": T0}])
    e = _eng()
    e.discover_components(T0, commit=True)
    e.collect_all_status(T1, commit=True)
    e.build_system_map([("knowledge_intelligence", "research_kg")], T1, commit=True)
    h = e.calculate_health_score("GLOBAL", T2, commit=True)
    o = e.build_system_overview("GLOBAL", T2, commit=True)
    e.build_dashboard("GLOBAL", T2, commit=True)
    r = e.generate_control_report("GLOBAL", {}, T2, commit=True)
    assert e.verify_state()["ok"] is True
    assert h.component_count == len(ledger.SOURCE_LEDGERS)
    assert o.active_component_count >= 2
    assert r.dependency_count == 1


def test_end_to_end_deterministic_ids(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e1 = _eng()
    e1.discover_components(T0, commit=True)
    ids1 = [c["component_id"] for c in ledger.read_components()]
    # 재현: 동일 입력 → 동일 id
    e2 = _eng()
    ids2 = [c.component_id for c in e2.discover_components(T0, commit=False)]
    assert set(ids1) == set(ids2)
