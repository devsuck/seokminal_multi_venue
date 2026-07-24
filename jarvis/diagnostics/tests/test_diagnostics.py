"""P14 diagnostics 테스트 — 죽은/대형 원장·느린 replay·깨진 계보·드리프트·회귀·집계·보안."""
from __future__ import annotations

import ast
import os

import pytest

from jarvis.diagnostics.checks import (
    CRITICAL,
    INFO,
    SEVERITIES,
    WARNING,
    Diagnostic,
    broken_lineage,
    dead_ledger,
    large_ledger,
    performance_regression,
    run_diagnostics,
    slow_replay,
    snapshot_drift,
)


# ═══════════════ dead_ledger ═══════════════
def test_dead_ledger_empty():
    d = dead_ledger("l", 0)
    assert d.code == "DEAD_LEDGER"
    assert d.severity == WARNING


def test_dead_ledger_nonempty():
    assert dead_ledger("l", 5) is None


def test_dead_ledger_negative():
    assert dead_ledger("l", -1).code == "DEAD_LEDGER"


def test_dead_ledger_not_actionable():
    assert dead_ledger("l", 0).is_actionable is False


# ═══════════════ large_ledger ═══════════════
def test_large_ledger_over():
    d = large_ledger("l", 200, threshold=100)
    assert d.code == "LARGE_LEDGER"


def test_large_ledger_under():
    assert large_ledger("l", 50, threshold=100) is None


def test_large_ledger_boundary():
    assert large_ledger("l", 100, threshold=100) is None  # 초과만


@pytest.mark.parametrize("cnt,thr,flag", [(0, 100, False), (101, 100, True), (100, 100, False),
                                          (99999, 100000, False), (100001, 100000, True)])
def test_large_ledger_param(cnt, thr, flag):
    assert (large_ledger("l", cnt, threshold=thr) is not None) == flag


# ═══════════════ slow_replay ═══════════════
def test_slow_replay_over():
    d = slow_replay("r", 2.0, threshold=1.0)
    assert d.code == "SLOW_REPLAY"


def test_slow_replay_under():
    assert slow_replay("r", 0.5, threshold=1.0) is None


@pytest.mark.parametrize("dur,thr,flag", [(0.5, 1.0, False), (1.5, 1.0, True), (1.0, 1.0, False)])
def test_slow_replay_param(dur, thr, flag):
    assert (slow_replay("r", dur, threshold=thr) is not None) == flag


# ═══════════════ broken_lineage ═══════════════
def test_broken_lineage_clean():
    arts = [{"artifact_id": "A", "parent_artifact": ""},
            {"artifact_id": "B", "parent_artifact": "A"}]
    assert broken_lineage(arts) == []


def test_broken_lineage_dangling():
    arts = [{"artifact_id": "B", "parent_artifact": "GHOST"}]
    out = broken_lineage(arts)
    assert len(out) == 1
    assert out[0].severity == CRITICAL


def test_broken_lineage_multiple():
    arts = [{"artifact_id": "A", "parent_artifact": "X"},
            {"artifact_id": "B", "parent_artifact": "Y"}]
    assert len(broken_lineage(arts)) == 2


def test_broken_lineage_empty():
    assert broken_lineage([]) == []


def test_broken_lineage_custom_fields():
    arts = [{"id": "B", "parent": "GHOST"}]
    out = broken_lineage(arts, id_field="id", parent_field="parent")
    assert len(out) == 1


# ═══════════════ snapshot_drift ═══════════════
def test_drift_none():
    assert snapshot_drift({"a": 1}, {"a": 1}) == []


def test_drift_decrease_warning():
    out = snapshot_drift({"a": 5}, {"a": 3})
    assert out[0].severity == WARNING


def test_drift_increase_info():
    out = snapshot_drift({"a": 3}, {"a": 5})
    assert out[0].severity == INFO


def test_drift_added():
    out = snapshot_drift({}, {"a": 1})
    assert out[0].severity == INFO
    assert "added" in out[0].detail


def test_drift_removed_warning():
    out = snapshot_drift({"a": 1}, {})
    assert out[0].severity == WARNING


def test_drift_deterministic():
    assert snapshot_drift({"a": 1, "b": 2}, {"a": 2}) == snapshot_drift({"a": 1, "b": 2}, {"a": 2})


