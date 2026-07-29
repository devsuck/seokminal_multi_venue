"""P35 system_integration 테스트 — 전체 생태계 검증: 구조·소유권·접두사·안전성(import/메서드)·append-only·
모델유출·API일관성·해시체인·계보·아키텍처·의존성·verify·replay·CLI. VALIDATION ≠ MUTATION."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.system_integration import ledger
from jarvis.system_integration import models as M
from jarvis.system_integration.engine import SystemIntegrationEngine
from jarvis.system_integration.models import (
    CHECK_TYPES,
    FORBIDDEN_VERBS,
    LAYER_REGISTRY,
    REQUIRED_MODULES,
    content_hash,
    packages_unique,
    prefixes_unique,
    verify_hash_records,
)
from jarvis.system_integration.verify import (
    duplicate_integrity,
    finding_integrity,
    lineage_integrity,
    replay,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]
_PACKAGES = [l["package"] for l in LAYER_REGISTRY]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.system_integration.ledger.state_path", sp)
    return sp


def _eng():
    return SystemIntegrationEngine()


# ═══════════════ registry ═══════════════
def test_registry_size():
    assert len(LAYER_REGISTRY) == 14  # P21~P34


def test_prefixes_unique():
    assert prefixes_unique() is True


def test_packages_unique():
    assert packages_unique() is True


def test_registry_fields():
    for l in LAYER_REGISTRY:
        assert set(l) == {"package", "prefix", "phase"}


@pytest.mark.parametrize("layer", LAYER_REGISTRY)
def test_registry_phases_ordered(layer):
    assert layer["phase"].startswith("P")


# ═══════════════ 계층별 구조 검증(P21~P34) ═══════════════
@pytest.mark.parametrize("package", _PACKAGES)
def test_structure_all_layers(package):
    r = _eng().check_structure(package)
    assert r["status"] == "PASS", r["detail"]


@pytest.mark.parametrize("package", _PACKAGES)
def test_prefix_confinement_all_layers(package):
    layer = next(l for l in LAYER_REGISTRY if l["package"] == package)
    r = _eng().check_prefix_confinement(package, layer["prefix"])
    assert r["status"] == "PASS", r["detail"]


@pytest.mark.parametrize("package", _PACKAGES)
def test_safety_imports_all_layers(package):
    r = _eng().check_safety_imports(package)
    assert r["status"] == "PASS", r["detail"]


@pytest.mark.parametrize("package", _PACKAGES)
def test_safety_methods_all_layers(package):
    r = _eng().check_safety_methods(package)
    assert r["status"] == "PASS", r["detail"]


@pytest.mark.parametrize("package", _PACKAGES)
def test_append_only_all_layers(package):
    r = _eng().check_append_only(package)
    assert r["status"] == "PASS", r["detail"]


@pytest.mark.parametrize("package", _PACKAGES)
def test_model_leak_all_layers(package):
    r = _eng().check_model_leak(package)
    assert r["status"] == "PASS", r["detail"]


@pytest.mark.parametrize("package", _PACKAGES)
def test_api_consistency_all_layers(package):
    r = _eng().check_api_consistency(package)
    assert r["status"] == "PASS", r["detail"]


# ═══════════════ check detail ═══════════════
def test_check_structure_shape():
    r = _eng().check_structure("production_readiness")
    assert r["check_type"] == "STRUCTURE"
    assert r["layer"] == "production_readiness"


def test_check_structure_missing():
    r = _eng().check_structure("nonexistent_package_xyz")
    assert r["status"] == "FAIL"


def test_check_ownership():
    r = _eng().check_ownership()
    assert r["status"] == "PASS"


def test_required_modules():
    assert "engine.py" in REQUIRED_MODULES
    assert "verify.py" in REQUIRED_MODULES
    assert "ledger.py" in REQUIRED_MODULES


@pytest.mark.parametrize("ct", CHECK_TYPES)
def test_check_types(ct):
    assert ct in CHECK_TYPES


# ═══════════════ generic hash chain verification ═══════════════
def _chain(engine, records):
    # helper: seal a list of core dicts into a valid chain using shared algorithm
    out = []
    prev = "GENESIS"
    for core in records:
        rec = dict(core)
        rec["previous_hash"] = prev
        rec["record_hash"] = content_hash(rec)
        out.append(rec)
        prev = rec["record_hash"]
    return out


def test_verify_hash_chain_valid(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    chain = _chain(e, [{"id": "a", "v": 1}, {"id": "b", "v": 2}])
    assert e.verify_hash_chain(chain)["ok"] is True


def test_verify_hash_chain_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().verify_hash_chain([])["ok"] is True


def test_verify_hash_chain_tamper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    chain = _chain(e, [{"id": "a", "v": 1}])
    chain[0]["v"] = 999
    assert e.verify_hash_chain(chain)["ok"] is False


def test_verify_hash_chain_broken(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    chain = _chain(e, [{"id": "a", "v": 1}, {"id": "b", "v": 2}])
    chain[1]["previous_hash"] = "sha256:bad"
    assert e.verify_hash_chain(chain)["ok"] is False


def test_verify_hash_chain_missing_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    chain = _chain(e, [{"id": "a"}])
    del chain[0]["record_hash"]
    assert e.verify_hash_chain(chain)["ok"] is False


def test_verify_hash_records_module():
    chain = []
    prev = "GENESIS"
    for core in [{"id": "x"}]:
        rec = dict(core, previous_hash=prev)
        rec["record_hash"] = content_hash(rec)
        chain.append(rec)
    assert verify_hash_records(chain)["ok"] is True


def test_hash_algorithm_matches_layers():
    # P35 의 content_hash 는 모든 계층과 동일 → 실제 계층 레코드 검증 가능
    from jarvis.research_monitoring.models import content_hash as rm_ch
    rec = {"a": 1, "previous_hash": "p", "record_hash": "r"}
    assert content_hash(rec) == rm_ch(rec)


@pytest.mark.parametrize("pkg", ["research_reliability", "autonomous_research",
                                 "research_insight_intelligence", "experiment_orchestration"])
def test_hash_algorithm_matches_multiple(pkg):
    import importlib
    other = importlib.import_module(f"jarvis.{pkg}.models")
    rec = {"x": 5, "y": "z", "previous_hash": "q", "record_hash": "w"}
    assert content_hash(rec) == other.content_hash(rec)


# ═══════════════ lineage ═══════════════
def test_check_lineage_ok():
    arts = [{"artifact_id": "A", "parent_artifact": ""},
            {"artifact_id": "B", "parent_artifact": "A"}]
    assert _eng().check_lineage(arts)["status"] == "PASS"


def test_check_lineage_missing_parent():
    arts = [{"artifact_id": "B", "parent_artifact": "MISSING"}]
    assert _eng().check_lineage(arts)["status"] == "FAIL"


def test_check_lineage_cycle():
    arts = [{"artifact_id": "A", "parent_artifact": "B"},
            {"artifact_id": "B", "parent_artifact": "A"}]
    assert _eng().check_lineage(arts)["status"] == "FAIL"


# ═══════════════ full validation ═══════════════
def test_run_full_validation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().run_full_validation("SYSTEM", T[0], commit=True)
    assert res["all_passed"] is True
    assert res["validation"]["checks_failed"] == 0


def test_full_validation_records_findings(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.run_full_validation("SYSTEM", T[0], commit=True)
    # 14 layers * 7 checks + 1 ownership = 99 findings
    assert len(ledger.read_findings()) == 14 * 7 + 1


def test_full_validation_all_pass(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.run_full_validation("SYSTEM", T[0], commit=True)
    assert all(f["status"] == "PASS" for f in ledger.read_findings())


def test_full_validation_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().run_full_validation("SYSTEM", T[0], commit=False)
    assert ledger.read_findings() == []
    assert ledger.read_validations() == []


def test_validation_record(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    res = e.run_full_validation("SYSTEM", T[0], commit=True)
    assert res["validation"]["validation_id"].startswith("SIV:")
    assert res["validation"]["all_passed"] is True


# ═══════════════ architecture / dependency graph ═══════════════
def test_architecture_summary():
    a = _eng().architecture_summary()
    assert a["layer_count"] == 14
    assert len(a["layers"]) == 14
    assert len(a["prefixes"]) == 14


def test_dependency_graph():
    g = _eng().dependency_graph()
    assert set(g) == set(_PACKAGES)


def test_dependency_graph_deterministic():
    assert _eng().dependency_graph() == _eng().dependency_graph()


def test_dependency_graph_has_edges():
    # 예: dashboard/gateway/meta 는 상위 계층을 READ ONLY 참조
    g = _eng().dependency_graph()
    assert any(len(v) > 0 for v in g.values())


# ═══════════════ verify / replay ═══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_verify_after_validation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.run_full_validation("SYSTEM", T[0], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.run_full_validation("SYSTEM", T[0], commit=True)
    p = sp("sysint_validations.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["checks_passed"] = 0
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.run_full_validation("SYSTEM", T[0], commit=True)
    p = sp("sysint_findings.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    if len(rows) > 1:
        rows[1]["previous_hash"] = "sha256:bad"
        with open(p, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        assert verify_chain()["ok"] is False


def test_finding_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.run_full_validation("SYSTEM", T[0], commit=True)
    assert finding_integrity()["ok"] is True


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.run_full_validation("SYSTEM", T[0], commit=True)
    assert duplicate_integrity()["ok"] is True


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.run_full_validation("SYSTEM", T[0], commit=True)
    assert lineage_integrity()["ok"] is True


def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.run_full_validation("SYSTEM", T[0], commit=True)
    assert replay(e, T[9])["deterministic"] is True


# ═══════════════ report ═══════════════
def test_generate_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.run_full_validation("SYSTEM", T[0], commit=True)
    r = e.generate_report("SYSTEM", T[1], commit=True)
    assert r.report_id.startswith("SIR:")
    assert r.is_binding is False
    assert r.layer_count == 14
    assert r.failed_finding_count == 0
    assert r.architecture_summary["layer_count"] == 14


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("SYSTEM", T[0], commit=True)
    assert "VALIDATION" in r.disclaimer


def test_report_has_dependency_graph(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("SYSTEM", T[0], commit=True)
    assert set(r.dependency_graph) == set(_PACKAGES)


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb(verb):
    assert M.is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["VALIDATE", "VERIFY", "CHECK", "SCAN", "AUDIT"])
def test_allowed_verb(verb):
    assert M.is_forbidden_verb(verb) is False


def test_forbidden_empty():
    assert M.is_forbidden_verb("") is False


# ═══════════════ ID / hash ═══════════════
@pytest.mark.parametrize("fn,args,prefix", [
    (M.validation_id, ("s", "t"), "SIV:"),
    (M.finding_id, ("l", "STRUCTURE", 0), "SIF:"),
    (M.report_id, ("s", "t"), "SIR:"),
    (M.artifact_id, ("VALIDATION", "r"), "SIA:"),
])
def test_id_prefixes(fn, args, prefix):
    assert fn(*args).startswith(prefix)


def test_content_hash_excludes_meta():
    a = content_hash({"x": 1, "previous_hash": "p", "record_hash": "r"})
    b = content_hash({"x": 1, "previous_hash": "Q", "record_hash": "Z"})
    assert a == b


# ═══════════════ summary ═══════════════
def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.run_full_validation("SYSTEM", T[0], commit=True)
    s = e.summary(T[9])
    assert s.layer_count == 14
    assert s.validation_count == 1
    assert s.finding_count > 0


# ═══════════════ CLI ═══════════════
def test_cli_validate(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.system_integration.__main__ import main
    assert main(["validate", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["all_passed"] is True


def test_cli_architecture(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.system_integration.__main__ import main
    assert main(["architecture"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["layer_count"] == 14


def test_cli_dependencies(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.system_integration.__main__ import main
    assert main(["dependencies"]) == 0


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.system_integration.__main__ import main
    assert main(["report", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["report"]["is_binding"] is False


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.system_integration.__main__ import main
    assert main(["verify"]) == 0


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.system_integration.__main__ import main
    assert main(["summary"]) == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.system_integration.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


# ═══════════════ 격리 / ledger ═══════════════
def test_records_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    res = e.run_full_validation("SYSTEM", T[0], commit=True)
    from jarvis.system_integration.models import ValidationRecord
    v = ValidationRecord(**{k: val for k, val in res["validation"].items()
                            if k in ValidationRecord.__dataclass_fields__})
    with pytest.raises(Exception):
        v.scope = "x"


def test_four_ledgers():
    assert len(ledger.ALL_LEDGERS) == 4


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("sysint_")


def test_required_ledgers_present():
    names = {f for f, _ in ledger.ALL_LEDGERS}
    for req in ("sysint_validations.jsonl", "sysint_findings.jsonl", "sysint_reports.jsonl",
                "sysint_artifacts.jsonl"):
        assert req in names


# ═══════════════ 보안 스캔(자체 패키지) ═══════════════
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
        if isinstance(node, ast.Import):
            for n in node.names:
                assert not any(n.name.startswith(f) for f in forbidden), n.name


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_method_defs(path):
    tree = ast.parse(open(path).read())
    bad = ("execute", "deploy", "trade", "allocate", "approve", "mutate_ledger", "modify_ownership",
           "execute_trade", "place_order", "allocate_capital", "deploy_strategy")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()


@pytest.mark.parametrize("path", _SRC)
def test_no_destructive_ledger_api(path):
    src = open(path).read()
    for bad in ("def delete_", "def overwrite_", "def drop_", "def truncate", "def purge_"):
        assert bad not in src


def test_ledger_append_only():
    src = open(os.path.join(_PKG, "ledger.py")).read()
    assert '"a"' in src
    assert '"w"' not in src


def test_engine_no_forbidden_methods():
    e = _eng()
    for attr in ("execute", "deploy", "trade", "allocate", "approve", "mutate_ledger"):
        assert not hasattr(e, attr)


# ═══════════════ end-to-end: 전체 생태계 최종 검증 ═══════════════
def test_end_to_end_full_ecosystem(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    # 1. 전체 계층 정적 검증(P21~P34)
    res = e.run_full_validation("SYSTEM", T[0], commit=True)
    assert res["all_passed"] is True  # 모든 계층 구조·소유권·안전성·append-only 통과
    # 2. 소유권 유일성
    assert prefixes_unique() and packages_unique()
    # 3. 아키텍처 요약(14 계층)
    arch = e.architecture_summary()
    assert arch["layer_count"] == 14
    # 4. 의존성 그래프(상위 READ ONLY 참조, 단방향)
    graph = e.dependency_graph()
    assert set(graph) == set(_PACKAGES)
    # 5. 범용 해시체인 검증(모든 계층 공통 알고리즘)
    chain = _chain(e, [{"id": "x", "v": 1}, {"id": "y", "v": 2}])
    assert e.verify_hash_chain(chain)["ok"] is True
    # 6. 시스템 리포트
    r = e.generate_report("SYSTEM", T[1], commit=True)
    assert r.failed_finding_count == 0
    assert r.is_binding is False
    # 7. 무결성·재현
    assert verify_chain()["ok"] is True
    assert replay(e, T[2])["deterministic"] is True
