"""P14 benchmark 테스트 — 결정적 측정·재현성·이력·비교·타겟 정확성·보안."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.benchmark import report as R
from jarvis.benchmark import suite as S
from jarvis.benchmark import targets as T
from jarvis.benchmark.harness import BenchmarkResult, StepClock, run_benchmark


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.benchmark.report.state_path", sp)
    return sp


# ═══════════════ StepClock ═══════════════
def test_stepclock_increments():
    c = StepClock(0.0, 1.0)
    assert c() == 0.0
    assert c() == 1.0
    assert c() == 2.0


def test_stepclock_custom_step():
    c = StepClock(10.0, 0.5)
    assert c() == 10.0
    assert c() == 10.5


@pytest.mark.parametrize("start,step", [(0, 1), (5, 2), (100, 0.25)])
def test_stepclock_param(start, step):
    c = StepClock(start, step)
    assert c() == start
    assert c() == start + step


# ═══════════════ run_benchmark ═══════════════
def test_run_benchmark_deterministic_elapsed():
    r = run_benchmark("t", lambda: 42, iterations=3, clock=StepClock(0, 1))
    # 각 iter: t0,t1 소비 → dt=1.0, 3 iters → 3.0
    assert r.elapsed == 3.0
    assert r.per_iter == 1.0


def test_run_benchmark_checksum_stable():
    a = run_benchmark("t", lambda: {"x": 1}, clock=StepClock())
    b = run_benchmark("t", lambda: {"x": 1}, clock=StepClock())
    assert a.checksum == b.checksum


def test_run_benchmark_checksum_differs():
    a = run_benchmark("t", lambda: 1, clock=StepClock())
    b = run_benchmark("t", lambda: 2, clock=StepClock())
    assert a.checksum != b.checksum


def test_run_benchmark_iterations_recorded():
    r = run_benchmark("t", lambda: 1, iterations=5, clock=StepClock())
    assert r.iterations == 5


def test_run_benchmark_work_units():
    r = run_benchmark("t", lambda: 1, work_units=99, clock=StepClock())
    assert r.work_units == 99


def test_run_benchmark_min_max():
    r = run_benchmark("t", lambda: 1, iterations=4, clock=StepClock(0, 1))
    assert r.min_iter == 1.0
    assert r.max_iter == 1.0


def test_run_benchmark_zero_iterations_rejected():
    with pytest.raises(ValueError):
        run_benchmark("t", lambda: 1, iterations=0)


def test_run_benchmark_result_type():
    assert isinstance(run_benchmark("t", lambda: 1, clock=StepClock()), BenchmarkResult)


def test_run_benchmark_frozen():
    r = run_benchmark("t", lambda: 1, clock=StepClock())
    with pytest.raises(Exception):
        r.name = "x"


def test_run_benchmark_default_clock_runs():
    r = run_benchmark("t", lambda: 1, iterations=2)
    assert r.iterations == 2
    assert r.elapsed >= 0.0


# ═══════════════ targets: 결정성 ═══════════════
def test_make_records_deterministic():
    assert T.make_records(10) == T.make_records(10)


def test_make_records_chain():
    recs = T.make_records(5)
    assert recs[0]["previous_hash"] == "GENESIS"
    assert recs[1]["previous_hash"] == recs[0]["record_hash"]


def test_replay_deterministic():
    recs = T.make_records(20)
    assert T.replay(recs) == T.replay(recs)


def test_hash_verification_all_valid():
    recs = T.make_records(30)
    assert T.hash_verification(recs) == 30


def test_hash_verification_detects_tamper():
    recs = T.make_records(10)
    recs[5]["payload"] = "TAMPERED"
    assert T.hash_verification(recs) < 10


def test_lineage_traversal_deterministic():
    tree = T.make_tree(31)
    assert T.lineage_traversal(tree) == T.lineage_traversal(tree)


def test_lineage_traversal_root_zero():
    tree = T.make_tree(1)
    assert T.lineage_traversal(tree) == 0


def test_graph_traversal_reaches_nodes():
    g = T.make_graph(20)
    assert T.graph_traversal(g) >= 1


def test_graph_traversal_deterministic():
    g = T.make_graph(50)
    assert T.graph_traversal(g) == T.graph_traversal(g)


def test_simulation_replay_deterministic():
    assert T.simulation_replay(500) == T.simulation_replay(500)


def test_decision_evaluation_deterministic():
    assert T.decision_evaluation(200) == T.decision_evaluation(200)


def test_memory_retrieval_all_hits():
    assert T.memory_retrieval(100, 50) == 50


def test_agent_workflow_deterministic():
    assert T.agent_workflow(300) == T.agent_workflow(300)


def test_agent_workflow_valid_state():
    assert T.agent_workflow(123) in ("INIT", "PLAN", "ACT", "OBSERVE", "RECORD")


def test_os_snapshot_deterministic():
    assert T.os_snapshot_generation(10, 4) == T.os_snapshot_generation(10, 4)


def test_os_snapshot_total():
    snap = T.os_snapshot_generation(3, 2)
    assert snap["total"] == 2 + 4 + 6


def test_ledger_append_writes(tmp_path):
    p = os.path.join(tmp_path, "a.jsonl")
    n_bytes = T.ledger_append(p, 10)
    assert n_bytes > 0
    assert sum(1 for _ in open(p)) == 10


@pytest.mark.parametrize("n", [1, 5, 50, 200])
def test_make_records_len(n):
    assert len(T.make_records(n)) == n


@pytest.mark.parametrize("n", [2, 10, 100])
def test_make_tree_len(n):
    assert len(T.make_tree(n)) == n


@pytest.mark.parametrize("n", [5, 20, 64])
def test_make_graph_no_self_loop(n):
    g = T.make_graph(n)
    for node, nbrs in g.items():
        assert node not in nbrs


# ═══════════════ suite ═══════════════
def test_suite_runs_all(tmp_path):
    rep = S.run_suite("s", clock=StepClock(), tmp_dir=str(tmp_path))
    names = [r["name"] for r in rep.results]
    assert names == list(S.BENCHMARK_NAMES)


def test_suite_has_ten_benchmarks():
    assert len(S.BENCHMARK_NAMES) == 10


def test_suite_deterministic_checksum(tmp_path):
    a = S.run_suite("s", clock=StepClock(), tmp_dir=str(tmp_path))
    b = S.run_suite("s", clock=StepClock(), tmp_dir=str(tmp_path))
    assert a.checksum == b.checksum


def test_suite_checksum_independent_of_clock(tmp_path):
    a = S.run_suite("s", clock=StepClock(0, 1), tmp_dir=str(tmp_path))
    b = S.run_suite("s", clock=StepClock(100, 5), tmp_dir=str(tmp_path))
    assert a.checksum == b.checksum  # 작업 지문은 타이밍 무관


def test_suite_without_tmp_dir(tmp_path):
    rep = S.run_suite("s", clock=StepClock())
    assert len(rep.results) == 10


def test_suite_results_sorted(tmp_path):
    rep = S.run_suite("s", clock=StepClock(), tmp_dir=str(tmp_path))
    names = [r["name"] for r in rep.results]
    assert names == sorted(names)


def test_suite_scale_override(tmp_path):
    rep = S.run_suite("s", scale={"replay": 10}, clock=StepClock(), tmp_dir=str(tmp_path))
    replay_r = next(r for r in rep.results if r["name"] == "replay")
    assert replay_r["work_units"] == 10


@pytest.mark.parametrize("name", S.BENCHMARK_NAMES)
def test_each_benchmark_present(tmp_path, name):
    rep = S.run_suite("s", clock=StepClock(), tmp_dir=str(tmp_path))
    assert any(r["name"] == name for r in rep.results)


@pytest.mark.parametrize("name", S.BENCHMARK_NAMES)
def test_each_benchmark_has_checksum(tmp_path, name):
    rep = S.run_suite("s", clock=StepClock(), tmp_dir=str(tmp_path))
    r = next(x for x in rep.results if x["name"] == name)
    assert r["checksum"].startswith("sha256:")


# ═══════════════ report / history / compare ═══════════════
def test_build_report_sorted():
    r1 = run_benchmark("zeta", lambda: 1, clock=StepClock())
    r2 = run_benchmark("alpha", lambda: 1, clock=StepClock())
    rep = R.build_report("l", [r1, r2])
    assert [r["name"] for r in rep.results] == ["alpha", "zeta"]


def test_build_report_total_elapsed():
    r1 = run_benchmark("a", lambda: 1, iterations=2, clock=StepClock(0, 1))
    r2 = run_benchmark("b", lambda: 1, iterations=2, clock=StepClock(0, 1))
    rep = R.build_report("l", [r1, r2])
    assert rep.total_elapsed == r1.elapsed + r2.elapsed


def test_report_checksum_deterministic():
    r = run_benchmark("a", lambda: 1, clock=StepClock())
    rep1 = R.build_report("l", [r])
    rep2 = R.build_report("l", [r])
    assert rep1.checksum == rep2.checksum


def test_history_append_read(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    rep = S.run_suite("s", clock=StepClock())
    R.append_history(rep)
    hist = R.read_history()
    assert len(hist) == 1
    assert hist[0]["label"] == "s"


def test_history_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert R.read_history() == []


def test_history_multiple(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    R.append_history(S.run_suite("a", clock=StepClock()))
    R.append_history(S.run_suite("b", clock=StepClock()))
    assert len(R.read_history()) == 2


def test_compare_no_regression():
    rep = S.run_suite("s", clock=StepClock()).to_dict()
    cmp = R.compare_reports(rep, rep)
    assert cmp["regressions"] == []
    assert cmp["same_workload"] is True


def test_compare_detects_regression():
    prev = {"checksum": "x", "results": [{"name": "a", "per_iter": 1.0}]}
    cur = {"checksum": "x", "results": [{"name": "a", "per_iter": 2.0}]}
    cmp = R.compare_reports(prev, cur)
    assert cmp["regressions"] and cmp["regressions"][0]["name"] == "a"


def test_compare_detects_improvement():
    prev = {"checksum": "x", "results": [{"name": "a", "per_iter": 2.0}]}
    cur = {"checksum": "x", "results": [{"name": "a", "per_iter": 1.0}]}
    cmp = R.compare_reports(prev, cur)
    assert cmp["improvements"] and cmp["improvements"][0]["name"] == "a"


def test_compare_unchanged():
    prev = {"checksum": "x", "results": [{"name": "a", "per_iter": 1.0}]}
    cur = {"checksum": "x", "results": [{"name": "a", "per_iter": 1.0}]}
    cmp = R.compare_reports(prev, cur)
    assert cmp["unchanged"] == ["a"]


def test_compare_added_removed():
    prev = {"checksum": "x", "results": [{"name": "a", "per_iter": 1.0}]}
    cur = {"checksum": "y", "results": [{"name": "b", "per_iter": 1.0}]}
    cmp = R.compare_reports(prev, cur)
    assert cmp["added"] == ["b"]
    assert cmp["removed"] == ["a"]
    assert cmp["same_workload"] is False


def test_compare_tolerance():
    prev = {"checksum": "x", "results": [{"name": "a", "per_iter": 1.0}]}
    cur = {"checksum": "x", "results": [{"name": "a", "per_iter": 1.05}]}
    cmp = R.compare_reports(prev, cur, tolerance=0.1)
    assert cmp["regressions"] == []  # 10% 허용 내


# ═══════════════ 보안 스캔 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN_IMPORTS = (
    "jarvis.execution", "jarvis.broker", "jarvis.portfolio", "jarvis.risk",
    "jarvis.permission", "jarvis.deployment", "jarvis.live", "jarvis.order",
    "jarvis.live_trading",
)


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_imports(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(f) for f in _FORBIDDEN_IMPORTS), node.module


@pytest.mark.parametrize("path", _SRC)
def test_no_execution_defs(path):
    tree = ast.parse(open(path).read())
    bad = ("execute_trade", "place_order", "deploy_model", "allocate_capital")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()


def test_history_file_namespaced():
    assert R.HISTORY_FILE.startswith("bench_")