def test_drift_sorted_keys():
    out = snapshot_drift({"z": 1, "a": 1}, {"z": 2, "a": 2})
    subjects = [d.subject for d in out]
    assert subjects == sorted(subjects)


# ═══════════════ performance_regression ═══════════════
def test_perf_regression():
    cmp = {"same_workload": True, "regressions": [{"name": "a", "previous": 1.0, "current": 2.0}]}
    out = performance_regression(cmp)
    assert out[0].code == "PERF_REGRESSION"


def test_perf_no_regression():
    cmp = {"same_workload": True, "regressions": []}
    assert performance_regression(cmp) == []


def test_perf_workload_changed():
    cmp = {"same_workload": False, "regressions": []}
    out = performance_regression(cmp)
    assert any(d.code == "WORKLOAD_CHANGED" for d in out)


# ═══════════════ run_diagnostics ═══════════════
def test_run_all_healthy():
    rep = run_diagnostics(ledgers={"a": 5}, replays={"a": 0.1})
    assert rep["healthy"] is True
    assert rep["ok"] is True


def test_run_dead_ledger():
    rep = run_diagnostics(ledgers={"a": 0})
    assert rep["total"] == 1
    assert rep["by_severity"][WARNING] == 1


def test_run_critical_lineage():
    rep = run_diagnostics(artifacts=[{"artifact_id": "B", "parent_artifact": "X"}])
    assert rep["ok"] is False
    assert rep["by_severity"][CRITICAL] == 1


def test_run_severity_ordering():
    rep = run_diagnostics(
        ledgers={"a": 0},
        artifacts=[{"artifact_id": "B", "parent_artifact": "X"}])
    # CRITICAL 먼저
    assert rep["findings"][0]["severity"] == CRITICAL


def test_run_deterministic():
    kw = dict(ledgers={"a": 0, "b": 200}, replays={"r": 2.0}, large_threshold=100,
              slow_threshold=1.0)
    assert run_diagnostics(**kw) == run_diagnostics(**kw)


def test_run_snapshot_drift():
    rep = run_diagnostics(snapshots=({"a": 5}, {"a": 3}))
    assert rep["by_severity"][WARNING] == 1


def test_run_compare_regression():
    cmp = {"same_workload": True, "regressions": [{"name": "x", "previous": 1.0, "current": 3.0}]}
    rep = run_diagnostics(compare_result=cmp)
    assert any(f["code"] == "PERF_REGRESSION" for f in rep["findings"])


def test_run_large_and_dead():
    rep = run_diagnostics(ledgers={"empty": 0, "big": 500}, large_threshold=100)
    codes = {f["code"] for f in rep["findings"]}
    assert codes == {"DEAD_LEDGER", "LARGE_LEDGER"}


def test_run_empty_inputs():
    rep = run_diagnostics()
    assert rep["healthy"] is True
    assert rep["total"] == 0


def test_run_by_severity_keys():
    rep = run_diagnostics(ledgers={"a": 0})
    assert set(rep["by_severity"]) == set(SEVERITIES)


def test_run_findings_not_actionable():
    rep = run_diagnostics(ledgers={"a": 0})
    assert all(f["is_actionable"] is False for f in rep["findings"])


# ═══════════════ Diagnostic 자료형 ═══════════════
def test_diagnostic_frozen():
    d = Diagnostic("C", INFO, "s", "d")
    with pytest.raises(Exception):
        d.code = "X"


def test_diagnostic_to_dict():
    d = Diagnostic("C", WARNING, "s", "d")
    assert d.to_dict()["severity"] == WARNING


@pytest.mark.parametrize("sev", SEVERITIES)
def test_severities_valid(sev):
    assert sev in SEVERITIES


# ═══════════════ 보안 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN_IMPORTS = ("jarvis.execution", "jarvis.broker", "jarvis.portfolio", "jarvis.risk",
                      "jarvis.permission", "jarvis.deployment", "jarvis.live", "jarvis.order")


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_imports(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(f) for f in _FORBIDDEN_IMPORTS), node.module


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()


@pytest.mark.parametrize("path", _SRC)
def test_no_execution_defs(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in ("execute_trade", "place_order", "deploy_model", "auto_recover")
