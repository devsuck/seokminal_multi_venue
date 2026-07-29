"""P10.10 Research Observatory & Control Plane 테스트. **관측 전용.**

관측 스냅샷(불변)·생명주기(CREATED→COLLECTING→ANALYZING→REPORTING→ARCHIVED, 차단전이)·교차계층
지표 수집·의존 그래프(broken/cycle)·타임라인·트렌드(방향 라벨)·대시보드·리포트·verify(체인/변조/중복/
의존/타임라인/고아/순환)·replay·상위 READ ONLY 보호·CLI·보안(금지import·선택/승인/배포/실행/자본배분/
권한/config/autonomy 없음·상위 원장 무변경·삭제 API 없음·불변·OBSERVED≠APPROVED·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from jarvis.research_observatory import ledger
from jarvis.research_observatory import models as M
from jarvis.research_observatory.engine import ResearchObservatoryEngine
from jarvis.research_observatory.models import (
    ANALYZING,
    ARCHIVED,
    COLLECTING,
    CREATED,
    REPORTING,
    IllegalTransition,
    ImmutableSnapshotError,
    UnknownSnapshot,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_observatory.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchObservatoryEngine()


def _seed(sp, filename, rows):
    with open(sp(filename), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _seed_sources(sp):
    """대표 상위 레이어 소스 시드(READ ONLY 입력)."""
    _seed(sp, "rg_strategies.jsonl", [{"strategy_id": "ST1", "created_at": "2026-07-01T00:00:00Z"},
                                      {"strategy_id": "ST2", "created_at": "2026-07-02T00:00:00Z"}])
    _seed(sp, "ai_signals.jsonl", [{"signal_id": "SG1", "created_at": "2026-07-01T00:00:00Z"}])
    _seed(sp, "ai_features.jsonl", [{"feature_id": "FT1"}, {"feature_id": "FT2"}])
    _seed(sp, "dg_datasets.jsonl", [{"dataset_id": "DS1"}])
    _seed(sp, "rg_experiments.jsonl", [{"experiment_id": "EX1", "created_at": "2026-07-03T00:00:00Z"}])
    _seed(sp, "pr_portfolios.jsonl", [{"portfolio_id": "PF1", "created_at": "2026-07-04T00:00:00Z"}])
    _seed(sp, "rv_validations.jsonl", [
        {"event_id": "E1", "validation_id": "V1", "created_at": "2026-07-05T00:00:00Z"},
        {"event_id": "E2", "validation_id": "V1", "created_at": "2026-07-05T00:01:00Z"}])
    _seed(sp, "di_decision_sessions.jsonl", [{"event_id": "D1", "session_id": "S1"}])
    _seed(sp, "sim_runs.jsonl", [{"event_id": "R1", "run_id": "RUN1", "created_at": "2026-07-06T00:00:00Z"}])
    _seed(sp, "kg_entities.jsonl", [{"event_id": "K1", "entity_id": "KGE1"},
                                    {"event_id": "K2", "entity_id": "KGE2"},
                                    {"event_id": "K3", "entity_id": "KGE3"}])
    _seed(sp, "kg_relationships.jsonl", [{"relationship_id": "R1"}, {"relationship_id": "R2"}])
    _seed(sp, "rv_replay_reports.jsonl", [{"replay_id": "RP1", "result": "REPRODUCIBLE"},
                                          {"replay_id": "RP2", "result": "NON_REPRODUCIBLE"},
                                          {"replay_id": "RP3", "result": "REPRODUCIBLE"}])
    _seed(sp, "rv_scores.jsonl", [{"score_id": "SC1", "grade": "A", "overall_score": 0.9},
                                  {"score_id": "SC2", "grade": "C", "overall_score": 0.55}])
    _seed(sp, "arg_agents.jsonl", [{"event_id": "AG1", "agent_id": "A1"}])


def _snap(eng, name="obs1", commit=True):
    return eng.create_snapshot(name, "2026Q3", T0, commit=commit)


# ── Snapshot lifecycle ──
def test_create_snapshot(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _snap(eng)
    assert s.status == CREATED and s.name == "obs1"
    assert eng.snapshot_state(s.snapshot_id) == CREATED


def test_snapshot_id_deterministic():
    a = M.snapshot_id("n", "e")
    assert a == M.snapshot_id("n", "e") and a.startswith("OBS:")


def test_snapshot_commit_persists(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _snap(_eng(), commit=True)
    assert len(ledger.read_snapshot_events()) == 1


def test_snapshot_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _snap(_eng(), commit=False)
    assert ledger.read_snapshot_events() == []


def test_snapshot_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _snap(eng)
    _snap(eng)
    assert len(ledger.distinct_snapshots()) == 1


def test_snapshot_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _snap(eng)
    sid = s.snapshot_id
    eng.transition_snapshot(sid, COLLECTING, T1, commit=True)
    eng.transition_snapshot(sid, ANALYZING, T1, commit=True)
    eng.transition_snapshot(sid, REPORTING, T2, commit=True)
    eng.transition_snapshot(sid, ARCHIVED, T2, commit=True)
    assert eng.snapshot_state(sid) == ARCHIVED


def test_snapshot_invalid_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _snap(eng)
    with pytest.raises(IllegalTransition):
        eng.transition_snapshot(s.snapshot_id, ANALYZING, T1, commit=True)  # CREATED→ANALYZING 차단


def test_snapshot_archived_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _snap(eng)
    for to in (COLLECTING, ANALYZING, REPORTING, ARCHIVED):
        eng.transition_snapshot(s.snapshot_id, to, T1, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition_snapshot(s.snapshot_id, CREATED, T2, commit=True)


def test_snapshot_transition_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownSnapshot):
        _eng().transition_snapshot("GHOST", COLLECTING, T1, commit=True)


def test_snapshot_transition_table():
    assert M.can_transition("", CREATED)
    assert M.can_transition(CREATED, COLLECTING)
    assert M.can_transition(COLLECTING, ANALYZING)
    assert M.can_transition(ANALYZING, REPORTING)
    assert M.can_transition(REPORTING, ARCHIVED)
    assert not M.can_transition(CREATED, ANALYZING)
    assert not M.can_transition(ARCHIVED, CREATED)


def test_snapshot_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_snapshot("s", "e1", T0, commit=True)
    # 동일 name+epoch → 같은 id, idempotent (내용 동일). 다른 epoch → 다른 스냅샷.
    s2 = eng.create_snapshot("s", "e2", T0, commit=True)
    assert s2.snapshot_id != M.snapshot_id("s", "e1")


def test_archive_helper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _snap(eng)
    for to in (COLLECTING, ANALYZING, REPORTING):
        eng.transition_snapshot(s.snapshot_id, to, T1, commit=True)
    eng.archive(s.snapshot_id, T2, commit=True)
    assert eng.snapshot_state(s.snapshot_id) == ARCHIVED


def test_snapshot_artifact_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _snap(eng)
    assert any(a["artifact_type"] == M.ART_SNAPSHOT and a["ref_id"] == s.snapshot_id
               for a in ledger.read_artifacts())


# ── Cross-layer collection ──
def test_collect_metrics(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    ms = eng.collect(s.snapshot_id, T1, commit=True)
    assert len(ms) > 0
    mv = ledger.metric_value(s.snapshot_id, "STRATEGY", "count")
    assert mv == 2


def test_collect_advances_to_collecting(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    eng.collect(s.snapshot_id, T1, commit=True)
    assert eng.snapshot_state(s.snapshot_id) == COLLECTING


def test_collect_signal_count(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    eng.collect(s.snapshot_id, T1, commit=True)
    assert ledger.metric_value(s.snapshot_id, "SIGNAL", "count") == 1


def test_collect_validation_distinct(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)  # V1 has 2 events → distinct 1
    eng = _eng()
    s = _snap(eng)
    eng.collect(s.snapshot_id, T1, commit=True)
    assert ledger.metric_value(s.snapshot_id, "VALIDATION", "count") == 1


def test_collect_kg_metrics(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    eng.collect(s.snapshot_id, T1, commit=True)
    assert ledger.metric_value(s.snapshot_id, "KNOWLEDGE_GRAPH", "entities") == 3
    assert ledger.metric_value(s.snapshot_id, "KNOWLEDGE_GRAPH", "connections") == 2


def test_collect_replay_rate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)  # 2 REPRODUCIBLE / 3 total
    eng = _eng()
    s = _snap(eng)
    eng.collect(s.snapshot_id, T1, commit=True)
    assert abs(ledger.metric_value(s.snapshot_id, "REPLAY", "success_rate") - 2 / 3) < 1e-6


def test_collect_empty_sources(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _snap(eng)
    eng.collect(s.snapshot_id, T1, commit=True)
    assert ledger.metric_value(s.snapshot_id, "STRATEGY", "count") == 0


def test_collect_unknown_snapshot(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownSnapshot):
        _eng().collect("GHOST", T1, commit=True)


def test_collect_idempotent(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    eng.collect(s.snapshot_id, T1, commit=True)
    n1 = len(ledger.read_metrics())
    eng.collect(s.snapshot_id, T1, commit=True)
    assert len(ledger.read_metrics()) == n1


def test_collect_does_not_mutate_sources(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    before = hashlib.sha256(open(sp("rg_strategies.jsonl"), "rb").read()).hexdigest()
    eng = _eng()
    s = _snap(eng)
    eng.collect(s.snapshot_id, T1, commit=True)
    after = hashlib.sha256(open(sp("rg_strategies.jsonl"), "rb").read()).hexdigest()
    assert before == after


# ── Dependency graph ──
def test_dependency_map(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    ds = eng.dependency_map(s.snapshot_id, T1, commit=True)
    assert len(ds) == len(M.DEPENDENCY_FLOW)
    assert len(ledger.read_dependencies()) == len(M.DEPENDENCY_FLOW)


def test_dependency_counts(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    ds = eng.dependency_map(s.snapshot_id, T1, commit=True)
    edge = next(d for d in ds if d.from_layer == "SIGNAL" and d.to_layer == "STRATEGY")
    assert edge.from_count == 1 and edge.to_count == 2


def test_dependency_broken_detection(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # STRATEGY exists but no SIGNAL → SIGNAL->STRATEGY broken (to>0, from==0)
    _seed(sp, "rg_strategies.jsonl", [{"strategy_id": "ST1"}])
    eng = _eng()
    s = _snap(eng)
    ds = eng.dependency_map(s.snapshot_id, T1, commit=True)
    broken = [d for d in ds if d.broken]
    assert any(d.to_layer == "STRATEGY" for d in broken)


def test_dependency_no_broken_when_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _snap(eng)
    ds = eng.dependency_map(s.snapshot_id, T1, commit=True)
    assert not any(d.broken for d in ds)  # 모두 0 → broken 아님


def test_dependency_flow_acyclic(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    eng.dependency_map(s.snapshot_id, T1, commit=True)
    assert eng.dependency_cycle(s.snapshot_id) == []


def test_dependency_idempotent(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    eng.dependency_map(s.snapshot_id, T1, commit=True)
    eng.dependency_map(s.snapshot_id, T1, commit=True)
    assert len(ledger.read_dependencies()) == len(M.DEPENDENCY_FLOW)


def test_dependency_unknown_snapshot(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownSnapshot):
        _eng().dependency_map("GHOST", T1, commit=True)


def test_detect_cycle_helper():
    assert M.detect_cycle([("a", "b"), ("b", "a")]) == ["a", "b", "a"]
    assert M.detect_cycle([("a", "b"), ("b", "c")]) == []


# ── Timeline ──
def test_build_timeline(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    ts = eng.build_timeline(s.snapshot_id, T1, commit=True)
    assert len(ts) > 0
    assert len(ledger.read_timelines()) == len(ts)


def test_timeline_sorted_by_timestamp(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    ts = eng.build_timeline(s.snapshot_id, T1, commit=True)
    stamps = [t.timestamp for t in ts]
    assert stamps == sorted(stamps)


def test_timeline_event_types(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    ts = eng.build_timeline(s.snapshot_id, T1, commit=True)
    types = {t.event_type for t in ts}
    assert "STRATEGY_CREATED" in types and "SIMULATION_FINISHED" in types


def test_timeline_idempotent(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    eng.build_timeline(s.snapshot_id, T1, commit=True)
    n1 = len(ledger.read_timelines())
    eng.build_timeline(s.snapshot_id, T1, commit=True)
    assert len(ledger.read_timelines()) == n1


def test_timeline_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _snap(eng)
    ts = eng.build_timeline(s.snapshot_id, T1, commit=True)
    assert ts == []


def test_timeline_unknown_snapshot(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownSnapshot):
        _eng().build_timeline("GHOST", T1, commit=True)


# ── Trend analytics ──
def test_trend_analysis(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    ts = eng.trend_analysis(s.snapshot_id, T1, commit=True)
    names = {t.name for t in ts}
    assert "replay_success_rate" in names and "knowledge_graph_density" in names


def test_trend_advances_to_analyzing(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    eng.trend_analysis(s.snapshot_id, T1, commit=True)
    assert eng.snapshot_state(s.snapshot_id) == ANALYZING


def test_trend_replay_rate_value(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    ts = eng.trend_analysis(s.snapshot_id, T1, commit=True)
    rr = next(t for t in ts if t.name == "replay_success_rate")
    assert abs(rr.value - 2 / 3) < 1e-6


def test_trend_baseline_direction(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    ts = eng.trend_analysis(s.snapshot_id, T1, commit=True)
    assert all(t.direction == M.TREND_BASELINE for t in ts)  # 첫 스냅샷 → baseline


def test_trend_direction_up_across_snapshots(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "rg_experiments.jsonl", [{"experiment_id": "EX1"}])
    eng = _eng()
    s1 = eng.create_snapshot("t1", "e1", T0, commit=True)
    eng.trend_analysis(s1.snapshot_id, T0, commit=True)
    # 실험 증가 후 두 번째 스냅샷
    _seed(sp, "rg_experiments.jsonl", [{"experiment_id": "EX1"}, {"experiment_id": "EX2"}])
    s2 = eng.create_snapshot("t2", "e2", T1, commit=True)
    ts = eng.trend_analysis(s2.snapshot_id, T1, commit=True)
    growth = next(t for t in ts if t.name == "experiment_growth")
    assert growth.direction == M.TREND_UP and growth.value == 2.0


def test_trend_kg_density(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)  # 3 entities, 2 relations
    eng = _eng()
    s = _snap(eng)
    ts = eng.trend_analysis(s.snapshot_id, T1, commit=True)
    dens = next(t for t in ts if t.name == "knowledge_graph_density")
    assert abs(dens.value - M.graph_density(3, 2)) < 1e-9


def test_trend_idempotent(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    eng.trend_analysis(s.snapshot_id, T1, commit=True)
    n1 = len(ledger.read_trends())
    eng.trend_analysis(s.snapshot_id, T1, commit=True)
    assert len(ledger.read_trends()) == n1


def test_trend_unknown_snapshot(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownSnapshot):
        _eng().trend_analysis("GHOST", T1, commit=True)


def test_trend_direction_helper():
    assert M.trend_direction(2.0, None) == M.TREND_BASELINE
    assert M.trend_direction(2.0, 1.0) == M.TREND_UP
    assert M.trend_direction(1.0, 2.0) == M.TREND_DOWN
    assert M.trend_direction(1.0, 1.0) == M.TREND_FLAT


# ── Dashboard ──
def test_dashboard_metrics(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    d = eng.dashboard(s.snapshot_id, T1, commit=True)
    assert d.metrics["total_strategies"] == 2
    assert d.metrics["total_signals"] == 1
    assert d.metrics["total_validations"] == 1
    assert abs(d.metrics["replay_success"] - 2 / 3) < 1e-6


def test_dashboard_score_distribution(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    d = eng.dashboard(s.snapshot_id, T1, commit=True)
    assert d.metrics["validation_score_distribution"] == {"A": 1, "C": 1}


def test_dashboard_lineage_integrity(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    d = eng.dashboard(s.snapshot_id, T1, commit=True)
    assert 0.0 <= d.metrics["lineage_integrity"] <= 1.0


def test_dashboard_persisted(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    eng.dashboard(s.snapshot_id, T1, commit=True)
    assert len(ledger.read_dashboards()) == 1


def test_dashboard_observation_only(tmp_path, monkeypatch):
    """대시보드에 승인/배포/실행 필드가 없어야 한다 — 관찰 정보만."""
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    d = eng.dashboard(s.snapshot_id, T1, commit=True)
    for banned in ("approved", "deployed", "executed", "selected"):
        assert banned not in d.metrics


def test_dashboard_idempotent(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    eng.dashboard(s.snapshot_id, T1, commit=True)
    eng.dashboard(s.snapshot_id, T1, commit=True)
    assert len(ledger.read_dashboards()) == 1


# ── Report ──
def test_generate_report(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    eng.collect(s.snapshot_id, T1, commit=True)
    eng.dependency_map(s.snapshot_id, T1, commit=True)
    eng.build_timeline(s.snapshot_id, T1, commit=True)
    eng.trend_analysis(s.snapshot_id, T1, commit=True)
    rep = eng.generate_report(s.snapshot_id, T2, commit=True)
    assert rep.metric_count > 0 and rep.dependency_count == len(M.DEPENDENCY_FLOW)
    assert rep.timeline_count > 0 and rep.trend_count > 0
    assert "OBSERVED" in rep.disclaimer


def test_report_advances_to_reporting(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    eng.generate_report(s.snapshot_id, T2, commit=True)
    assert eng.snapshot_state(s.snapshot_id) == REPORTING


def test_report_dashboard_metrics_included(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    rep = eng.generate_report(s.snapshot_id, T2, commit=True)
    assert rep.dashboard_metrics["total_strategies"] == 2


def test_report_idempotent(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    eng.generate_report(s.snapshot_id, T2, commit=True)
    eng.generate_report(s.snapshot_id, T2, commit=True)
    assert len(ledger.read_reports()) == 1


def test_report_unknown_snapshot(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownSnapshot):
        _eng().generate_report("GHOST", T2, commit=True)


# ── Summary ──
def test_summary(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    eng.collect(s.snapshot_id, T1, commit=True)
    eng.dependency_map(s.snapshot_id, T1, commit=True)
    rep = eng.summary(T2)
    assert rep.snapshot_count == 1 and rep.metric_count > 0
    assert rep.dependency_count == len(M.DEPENDENCY_FLOW)


def test_summary_deterministic(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    eng.collect(s.snapshot_id, T1, commit=True)
    assert eng.summary(T2).to_dict() == eng.summary(T2).to_dict()


def test_summary_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    rep = _eng().summary(T0)
    assert rep.snapshot_count == 0 and rep.metric_count == 0


# ── helpers ──
def test_ratio_helper():
    assert M.ratio(2, 4) == 0.5
    assert M.ratio(1, 0) == 0.0


def test_graph_density_helper():
    assert M.graph_density(3, 2) == round(2 / 6, 8)
    assert M.graph_density(1, 0) == 0.0
    assert M.graph_density(0, 5) == 0.0


# ── verify ──
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_observatory.verify import verify_chain
    assert verify_chain()["ok"] is True


def _full(eng):
    s = _snap(eng)
    eng.collect(s.snapshot_id, T1, commit=True)
    eng.dependency_map(s.snapshot_id, T1, commit=True)
    eng.build_timeline(s.snapshot_id, T1, commit=True)
    eng.trend_analysis(s.snapshot_id, T1, commit=True)
    eng.generate_report(s.snapshot_id, T2, commit=True)
    return s


def test_verify_full_ok(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    from jarvis.research_observatory.verify import verify_chain
    eng = _eng()
    _full(eng)
    res = verify_chain()
    assert res["ok"] is True
    assert res["dependency"]["ok"] and res["timeline"]["ok"] and res["artifact"]["ok"]


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_observatory.verify import verify_chain
    eng = _eng()
    _snap(eng)
    recs = ledger.read_snapshot_events()
    recs[0]["name"] = "TAMPERED"
    with open(sp("ob_snapshots.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_chain_break(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_observatory.verify import verify_ledger
    eng = _eng()
    eng.create_snapshot("a", "1", T0, commit=True)
    eng.create_snapshot("b", "2", T0, commit=True)
    recs = ledger.read_snapshot_events()
    recs[1]["previous_hash"] = "GENESIS"
    with open(sp("ob_snapshots.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_ledger(ledger.SNAPSHOTS)["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_observatory.verify import verify_ledger
    eng = _eng()
    _snap(eng)
    recs = ledger.read_snapshot_events()
    dup = dict(recs[0])
    dup["previous_hash"] = recs[0]["record_hash"]
    with open(sp("ob_snapshots.jsonl"), "a") as f:
        f.write(json.dumps(dup) + "\n")
    assert verify_ledger(ledger.SNAPSHOTS)["ok"] is False


def test_verify_dependency_dangling(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_observatory.verify import dependency_integrity
    rec = {"dependency_id": "OBD:x", "snapshot_id": "OBS:ghost", "from_layer": "A",
           "to_layer": "B", "from_count": 1, "to_count": 1, "broken": False, "created_at": T0,
           "previous_hash": "GENESIS"}
    rec["record_hash"] = M.content_hash(rec)
    with open(sp("ob_dependencies.jsonl"), "w") as f:
        f.write(json.dumps(rec) + "\n")
    res = dependency_integrity()
    assert res["ok"] is False
    assert any("dangling_dependency" in i for i in res["issues"])


def test_verify_dependency_cycle(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_observatory.verify import dependency_integrity
    eng = _eng()
    s = _snap(eng)
    sid = s.snapshot_id
    for frm, to in (("A", "B"), ("B", "A")):
        rec = {"dependency_id": M.dependency_id(sid, frm, to), "snapshot_id": sid,
               "from_layer": frm, "to_layer": to, "from_count": 1, "to_count": 1,
               "broken": False, "created_at": T0, "previous_hash": "GENESIS"}
        # 체인 무시하고 무결성만 검사(직접 주입)
        rec["record_hash"] = M.content_hash(rec)
        ledger.append_dependency(rec)
    assert any("dependency_cycle" in i for i in dependency_integrity()["issues"])


def test_verify_timeline_dangling(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_observatory.verify import timeline_integrity
    rec = {"timeline_id": "OBT:x", "snapshot_id": "OBS:ghost", "layer": "STRATEGY",
           "event_type": "STRATEGY_CREATED", "reference": "ST1", "timestamp": T0,
           "created_at": T0, "previous_hash": "GENESIS"}
    rec["record_hash"] = M.content_hash(rec)
    with open(sp("ob_timelines.jsonl"), "w") as f:
        f.write(json.dumps(rec) + "\n")
    res = timeline_integrity()
    assert any("dangling_timeline" in i for i in res["issues"])


def test_verify_artifact_dangling_parent(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_observatory.verify import artifact_integrity
    rec = {"artifact_id": "A1", "artifact_type": "X", "ref_id": "r", "parent_artifact": "GHOST",
           "snapshot_id": "", "created_at": T0, "previous_hash": "GENESIS"}
    rec["record_hash"] = M.content_hash(rec)
    with open(sp("ob_artifacts.jsonl"), "w") as f:
        f.write(json.dumps(rec) + "\n")
    res = artifact_integrity()
    assert any("dangling_parent" in i for i in res["issues"])


def test_verify_artifact_cycle(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_observatory.verify import artifact_integrity
    a1 = {"artifact_id": "A1", "artifact_type": "X", "ref_id": "r", "parent_artifact": "A2",
          "snapshot_id": "", "created_at": T0, "previous_hash": "GENESIS"}
    a1["record_hash"] = M.content_hash(a1)
    a2 = {"artifact_id": "A2", "artifact_type": "X", "ref_id": "r", "parent_artifact": "A1",
          "snapshot_id": "", "created_at": T0, "previous_hash": a1["record_hash"]}
    a2["record_hash"] = M.content_hash(a2)
    with open(sp("ob_artifacts.jsonl"), "w") as f:
        f.write(json.dumps(a1) + "\n")
        f.write(json.dumps(a2) + "\n")
    assert any("cycle" in i for i in artifact_integrity()["issues"])


# ── replay ──
def test_replay_deterministic(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    from jarvis.research_observatory.verify import replay
    eng = _eng()
    _full(eng)
    assert replay(eng, T2)["deterministic"] is True


def test_content_hash_excludes_chain_fields():
    a = {"x": 1, "previous_hash": "A", "record_hash": "B", "report_hash": "C"}
    b = {"x": 1, "previous_hash": "Z", "record_hash": "Z", "report_hash": "Z"}
    assert M.content_hash(a) == M.content_hash(b)


# ── CLI ──
def test_cli_snapshot_and_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_observatory.__main__ import main
    rc = main(["snapshot", "--name", "obs1", "--epoch", "2026Q3", "--commit"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["snapshot"]["name"] == "obs1"
    main(["summary"])
    assert json.loads(capsys.readouterr().out)["snapshot_count"] == 1


def test_cli_full_workflow(tmp_path, monkeypatch, capsys):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    from jarvis.research_observatory.__main__ import main
    main(["snapshot", "--name", "obs1", "--commit"])
    sid = json.loads(capsys.readouterr().out)["snapshot"]["snapshot_id"]
    main(["collect", "--snapshot-id", sid, "--commit"])
    capsys.readouterr()
    main(["dependency", "--snapshot-id", sid, "--commit"])
    dep = json.loads(capsys.readouterr().out)
    assert dep["cycle"] == []
    main(["timeline", "--snapshot-id", sid, "--commit"])
    capsys.readouterr()
    main(["trend", "--snapshot-id", sid, "--commit"])
    capsys.readouterr()
    main(["dashboard", "--snapshot-id", sid, "--commit"])
    dash = json.loads(capsys.readouterr().out)["dashboard"]
    assert dash["metrics"]["total_strategies"] == 2
    main(["report", "--snapshot-id", sid, "--commit"])
    capsys.readouterr()
    rc = main(["verify"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_verify_empty_zero(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_observatory.__main__ import main
    assert main(["verify"]) == 0
    capsys.readouterr()


# ── 보안·불변·READ ONLY 가드 ──
def test_no_forbidden_imports():
    import jarvis.research_observatory.engine as eng_mod
    import jarvis.research_observatory.models as mdl_mod
    import jarvis.research_observatory.ledger as led_mod
    import jarvis.research_observatory.verify as ver_mod
    src = ""
    for m in (eng_mod, mdl_mod, led_mod, ver_mod):
        with open(m.__file__) as f:
            src += f.read()
    _j = "jarvis."
    forbidden = [_j + "live_execution", _j + "broker", _j + "order",
                 _j + "portfolio.", _j + "risk_governor", _j + "permission",
                 "place_order(", "submit_order(", "execute_trade(", "deploy_strategy(",
                 "allocate_capital(", "promote_model(", "activate_live("]
    for token in forbidden:
        assert token not in src, f"forbidden reference: {token}"


def test_no_execution_authority_api():
    api = set(dir(ResearchObservatoryEngine))
    for banned in ("execute", "trade", "place_order", "allocate", "deploy", "promote",
                   "activate_live", "approve", "select_strategy", "submit_order",
                   "change_permission", "set_autonomy"):
        assert banned not in api


def test_observed_not_approved(tmp_path, monkeypatch):
    """관측 REPORTING 이어도 승인/배포/실행 권한은 전혀 없다."""
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _full(eng)
    assert eng.snapshot_state(s.snapshot_id) == REPORTING
    assert not hasattr(eng, "approve")
    assert not hasattr(eng, "deploy")


def test_live_execution_disabled_invariant():
    import jarvis.config as _cfg
    assert _cfg.live_execution_enabled() is False
    assert _cfg.AUTONOMY_LEVEL < _cfg.MIN_LIVE_LEVEL


def test_autonomy_unchanged_after_observation(tmp_path, monkeypatch):
    import jarvis.config as _cfg
    before = _cfg.AUTONOMY_LEVEL
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    _full(_eng())
    assert _cfg.AUTONOMY_LEVEL == before
    assert _cfg.live_execution_enabled() is False


def test_no_delete_or_update_api():
    import importlib
    for mod_name in ("engine", "ledger"):
        m = importlib.import_module(f"jarvis.research_observatory.{mod_name}")
        for attr in dir(m):
            low = attr.lower()
            assert not low.startswith("delete_")
            assert not low.startswith("update_")
            assert not low.startswith("remove_")


def test_ledgers_namespaced_ob_prefix():
    for filename, _ in ledger.ALL_LEDGERS:
        assert filename.startswith("ob_")


def test_no_collision_with_existing_prefixes():
    ours = {fn for fn, _ in ledger.ALL_LEDGERS}
    known = {"rg_strategies.jsonl", "ai_signals.jsonl", "pr_portfolios.jsonl",
             "kg_entities.jsonl", "arg_agents.jsonl", "di_candidates.jsonl",
             "sim_scenarios.jsonl", "rv_validations.jsonl"}
    assert ours.isdisjoint(known)
    assert all(fn.startswith("ob_") for fn in ours)


def test_source_ledgers_read_only_not_owned():
    owned = {fn for fn, _ in ledger.ALL_LEDGERS}
    for layer, spec in ledger.SOURCE_LEDGERS.items():
        assert spec[0] not in owned


def test_existing_source_ledgers_untouched(tmp_path, monkeypatch):
    """상위 P10.2~P10.9 원장을 시드한 뒤 전체 관측 워크플로를 돌려도 원본 SHA256 불변."""
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    source_files = ["rg_strategies.jsonl", "ai_signals.jsonl", "pr_portfolios.jsonl",
                    "kg_entities.jsonl", "kg_relationships.jsonl", "rv_validations.jsonl",
                    "sim_runs.jsonl", "rv_replay_reports.jsonl", "rv_scores.jsonl"]
    hashes = {f: hashlib.sha256(open(sp(f), "rb").read()).hexdigest() for f in source_files}
    eng = _eng()
    _full(eng)
    for f, h in hashes.items():
        assert hashlib.sha256(open(sp(f), "rb").read()).hexdigest() == h


def test_engine_only_appends_ob_files(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    _full(eng)
    created = [f for f in os.listdir(tmp_path)
               if f.endswith(".jsonl") and not any(
                   f.startswith(p) for p in ("rg_", "ai_", "pr_", "kg_", "rv_", "sim_",
                                             "di_", "arg_", "dg_"))]
    assert created and all(f.startswith("ob_") for f in created)


def test_observed_layers_defined():
    assert "STRATEGY" in M.OBSERVED_LAYERS and "SIMULATION" in M.OBSERVED_LAYERS


def test_dependency_flow_covers_full_chain():
    froms = {a for a, b in M.DEPENDENCY_FLOW}
    tos = {b for a, b in M.DEPENDENCY_FLOW}
    assert "DATASET" in froms and "SIMULATION" in tos


# ── 추가: ID prefix / 세부 지표 ──
def test_snapshot_id_varies_by_epoch():
    assert M.snapshot_id("n", "e1") != M.snapshot_id("n", "e2")


def test_metric_id_prefix():
    assert M.metric_id("OBS:x", "STRATEGY", "count").startswith("OBM:")


def test_dependency_id_prefix():
    assert M.dependency_id("OBS:x", "A", "B").startswith("OBD:")


def test_timeline_id_prefix():
    assert M.timeline_id("OBS:x", "L", "E", "r").startswith("OBT:")


def test_trend_id_prefix():
    assert M.trend_id("OBS:x", "n").startswith("OBR:")


def test_dashboard_id_prefix():
    assert M.dashboard_id("OBS:x").startswith("OBH:")


def test_report_id_prefix():
    assert M.report_id("OBS:x").startswith("OBP:")


def test_artifact_id_prefix():
    assert M.artifact_id(M.ART_SNAPSHOT, "x").startswith("OBA:")


def test_collect_experiment_count(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    eng.collect(s.snapshot_id, T1, commit=True)
    assert ledger.metric_value(s.snapshot_id, "EXPERIMENT", "count") == 1


def test_collect_dataset_feature_counts(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    eng.collect(s.snapshot_id, T1, commit=True)
    assert ledger.metric_value(s.snapshot_id, "DATASET", "count") == 1
    assert ledger.metric_value(s.snapshot_id, "FEATURE", "count") == 2


def test_dashboard_total_experiments_simulations(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    d = eng.dashboard(s.snapshot_id, T1, commit=True)
    assert d.metrics["total_experiments"] == 1 and d.metrics["total_simulations"] == 1


def test_trend_dataset_and_feature_reuse(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)  # datasets=1 features=2 signals=1
    eng = _eng()
    s = _snap(eng)
    ts = eng.trend_analysis(s.snapshot_id, T1, commit=True)
    dr = next(t for t in ts if t.name == "dataset_reuse")
    fr = next(t for t in ts if t.name == "feature_reuse")
    assert dr.value == 2.0 and fr.value == 0.5


def test_report_broken_dependency_count(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "rg_strategies.jsonl", [{"strategy_id": "ST1"}])  # SIGNAL->STRATEGY broken
    eng = _eng()
    s = _snap(eng)
    eng.dependency_map(s.snapshot_id, T1, commit=True)
    rep = eng.generate_report(s.snapshot_id, T2, commit=True)
    assert rep.broken_dependency_count >= 1


def test_dependency_edge_specific_datacounts(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    eng = _eng()
    s = _snap(eng)
    ds = eng.dependency_map(s.snapshot_id, T1, commit=True)
    ds_ft = next(d for d in ds if d.from_layer == "DATASET" and d.to_layer == "FEATURE")
    assert ds_ft.from_count == 1 and ds_ft.to_count == 2 and ds_ft.broken is False


def test_metrics_hash_stable():
    assert M.metrics_hash({"a": 1, "b": 2}) == M.metrics_hash({"b": 2, "a": 1})


def test_full_workflow_artifact_lineage_intact(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_sources(sp)
    from jarvis.research_observatory.verify import artifact_integrity
    eng = _eng()
    _full(eng)
    res = artifact_integrity()
    assert res["ok"] is True and not res["issues"]
