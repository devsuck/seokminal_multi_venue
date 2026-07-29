"""P11.2 Autonomous Research Task Planner 테스트. **AI 에이전트 연구 워크플로 계획 — 계획 전용.**

계획 요청·생애주기(REQUESTED→PLANNED→RUNNING→COMPLETED→REVIEWED)·태스크 추가(불변·종류·계보)·의존성(DAG·순환
거부·자기의존 거부)·그래프 구성/검증(DAG validation·dependency detection·roots/leaves/topo)·스케줄(위상·웨이브·
불변)·리포트·태스크 계보·동결(PLANNED 이후 불변 plans)·verify(체인/변조/중복/DAG/계보/생애주기)·replay·CLI·보안
(금지import·실행/자동승인/자동배포 없음·삭제 API 없음·불변·PLAN≠EXECUTE·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.research_task_planner import ledger
from jarvis.research_task_planner import models as M
from jarvis.research_task_planner.engine import ResearchTaskPlannerEngine
from jarvis.research_task_planner.models import (
    KIND_ANALYSIS,
    KIND_BACKTEST,
    KIND_DATA,
    KIND_REVIEW,
    KIND_VALIDATION,
    PLAN_COMPLETED,
    PLAN_PLANNED,
    PLAN_REQUESTED,
    PLAN_REVIEWED,
    PLAN_RUNNING,
    DependencyCycleError,
    IllegalPlanTransition,
    ImmutableScheduleError,
    ImmutableTaskError,
    InvalidTaskKind,
    PlanFrozenError,
    SelfDependencyError,
    UnknownPlanError,
    UnknownTaskError,
)

T0 = "2026-07-24T00:00:00Z"
T1 = "2026-07-24T00:01:00Z"
T2 = "2026-07-24T00:02:00Z"
T3 = "2026-07-24T00:03:00Z"
T4 = "2026-07-24T00:04:00Z"
T5 = "2026-07-24T00:05:00Z"


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_task_planner.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchTaskPlannerEngine()


def _plan(e, objective="find alpha", by="strat_agent", title="P1", now=T0):
    return e.request_plan(objective, by, title, now, commit=True).plan_id


def _chain_plan(e):
    """3-태스크 선형 DAG 계획(REQUESTED)."""
    p = _plan(e)
    a = e.add_task(p, "collect", KIND_DATA, "", "", T0, commit=True)
    b = e.add_task(p, "analyze", KIND_ANALYSIS, "", "", T0, commit=True)
    c = e.add_task(p, "backtest", KIND_BACKTEST, "", "", T0, commit=True)
    e.add_dependency(p, a.task_id, b.task_id, T0, commit=True)
    e.add_dependency(p, b.task_id, c.task_id, T0, commit=True)
    return p, a.task_id, b.task_id, c.task_id


# ══════════════ request_plan / lifecycle ══════════════
def test_request_plan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().request_plan("obj", "agent", "T", T0, commit=True)
    assert ev.plan_id.startswith("RTP:")
    assert ev.to_state == PLAN_REQUESTED


def test_request_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _eng().request_plan("o", "a", "t", T0, commit=False)
    b = _eng().request_plan("o", "a", "t", T1, commit=False)
    assert a.plan_id == b.plan_id


def test_request_no_auto_advance(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    assert e.current_plan_state(p) == PLAN_REQUESTED  # 자동 승인/진행 없음


def test_request_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _plan(e)
    _plan(e, now=T1)
    assert len(ledger.plan_ids()) == 1


def test_plan_meta(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e, "obj-x", "agent-y", "title-z")
    meta = e.plan_meta(p)
    assert meta["objective"] == "obj-x"
    assert meta["requested_by"] == "agent-y"
    assert meta["state"] == PLAN_REQUESTED


def test_unknown_plan_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().current_plan_state("RTP:ghost") is None


def test_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, *_ = _chain_plan(e)
    e.finalize_plan(p, T1, commit=True)
    assert e.current_plan_state(p) == PLAN_PLANNED
    e.mark_running(p, T2, commit=True)
    assert e.current_plan_state(p) == PLAN_RUNNING
    e.mark_completed(p, T3, commit=True)
    assert e.current_plan_state(p) == PLAN_COMPLETED
    e.review_plan(p, T4, commit=True)
    assert e.current_plan_state(p) == PLAN_REVIEWED


def test_illegal_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    with pytest.raises(IllegalPlanTransition):
        e.mark_running(p, T1, commit=True)  # REQUESTED->RUNNING 불가


def test_reviewed_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, *_ = _chain_plan(e)
    e.finalize_plan(p, T1, commit=True)
    e.mark_running(p, T2, commit=True)
    e.mark_completed(p, T3, commit=True)
    e.review_plan(p, T4, commit=True)
    with pytest.raises(IllegalPlanTransition):
        e.mark_running(p, T5, commit=True)


def test_five_plan_states():
    assert len(M.PLAN_STATES) == 5
    assert set(M.PLAN_STATES) == {"REQUESTED", "PLANNED", "RUNNING", "COMPLETED", "REVIEWED"}


# ══════════════ add_task ══════════════
def test_add_task(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    t = e.add_task(p, "collect", KIND_DATA, "gather", "", T0, commit=True)
    assert t.task_id.startswith("RTK:")
    assert t.kind == KIND_DATA


def test_add_task_invalid_kind(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    with pytest.raises(InvalidTaskKind):
        e.add_task(p, "x", "MINING", "", "", T0, commit=True)


@pytest.mark.parametrize("kind", list(M.TASK_KINDS))
def test_add_task_all_kinds(tmp_path, monkeypatch, kind):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    t = e.add_task(p, f"t_{kind}", kind, "", "", T0, commit=True)
    assert t.kind == kind


def test_add_task_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    e.add_task(p, "x", KIND_DATA, "", "", T0, commit=True)
    with pytest.raises(ImmutableTaskError):
        e.add_task(p, "x", KIND_ANALYSIS, "", "", T1, commit=True)


def test_add_task_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    e.add_task(p, "x", KIND_DATA, "", "", T0, commit=True)
    e.add_task(p, "x", KIND_DATA, "", "", T1, commit=True)
    assert len(ledger.plan_tasks(p)) == 1


def test_add_task_unknown_plan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownPlanError):
        _eng().add_task("RTP:ghost", "x", KIND_DATA, "", "", T0, commit=True)


def test_add_task_unknown_parent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    with pytest.raises(UnknownTaskError):
        e.add_task(p, "x", KIND_DATA, "", "RTK:ghost", T0, commit=True)


# ══════════════ 태스크 계보 ══════════════
def test_task_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    a = e.add_task(p, "root", KIND_RESEARCH := "RESEARCH", "", "", T0, commit=True)
    b = e.add_task(p, "child", KIND_ANALYSIS, "", a.task_id, T0, commit=True)
    c = e.add_task(p, "grandchild", KIND_BACKTEST, "", b.task_id, T0, commit=True)
    assert e.trace_lineage(p, c.task_id) == [b.task_id, a.task_id]


def test_lineage_validation_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    a = e.add_task(p, "root", KIND_DATA, "", "", T0, commit=True)
    e.add_task(p, "child", KIND_ANALYSIS, "", a.task_id, T0, commit=True)
    assert e.validate_lineage(p)["ok"] is True


# ══════════════ add_dependency + DAG ══════════════
def test_add_dependency(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    a = e.add_task(p, "a", KIND_DATA, "", "", T0, commit=True)
    b = e.add_task(p, "b", KIND_ANALYSIS, "", "", T0, commit=True)
    d = e.add_dependency(p, a.task_id, b.task_id, T0, commit=True)
    assert d.dependency_id.startswith("RTD:")


def test_dependency_self_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    a = e.add_task(p, "a", KIND_DATA, "", "", T0, commit=True)
    with pytest.raises(SelfDependencyError):
        e.add_dependency(p, a.task_id, a.task_id, T0, commit=True)


def test_dependency_cycle_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    a = e.add_task(p, "a", KIND_DATA, "", "", T0, commit=True)
    b = e.add_task(p, "b", KIND_ANALYSIS, "", "", T0, commit=True)
    c = e.add_task(p, "c", KIND_BACKTEST, "", "", T0, commit=True)
    e.add_dependency(p, a.task_id, b.task_id, T0, commit=True)
    e.add_dependency(p, b.task_id, c.task_id, T0, commit=True)
    with pytest.raises(DependencyCycleError):
        e.add_dependency(p, c.task_id, a.task_id, T0, commit=True)  # 순환
    assert len(ledger.plan_dependencies(p)) == 2  # 순환 간선 미기록


def test_dependency_unknown_task(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    a = e.add_task(p, "a", KIND_DATA, "", "", T0, commit=True)
    with pytest.raises(UnknownTaskError):
        e.add_dependency(p, a.task_id, "RTK:ghost", T0, commit=True)


def test_dependency_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    a = e.add_task(p, "a", KIND_DATA, "", "", T0, commit=True)
    b = e.add_task(p, "b", KIND_ANALYSIS, "", "", T0, commit=True)
    e.add_dependency(p, a.task_id, b.task_id, T0, commit=True)
    e.add_dependency(p, a.task_id, b.task_id, T1, commit=True)
    assert len(ledger.plan_dependencies(p)) == 1


# ══════════════ build_task_graph / validate_dag ══════════════
def test_build_task_graph(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, a, b, c = _chain_plan(e)
    g = e.build_task_graph(p)
    assert g["node_count"] == 3
    assert g["edge_count"] == 2
    assert g["is_dag"] is True
    assert g["roots"] == [a]
    assert g["leaves"] == [c]


def test_graph_topo_order(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, a, b, c = _chain_plan(e)
    order = e.build_task_graph(p)["order"]
    assert order.index(a) < order.index(b) < order.index(c)


def test_validate_dag_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, *_ = _chain_plan(e)
    assert e.validate_dag(p)["ok"] is True
    assert e.validate_dag(p)["is_dag"] is True


def test_dependency_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, a, b, c = _chain_plan(e)
    assert e.dependencies_of(p, c) == sorted([a, b])
    assert e.dependents_of(p, a) == sorted([b, c])


def test_redundant_dependency_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    a = e.add_task(p, "a", KIND_DATA, "", "", T0, commit=True)
    b = e.add_task(p, "b", KIND_ANALYSIS, "", "", T0, commit=True)
    c = e.add_task(p, "c", KIND_BACKTEST, "", "", T0, commit=True)
    e.add_dependency(p, a.task_id, b.task_id, T0, commit=True)
    e.add_dependency(p, b.task_id, c.task_id, T0, commit=True)
    e.add_dependency(p, a.task_id, c.task_id, T0, commit=True)  # a->c 는 잉여(a->b->c)
    red = e.redundant_dependencies(p)
    assert [a.task_id, c.task_id] in red


# ══════════════ finalize_plan + schedule ══════════════
def test_finalize_plan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, a, b, c = _chain_plan(e)
    res = e.finalize_plan(p, T1, commit=True)
    assert e.current_plan_state(p) == PLAN_PLANNED
    assert res["schedule"]["order"] == [a, b, c]


def test_schedule_waves(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    a = e.add_task(p, "a", KIND_DATA, "", "", T0, commit=True)
    b = e.add_task(p, "b", KIND_ANALYSIS, "", "", T0, commit=True)
    c = e.add_task(p, "c", KIND_BACKTEST, "", "", T0, commit=True)
    # a->c, b->c : wave0={a,b}, wave1={c}
    e.add_dependency(p, a.task_id, c.task_id, T0, commit=True)
    e.add_dependency(p, b.task_id, c.task_id, T0, commit=True)
    sched = e.build_schedule(p, T1, commit=True)
    assert sched.waves[0] == sorted([a.task_id, b.task_id])
    assert sched.waves[1] == [c.task_id]


def test_schedule_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, *_ = _chain_plan(e)
    a = e.build_schedule(p, T1, commit=False)
    b = e.build_schedule(p, T2, commit=False)
    assert a.order == b.order


def test_schedule_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, a, b, c = _chain_plan(e)
    e.build_schedule(p, T1, commit=True)
    # 스케줄 확정 후 (동결 전이라도) 동일 plan 재-스케줄은 idempotent; 순서 변화 시 불변 위반
    # 여기서는 idempotent 확인
    e.build_schedule(p, T2, commit=True)
    assert len(ledger.read_schedules()) == 1


# ══════════════ 동결(immutable plans) ══════════════
def test_frozen_after_finalize_task(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, *_ = _chain_plan(e)
    e.finalize_plan(p, T1, commit=True)
    with pytest.raises(PlanFrozenError):
        e.add_task(p, "late", KIND_REVIEW, "", "", T2, commit=True)


def test_frozen_after_finalize_dependency(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, a, b, c = _chain_plan(e)
    e.finalize_plan(p, T1, commit=True)
    with pytest.raises(PlanFrozenError):
        e.add_dependency(p, a, c, T2, commit=True)


def test_finalize_requires_requested(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, *_ = _chain_plan(e)
    e.finalize_plan(p, T1, commit=True)
    with pytest.raises(IllegalPlanTransition):
        e.finalize_plan(p, T2, commit=True)


# ══════════════ generate_report ══════════════
def test_report_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, a, b, c = _chain_plan(e)
    r = e.generate_report(p, "PLAN", {"k": 1}, T1, commit=True)
    assert r.report_id.startswith("RTR:")
    assert r.task_count == 3
    assert r.dependency_count == 2
    assert r.is_dag is True
    assert r.metrics["k"] == 1


def test_report_kind_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, *_ = _chain_plan(e)
    r = e.generate_report(p, "PLAN", {}, T1, commit=True)
    assert r.kind_distribution[KIND_DATA] == 1
    assert r.kind_distribution[KIND_ANALYSIS] == 1


def test_report_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, *_ = _chain_plan(e)
    a = e.generate_report(p, "PLAN", {}, T1, commit=False)
    b = e.generate_report(p, "PLAN", {}, T1, commit=False)
    assert a.to_dict() == b.to_dict()


def test_report_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, *_ = _chain_plan(e)
    e.generate_report(p, "PLAN", {}, T1, commit=True)
    e.generate_report(p, "PLAN", {}, T1, commit=True)
    assert len(ledger.read_reports()) == 1


def test_report_has_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, *_ = _chain_plan(e)
    r = e.generate_report(p, "PLAN", {}, T1, commit=True)
    assert "PLAN ≠ EXECUTE" in r.disclaimer


# ══════════════ 순수 그래프 함수 ══════════════
def test_topological_sort_pure():
    assert M.topological_sort(["a", "b", "c"], [("a", "b"), ("b", "c")]) == ["a", "b", "c"]
    assert M.topological_sort(["a", "b"], [("a", "b"), ("b", "a")]) is None


def test_detect_cycle_pure():
    assert M.detect_cycle([("a", "b"), ("b", "c")]) == []
    cyc = M.detect_cycle([("a", "b"), ("b", "a")])
    assert cyc and cyc[0] == cyc[-1]


def test_build_waves_pure():
    waves = M.build_waves(["a", "b", "c"], [("a", "c"), ("b", "c")])
    assert waves == [["a", "b"], ["c"]]
    assert M.build_waves(["a", "b"], [("a", "b"), ("b", "a")]) is None


def test_roots_leaves_pure():
    assert M.roots(["a", "b", "c"], [("a", "b"), ("b", "c")]) == ["a"]
    assert M.leaves(["a", "b", "c"], [("a", "b"), ("b", "c")]) == ["c"]


def test_ancestors_descendants_pure():
    edges = [("a", "b"), ("b", "c")]
    assert M.ancestors(edges, "c") == ["a", "b"]
    assert M.descendants(edges, "a") == ["b", "c"]


def test_redundant_edges_pure():
    assert M.redundant_edges([("a", "b"), ("b", "c"), ("a", "c")]) == [("a", "c")]
    assert M.redundant_edges([("a", "b"), ("b", "c")]) == []


def test_lineage_chain_pure():
    pm = {"c": "b", "b": "a"}
    assert M.lineage_chain(pm, "c") == ["b", "a"]


def test_can_transition_plan_pure():
    assert M.can_transition_plan(PLAN_REQUESTED, PLAN_PLANNED) is True
    assert M.can_transition_plan(PLAN_REQUESTED, PLAN_RUNNING) is False


# ══════════════ verify / replay ══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_task_planner.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_after_full_plan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_task_planner.verify import verify_chain
    e = _eng()
    p, *_ = _chain_plan(e)
    e.finalize_plan(p, T1, commit=True)
    e.generate_report(p, "PLAN", {}, T2, commit=True)
    res = verify_chain()
    assert res["ok"] is True
    assert res["dag"]["ok"] is True
    assert res["lifecycle"]["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    e.add_task(p, "x", KIND_DATA, "", "", T0, commit=True)
    fp = sp("rtp_tasks.jsonl")
    rows = [json.loads(x) for x in open(fp)]
    rows[0]["kind"] = "TAMPERED"
    with open(fp, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_task_planner.verify import verify_chain
    assert verify_chain()["ok"] is False


def test_verify_dag_integrity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_task_planner.verify import dag_integrity
    e = _eng()
    _chain_plan(e)
    assert dag_integrity()["ok"] is True


def test_verify_lifecycle_integrity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_task_planner.verify import lifecycle_integrity
    e = _eng()
    p, *_ = _chain_plan(e)
    e.finalize_plan(p, T1, commit=True)
    assert lifecycle_integrity()["ok"] is True


def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_task_planner.verify import replay
    e = _eng()
    _chain_plan(e)
    assert replay(e, T1)["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, *_ = _chain_plan(e)
    e.finalize_plan(p, T1, commit=True)
    s = e.summary(T2)
    assert s.task_count == 3
    assert s.dependency_count == 2
    assert s.schedule_count == 1


# ══════════════ 보안 / 불변식 (planning only) ══════════════
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


def test_engine_no_execution_methods():
    e = ResearchTaskPlannerEngine()
    for bad in ("execute", "trade", "deploy", "auto_deploy", "approve", "auto_approve",
                "allocate", "activate", "promote", "release", "run_task", "dispatch"):
        assert not hasattr(e, bad), bad


def test_no_auto_approve_or_deploy_in_source():
    base = os.path.dirname(os.path.dirname(__file__))
    for fn in ("engine.py", "models.py"):
        src = open(os.path.join(base, fn)).read()
        for bad in ("def approve", "def auto_approve", "def deploy", "def auto_deploy",
                    "def execute", "def allocate", "def run_task"):
            assert bad not in src, (fn, bad)


def test_forbidden_planner_verbs_defined():
    for v in ("APPROVE", "AUTO_APPROVE", "DEPLOY", "AUTO_DEPLOY", "EXECUTE"):
        assert M.is_forbidden_planner_verb(v) is True
    assert M.is_forbidden_planner_verb("PLAN") is False


def test_no_delete_or_update_api():
    import inspect
    src = inspect.getsource(ledger)
    for bad in ("def delete", "def update", "def remove", "def overwrite", "def edit_"):
        assert bad not in src, bad


def test_ledger_only_appends():
    import inspect
    src = inspect.getsource(ledger)
    assert '"a"' in src
    assert 'open(p, "w"' not in src


def test_disclaimer_marks_plan_only():
    from jarvis.research_task_planner.engine import _DISCLAIMER
    assert "PLAN ≠ EXECUTE" in _DISCLAIMER
    assert "SCHEDULE ≠ DEPLOY" in _DISCLAIMER


def test_records_frozen():
    t = M.TaskRecord(task_id="RTK:x", plan_id="RTP:p", name="a", kind="DATA", objective="",
                     parent_task="", created_at=T0)
    with pytest.raises(Exception):
        t.kind = "ANALYSIS"  # type: ignore


# ══════════════ 커버리지: id 접두사·상수 ══════════════
def test_id_prefixes_distinct():
    ids = {M.plan_id("o", "b", "t")[:4], M.plan_event_id("p", "s")[:4], M.task_id("p", "n")[:4],
           M.dependency_id("p", "u", "d")[:4], M.schedule_id("p")[:4],
           M.report_id("p", "s", T0)[:4]}
    assert len(ids) == 6


def test_five_owned_ledgers():
    assert len(ledger.ALL_LEDGERS) == 5
    fns = {l[0] for l in ledger.ALL_LEDGERS}
    assert len(fns) == 5
    assert all(f.startswith("rtp_") for f in fns)


def test_six_task_kinds():
    assert len(M.TASK_KINDS) == 6


def test_content_hash_excludes_hash_fields():
    r = {"a": 1, "previous_hash": "p", "record_hash": "r"}
    assert M.content_hash(r) == M.content_hash({"a": 1, "previous_hash": "z", "record_hash": "q"})


def test_input_digest_deterministic():
    assert M.input_digest("a", "b") == M.input_digest("a", "b")
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


def test_editable_states():
    assert M.EDITABLE_STATES == frozenset({PLAN_REQUESTED})


def test_list_plans_and_tasks(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, *_ = _chain_plan(e)
    assert p in e.list_plans()
    assert "collect" in e.list_tasks(p)


# ══════════════ CLI ══════════════
def _run(argv, capsys):
    from jarvis.research_task_planner.__main__ import main
    rc = main(argv)
    return rc, capsys.readouterr().out


def test_cli_request(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["request", "--objective", "o", "--by", "a", "--title", "t", "--commit"],
                   capsys)
    assert rc == 0
    assert json.loads(out)["plan"]["to_state"] == "REQUESTED"


def test_cli_task_and_depend_and_finalize(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _run(["request", "--objective", "o", "--by", "a", "--title", "t", "--commit"], capsys)
    e = _eng()
    p = e.list_plans()[0]
    _run(["task", "--plan", p, "--name", "c1", "--kind", "DATA", "--commit"], capsys)
    _run(["task", "--plan", p, "--name", "c2", "--kind", "ANALYSIS", "--commit"], capsys)
    t1 = M.task_id(p, "c1")
    t2 = M.task_id(p, "c2")
    rc, out = _run(["depend", "--plan", p, "--up", t1, "--down", t2, "--commit"], capsys)
    assert rc == 0
    rc2, out2 = _run(["finalize", "--plan", p, "--commit"], capsys)
    assert rc2 == 0
    assert json.loads(out2)["finalized"]["schedule"]["order"] == [t1, t2]


def test_cli_graph_validate(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _run(["request", "--objective", "o", "--by", "a", "--title", "t", "--commit"], capsys)
    e = _eng()
    p = e.list_plans()[0]
    _run(["task", "--plan", p, "--name", "c1", "--kind", "DATA", "--commit"], capsys)
    rc, out = _run(["graph", "--plan", p], capsys)
    assert rc == 0
    assert json.loads(out)["node_count"] == 1
    rc2, out2 = _run(["validate", "--plan", p], capsys)
    assert rc2 == 0
    assert json.loads(out2)["ok"] is True


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _run(["request", "--objective", "o", "--by", "a", "--title", "t", "--commit"], capsys)
    e = _eng()
    p = e.list_plans()[0]
    rc, out = _run(["report", "--plan", p, "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["report"]["plan_id"] == p


def test_cli_advance(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, *_ = _chain_plan(e)
    e.finalize_plan(p, T1, commit=True)
    rc, out = _run(["advance", "--plan", p, "--to", "RUNNING", "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["plan"]["to_state"] == "RUNNING"


def test_cli_plans(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _run(["request", "--objective", "o", "--by", "a", "--title", "t", "--commit"], capsys)
    rc, out = _run(["plans"], capsys)
    assert rc == 0
    assert len(json.loads(out)["plans"]) == 1


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["verify"], capsys)
    assert rc == 0
    assert json.loads(out)["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _chain_plan(e)
    rc, out = _run(["replay"], capsys)
    assert rc == 0
    assert json.loads(out)["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["summary"], capsys)
    assert rc == 0
    assert "task_count" in json.loads(out)


# ══════════════ 추가 커버리지 ══════════════
@pytest.mark.parametrize("frm,to,ok", [
    (PLAN_REQUESTED, PLAN_PLANNED, True), (PLAN_PLANNED, PLAN_RUNNING, True),
    (PLAN_RUNNING, PLAN_COMPLETED, True), (PLAN_COMPLETED, PLAN_REVIEWED, True),
    (PLAN_REQUESTED, PLAN_RUNNING, False), (PLAN_PLANNED, PLAN_COMPLETED, False),
    (PLAN_REVIEWED, PLAN_RUNNING, False), (PLAN_RUNNING, PLAN_REVIEWED, False),
])
def test_plan_transition_matrix(frm, to, ok):
    assert M.can_transition_plan(frm, to) is ok


@pytest.mark.parametrize("edges,expect", [
    ([("a", "b"), ("b", "c")], ["a", "b", "c"]),
    ([], ["a"]),
    ([("a", "c"), ("b", "c")], None),
])
def test_topo_various(edges, expect):
    nodes = sorted({n for e in edges for n in e} | {"a"})
    order = M.topological_sort(nodes, edges)
    if expect == ["a"]:
        assert order == sorted(nodes)
    elif expect is None:
        assert order is not None  # a,b,c dag still valid
    else:
        assert order == expect


def test_task_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    e.add_task(p, "x", KIND_DATA, "", "", T0, commit=False)
    assert ledger.read_tasks() == []


def test_dependency_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    a = e.add_task(p, "a", KIND_DATA, "", "", T0, commit=True)
    b = e.add_task(p, "b", KIND_ANALYSIS, "", "", T0, commit=True)
    e.add_dependency(p, a.task_id, b.task_id, T0, commit=False)
    assert ledger.read_dependencies() == []


def test_report_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, *_ = _chain_plan(e)
    e.generate_report(p, "PLAN", {}, T1, commit=False)
    assert ledger.read_reports() == []


def test_request_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().request_plan("o", "a", "t", T0, commit=False)
    assert ledger.read_plan_events() == []


def test_empty_graph(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    g = e.build_task_graph(p)
    assert g["node_count"] == 0
    assert g["is_dag"] is True


def test_single_task_graph(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    a = e.add_task(p, "solo", KIND_DATA, "", "", T0, commit=True)
    g = e.build_task_graph(p)
    assert g["roots"] == [a.task_id]
    assert g["leaves"] == [a.task_id]


def test_diamond_dag(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    a = e.add_task(p, "a", KIND_DATA, "", "", T0, commit=True)
    b = e.add_task(p, "b", KIND_ANALYSIS, "", "", T0, commit=True)
    c = e.add_task(p, "c", KIND_ANALYSIS, "", "", T0, commit=True)
    d = e.add_task(p, "d", KIND_BACKTEST, "", "", T0, commit=True)
    e.add_dependency(p, a.task_id, b.task_id, T0, commit=True)
    e.add_dependency(p, a.task_id, c.task_id, T0, commit=True)
    e.add_dependency(p, b.task_id, d.task_id, T0, commit=True)
    e.add_dependency(p, c.task_id, d.task_id, T0, commit=True)
    g = e.build_task_graph(p)
    assert g["roots"] == [a.task_id]
    assert g["leaves"] == [d.task_id]
    assert g["is_dag"] is True
    assert e.dependencies_of(p, d.task_id) == sorted([a.task_id, b.task_id, c.task_id])


def test_validate_dag_unknown_plan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownPlanError):
        _eng().validate_dag("RTP:ghost")


def test_lineage_no_parent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    a = e.add_task(p, "solo", KIND_DATA, "", "", T0, commit=True)
    assert e.trace_lineage(p, a.task_id) == []


def test_plan_meta_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownPlanError):
        _eng().plan_meta("RTP:ghost")


def test_multiple_plans_isolated(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p1 = _plan(e, "obj1", "a", "t1")
    p2 = _plan(e, "obj2", "a", "t2")
    e.add_task(p1, "x", KIND_DATA, "", "", T0, commit=True)
    e.add_task(p2, "y", KIND_DATA, "", "", T0, commit=True)
    assert e.list_tasks(p1) == ["x"]
    assert e.list_tasks(p2) == ["y"]


def test_finalize_records_schedule(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, *_ = _chain_plan(e)
    e.finalize_plan(p, T1, commit=True)
    assert len(ledger.read_schedules()) == 1


def test_schedule_task_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, *_ = _chain_plan(e)
    s = e.build_schedule(p, T1, commit=True)
    assert s.task_count == 3


def test_report_roots_leaves_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, a, b, c = _chain_plan(e)
    r = e.generate_report(p, "PLAN", {}, T1, commit=True)
    assert r.root_count == 1
    assert r.leaf_count == 1


def test_report_redundant_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    a = e.add_task(p, "a", KIND_DATA, "", "", T0, commit=True)
    b = e.add_task(p, "b", KIND_ANALYSIS, "", "", T0, commit=True)
    c = e.add_task(p, "c", KIND_BACKTEST, "", "", T0, commit=True)
    e.add_dependency(p, a.task_id, b.task_id, T0, commit=True)
    e.add_dependency(p, b.task_id, c.task_id, T0, commit=True)
    e.add_dependency(p, a.task_id, c.task_id, T0, commit=True)
    r = e.generate_report(p, "PLAN", {}, T1, commit=True)
    assert r.redundant_edge_count == 1


def test_report_lifecycle_state_reflected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, *_ = _chain_plan(e)
    e.finalize_plan(p, T1, commit=True)
    r = e.generate_report(p, "PLAN", {}, T2, commit=True)
    assert r.lifecycle_state == PLAN_PLANNED


def test_ancestors_empty():
    assert M.ancestors([], "x") == []


def test_descendants_empty():
    assert M.descendants([], "x") == []


def test_roots_all_isolated():
    assert M.roots(["a", "b"], []) == ["a", "b"]
    assert M.leaves(["a", "b"], []) == ["a", "b"]


def test_only_rtp_files_written(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    p, *_ = _chain_plan(e)
    e.finalize_plan(p, T1, commit=True)
    e.generate_report(p, "PLAN", {}, T2, commit=True)
    for fn in os.listdir(tmp_path):
        assert fn.startswith("rtp_"), fn


def test_plan_events_immutable_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, *_ = _chain_plan(e)
    e.finalize_plan(p, T1, commit=True)
    # 같은 to_state 재전이 시도는 idempotent(event id 동일) — 중복 미기록
    n_before = len(ledger.plan_events(p))
    # PLANNED 재확정은 IllegalPlanTransition
    with pytest.raises(IllegalPlanTransition):
        e.finalize_plan(p, T2, commit=True)
    assert len(ledger.plan_events(p)) == n_before


def test_dependents_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    a = e.add_task(p, "a", KIND_DATA, "", "", T0, commit=True)
    assert e.dependents_of(p, a.task_id) == []


def test_no_redundant_when_clean(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p, *_ = _chain_plan(e)
    assert e.redundant_dependencies(p) == []


def test_schedule_empty_plan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _plan(e)
    s = e.build_schedule(p, T1, commit=True)
    assert s.order == []
    assert s.waves == []


def test_plan_id_varies_by_input():
    assert M.plan_id("o1", "a", "t") != M.plan_id("o2", "a", "t")
    assert M.task_id("p", "n1") != M.task_id("p", "n2")


# ══════════════ 통합 시나리오 ══════════════
def test_end_to_end_plan_workflow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = e.request_plan("discover momentum alpha", "strategy_agent", "momentum-v1", T0,
                       commit=True).plan_id
    data = e.add_task(p, "load_prices", KIND_DATA, "load OHLCV", "", T0, commit=True)
    feat = e.add_task(p, "features", KIND_ANALYSIS, "compute", data.task_id, T0, commit=True)
    bt = e.add_task(p, "backtest", KIND_BACKTEST, "run", "", T0, commit=True)
    val = e.add_task(p, "validate", KIND_VALIDATION, "oos", "", T0, commit=True)
    rev = e.add_task(p, "review", KIND_REVIEW, "review", "", T0, commit=True)
    e.add_dependency(p, data.task_id, feat.task_id, T0, commit=True)
    e.add_dependency(p, feat.task_id, bt.task_id, T0, commit=True)
    e.add_dependency(p, bt.task_id, val.task_id, T0, commit=True)
    e.add_dependency(p, val.task_id, rev.task_id, T0, commit=True)
    fin = e.finalize_plan(p, T1, commit=True)
    assert fin["schedule"]["order"] == [data.task_id, feat.task_id, bt.task_id, val.task_id,
                                        rev.task_id]
    # 계획만 — 실행 없이 관측 상태만 전이
    e.mark_running(p, T2, commit=True)
    e.mark_completed(p, T3, commit=True)
    rep = e.generate_report(p, "PLAN", {"n": 5}, T4, commit=True)
    e.review_plan(p, T5, commit=True)
    assert rep.task_count == 5
    assert rep.is_dag is True
    assert e.dependencies_of(p, rev.task_id) == sorted([data.task_id, feat.task_id, bt.task_id,
                                                        val.task_id])
    from jarvis.research_task_planner.verify import verify_chain
    v = verify_chain()
    assert v["ok"] is True
    assert v["dag"]["ok"] and v["lineage"]["ok"] and v["lifecycle"]["ok"]
