"""P40 release_candidate 테스트 — 릴리스 산출물·릴리스 게이트(무결성·보안·준비성·재현·의존성)·상태 선언.
연구 보조만, 라이브 실행/자율 거래 없음."""
from __future__ import annotations

import ast
import os

import pytest

from jarvis.release_candidate import gate, generator
from jarvis.release_candidate import models as M
from jarvis.release_candidate.models import (
    KNOWN_LIMITATIONS,
    PLATFORM_NAME,
    RELEASE_ARTIFACTS,
    RELEASE_GATES,
    STATUS_STATEMENTS,
    VERSION,
    artifact_hash,
)


# ═══════════════ version / artifacts ═══════════════
def test_version():
    assert VERSION == "1.0.0-rc.1"


def test_platform_name():
    assert "Jarvis" in PLATFORM_NAME


def test_seven_artifacts():
    assert len(RELEASE_ARTIFACTS) == 7


@pytest.mark.parametrize("art", RELEASE_ARTIFACTS)
def test_artifact_is_release(art):
    assert M.is_release_artifact(art)


def test_generate_complete():
    assert set(generator.generate_artifacts()) == set(RELEASE_ARTIFACTS)


@pytest.mark.parametrize("art", RELEASE_ARTIFACTS)
def test_artifact_nonempty(art):
    assert len(generator.generate_artifacts()[art]) > 0


def test_generate_deterministic():
    assert generator.generate_artifacts() == generator.generate_artifacts()


@pytest.mark.parametrize("art", RELEASE_ARTIFACTS)
def test_artifact_hash_deterministic(art):
    c = generator.generate_artifacts()[art]
    assert artifact_hash(c) == artifact_hash(c)


def test_version_file_content():
    assert generator.generate_artifacts()["VERSION"].strip() == "1.0.0-rc.1"


# ═══════════════ artifact content ═══════════════
def test_release_notes_status():
    doc = generator.generate_artifacts()["RELEASE_NOTES.md"]
    assert "No live execution" in doc
    assert "No autonomous trading" in doc


@pytest.mark.parametrize("stmt", STATUS_STATEMENTS)
def test_status_in_release_notes(stmt):
    doc = generator.generate_artifacts()["RELEASE_NOTES.md"]
    assert stmt in doc


def test_architecture_summary_layers():
    doc = generator.generate_artifacts()["ARCHITECTURE_SUMMARY.md"]
    from jarvis.system_integration.models import LAYER_REGISTRY
    for l in LAYER_REGISTRY:
        assert l["package"] in doc


def test_feature_inventory_not_included():
    doc = generator.generate_artifacts()["FEATURE_INVENTORY.md"]
    assert "Not included" in doc
    assert "trade execution" in doc.lower()


def test_test_summary_regression():
    doc = generator.generate_artifacts()["TEST_SUMMARY.md"]
    assert "pytest jarvis" in doc


def test_security_summary_forbidden():
    doc = generator.generate_artifacts()["SECURITY_SUMMARY.md"]
    assert "execute_trade" in doc
    assert "broker" in doc.lower()


@pytest.mark.parametrize("lim", KNOWN_LIMITATIONS)
def test_known_limitation_present(lim):
    doc = generator.generate_artifacts()["KNOWN_LIMITATIONS.md"]
    assert lim in doc


def test_status_statements_count():
    assert len(STATUS_STATEMENTS) == 6


def test_status_research_only():
    assert "Research assistance only." in STATUS_STATEMENTS


# ═══════════════ release gate ═══════════════
def test_release_gates_count():
    assert len(RELEASE_GATES) == 5


def test_run_release_gate_approved():
    res = gate.run_release_gate()
    assert res["approved"] is True


def test_gate_no_live_execution():
    res = gate.run_release_gate()
    assert res["live_execution"] is False
    assert res["autonomous_trading"] is False


def test_gate_system_integrity():
    r = gate.check_system_integrity()
    assert r["ok"] is True
    assert r["failed"] == 0


def test_gate_security_audit():
    r = gate.check_security_audit()
    assert r["ok"] is True
    assert r["failed"] == 0


