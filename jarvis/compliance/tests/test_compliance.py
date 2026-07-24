"""P15 compliance 테스트 — 체크리스트·집계·결정성·보안."""
from __future__ import annotations

import ast
import os

import pytest

from jarvis.compliance import checklist as C
from jarvis.compliance.checklist import (
    CheckItem,
    run_checklist,
    run_compliance,
)

# 완전 컴플라이언트 증거
GOOD = {
    "secret_findings": 0, "static_critical": 0, "execution_capability": False,
    "live_execution_enabled": False, "dependency_ok": True, "sbom_present": True,
    "test_count": 300, "regression_pass": True, "modified_files": 0,
    "license_inventory": True, "pyproject_present": True,
    "version": "0.1.0", "ledger_ok": True, "artifacts_ok": True, "open_critical": 0,
    "commit_recorded": True, "replay_deterministic": True, "benchmark_reproducible": True,
    "hash_chained": True, "no_clock_ids": True,
}


# ═══════════════ 개별 체크리스트 ═══════════════
@pytest.mark.parametrize("name", ["security", "repository", "release", "reproducibility"])
def test_checklist_compliant(name):
    assert run_checklist(name, GOOD)["compliant"] is True


@pytest.mark.parametrize("name", ["security", "repository", "release", "reproducibility"])
def test_checklist_full_pass_rate(name):
    assert run_checklist(name, GOOD)["pass_rate"] == 1.0


def test_security_secret_fail():
    ev = dict(GOOD, secret_findings=3)
    res = run_checklist("security", ev)
    assert res["compliant"] is False
    assert "SEC-1" in res["required_failed"]


def test_security_execution_capability_fail():
    ev = dict(GOOD, execution_capability=True)
    assert run_checklist("security", ev)["compliant"] is False


def test_security_live_execution_fail():
    ev = dict(GOOD, live_execution_enabled=True)
    assert "SEC-4" in run_checklist("security", ev)["required_failed"]


def test_repository_modified_files_fail():
    ev = dict(GOOD, modified_files=5)
    assert "REPO-3" in run_checklist("repository", ev)["required_failed"]


def test_repository_regression_fail():
    ev = dict(GOOD, regression_pass=False)
    assert run_checklist("repository", ev)["compliant"] is False


def test_release_version_fail():
    ev = dict(GOOD, version="")
    assert "REL-1" in run_checklist("release", ev)["required_failed"]


def test_release_ledger_fail():
    ev = dict(GOOD, ledger_ok=False)
    assert run_checklist("release", ev)["compliant"] is False


def test_reproducibility_replay_fail():
    ev = dict(GOOD, replay_deterministic=False)
    assert "REPRO-1" in run_checklist("reproducibility", ev)["required_failed"]


def test_optional_check_not_required():
    # sbom_present 는 optional — False 여도 compliant
    ev = dict(GOOD, sbom_present=False)
    assert run_checklist("security", ev)["compliant"] is True


def test_checklist_items_type():
    res = run_checklist("security", GOOD)
    assert isinstance(res["items"], list)
    assert res["items"][0]["id"].startswith("SEC")


def test_checklist_deterministic():
    assert run_checklist("security", GOOD) == run_checklist("security", GOOD)


def test_empty_evidence_defaults_fail():
    # 빈 증거는 기본적으로 대부분 실패(안전 기본값)
    res = run_checklist("security", {})
    assert res["compliant"] is False


# ═══════════════ run_compliance ═══════════════
def test_compliance_all_good():
    rep = run_compliance(GOOD)
    assert rep["compliant"] is True
    assert rep["pass_rate"] == 1.0


def test_compliance_has_four_checklists():
    rep = run_compliance(GOOD)
    assert set(rep["checklists"]) == {"security", "repository", "release", "reproducibility"}


def test_compliance_failure_propagates():
    ev = dict(GOOD, secret_findings=1)
    rep = run_compliance(ev)
    assert rep["compliant"] is False
    assert "security" in rep["failed_checklists"]


def test_compliance_totals():
    rep = run_compliance(GOOD)
    assert rep["total_passed"] == rep["total_checks"]


def test_compliance_deterministic():
    assert run_compliance(GOOD) == run_compliance(GOOD)


def test_compliance_partial():
    ev = dict(GOOD, regression_pass=False, ledger_ok=False)
    rep = run_compliance(ev)
    assert set(rep["failed_checklists"]) == {"repository", "release"}


# ═══════════════ CheckItem ═══════════════
def test_checkitem_frozen():
    it = CheckItem("X", "d", True, True)
    with pytest.raises(Exception):
        it.passed = False


def test_checkitem_to_dict():
    it = CheckItem("X", "d", True, False)
    assert it.to_dict()["required"] is False


# ═══════════════ 보안 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN = ("jarvis.execution", "jarvis.broker", "jarvis.portfolio", "jarvis.risk",
              "jarvis.permission", "jarvis.deployment", "jarvis.live", "jarvis.order")


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_imports(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(f) for f in _FORBIDDEN), node.module


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()


@pytest.mark.parametrize("path", _SRC)
def test_no_auto_approval(path):
    # 자동 승인 함수 없음
    src = open(path).read()
    assert "def auto_approve" not in src
    assert "def force_pass" not in src