def test_gate_production_readiness():
    r = gate.check_production_readiness()
    assert r["ok"] is True
    assert r["deployment_performed"] is False


def test_gate_replay_validation():
    assert gate.check_replay_validation()["ok"] is True


def test_gate_dependency_validation():
    assert gate.check_dependency_validation()["ok"] is True


def test_gate_has_five_gates():
    res = gate.run_release_gate()
    assert len(res["gates"]) == 5
    gates = {g["gate"] for g in res["gates"]}
    assert gates == set(RELEASE_GATES)


def test_gate_all_ok():
    res = gate.run_release_gate()
    assert all(g["ok"] for g in res["gates"])


def test_gate_deterministic():
    assert gate.run_release_gate() == gate.run_release_gate()


@pytest.mark.parametrize("g", RELEASE_GATES)
def test_each_gate_name(g):
    assert g in RELEASE_GATES


# ═══════════════ artifacts on disk ═══════════════
def test_release_dir_exists():
    assert os.path.isdir(generator.release_dir())


@pytest.mark.parametrize("art", RELEASE_ARTIFACTS)
def test_artifact_on_disk(art):
    assert os.path.exists(os.path.join(generator.release_dir(), art))


@pytest.mark.parametrize("art", RELEASE_ARTIFACTS)
def test_artifact_matches_generated(art):
    on_disk = open(os.path.join(generator.release_dir(), art)).read()
    assert on_disk == generator.generate_artifacts()[art]


def test_version_file_on_disk():
    assert open(os.path.join(generator.release_dir(), "VERSION")).read().strip() == VERSION


# ═══════════════ CLI ═══════════════
def test_cli_version(capsys):
    from jarvis.release_candidate.__main__ import main
    assert main(["version"]) == 0
    assert capsys.readouterr().out.strip() == "1.0.0-rc.1"


def test_cli_status(capsys):
    import json
    from jarvis.release_candidate.__main__ import main
    assert main(["status"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["version"] == VERSION
    assert "Research assistance only." in out["status"]


def test_cli_gate(capsys):
    import json
    from jarvis.release_candidate.__main__ import main
    assert main(["gate"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["approved"] is True


def test_cli_generate(capsys):
    import json
    from jarvis.release_candidate.__main__ import main
    assert main(["generate"]) == 0
    assert json.loads(capsys.readouterr().out)["count"] == 7


# ═══════════════ 자체 안전성(실행/배포 없음) ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_imports(path):
    forbidden = ("jarvis.execution", "jarvis.broker", "jarvis.live_trading",
                 "jarvis.portfolio_execution", "jarvis.live_portfolio")
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(f) for f in forbidden), node.module


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_method_defs(path):
    tree = ast.parse(open(path).read())
    bad = ("execute", "deploy", "trade", "allocate", "approve", "activate_live")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert ("claude" + "-opus") not in open(path).read().lower()


def test_no_ledger():
    assert not os.path.exists(os.path.join(_PKG, "ledger.py"))


# ═══════════════ end-to-end: v1.0 RC ═══════════════
def test_end_to_end_v1_release_candidate():
    # 1. 7개 릴리스 산출물 생성
    arts = generator.generate_artifacts()
    assert len(arts) == 7
    assert arts["VERSION"].strip() == "1.0.0-rc.1"
    # 2. 릴리스 게이트 승인(무결성·보안·준비성·재현·의존성)
    res = gate.run_release_gate()
    assert res["approved"] is True
    # 3. 라이브 실행·자율 거래 없음
    assert res["live_execution"] is False
    assert res["autonomous_trading"] is False
    # 4. 5개 게이트 모두 통과
    assert all(g["ok"] for g in res["gates"])
    # 5. 상태 선언: 연구 보조만
    assert "Research assistance only." in STATUS_STATEMENTS
    assert "No live execution." in STATUS_STATEMENTS
    # 6. 디스크 산출물 == 생성 산출물
    for name, content in arts.items():
        assert open(os.path.join(generator.release_dir(), name)).read() == content
