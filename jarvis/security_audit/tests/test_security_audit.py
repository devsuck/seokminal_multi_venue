"""P38 security_audit 테스트 — 원장 보안(해시체인·변조탐지·재현)·아키텍처 보안(금지import·소유권)·
런타임 보안(불안전실행·숨은배포·우발적거래)·엔진 미노출. AUDIT ≠ EXECUTION."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.security_audit import ledger
from jarvis.security_audit import models as M
from jarvis.security_audit.engine import SecurityAuditEngine
from jarvis.security_audit.models import (
    AUDIT_DIMENSIONS,
    AUDIT_TARGETS,
    FORBIDDEN_ENGINE_METHODS,
    FORBIDDEN_VERBS,
    content_hash,
    verify_hash_records,
)
from jarvis.security_audit.verify import (
    duplicate_integrity,
    finding_integrity,
    lineage_integrity,
    replay,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.security_audit.ledger.state_path", sp)
    return sp


def _eng():
    return SecurityAuditEngine()


def _chain(cores):
    out = []
    prev = "GENESIS"
    for core in cores:
        rec = dict(core, previous_hash=prev)
        rec["record_hash"] = content_hash(rec)
        out.append(rec)
        prev = rec["record_hash"]
    return out


# ═══════════════ audit targets ═══════════════
def test_audit_targets_count():
    assert len(AUDIT_TARGETS) == 18  # 14 registry + 4 finalization


def test_audit_dimensions():
    assert set(AUDIT_DIMENSIONS) == {"LEDGER_SECURITY", "ARCHITECTURE_SECURITY", "RUNTIME_SECURITY"}


@pytest.mark.parametrize("m", FORBIDDEN_ENGINE_METHODS)
def test_forbidden_engine_methods(m):
    assert m in ("execute", "trade", "deploy", "allocate", "approve")


# ═══════════════ 원장 보안 ═══════════════
def test_audit_hash_chain_valid():
    chain = _chain([{"id": "a"}, {"id": "b"}])
    r = _eng().audit_hash_chain(chain)
    assert r["status"] == "PASS"
    assert r["dimension"] == "LEDGER_SECURITY"


def test_audit_hash_chain_broken():
    chain = _chain([{"id": "a"}, {"id": "b"}])
    chain[1]["previous_hash"] = "sha256:bad"
    assert _eng().audit_hash_chain(chain)["status"] == "FAIL"


def test_audit_tamper_detection():
    chain = _chain([{"id": "a", "v": 1}, {"id": "b", "v": 2}])
    r = _eng().audit_tamper_detection(chain)
    assert r["status"] == "PASS"  # 변조가 탐지됨


def test_audit_tamper_empty():
    assert _eng().audit_tamper_detection([])["status"] == "PASS"


def test_verify_hash_records_valid():
    chain = _chain([{"id": "x"}])
    assert verify_hash_records(chain)["ok"] is True


def test_verify_hash_records_tamper():
    chain = _chain([{"id": "x", "v": 1}])
    chain[0]["v"] = 2
    assert verify_hash_records(chain)["ok"] is False


# ═══════════════ 아키텍처 보안: 금지 import (전 대상) ═══════════════
@pytest.mark.parametrize("target", AUDIT_TARGETS)
def test_forbidden_imports_all_targets(target):
    r = _eng().audit_forbidden_imports(target)
    assert r["status"] == "PASS", r["detail"]


@pytest.mark.parametrize("target", AUDIT_TARGETS)
def test_model_leak_all_targets(target):
    r = _eng().audit_model_leak(target)
    assert r["status"] == "PASS", r["detail"]


def test_ownership_boundary():
    assert _eng().audit_ownership_boundary()["status"] == "PASS"


# ═══════════════ 런타임 보안: 불안전 실행/배포/거래 (전 대상) ═══════════════
@pytest.mark.parametrize("target", AUDIT_TARGETS)
def test_unsafe_execution_all_targets(target):
    r = _eng().audit_unsafe_execution(target)
    assert r["status"] == "PASS", r["detail"]


@pytest.mark.parametrize("target", AUDIT_TARGETS)
def test_hidden_deployment_all_targets(target):
    r = _eng().audit_hidden_deployment(target)
    assert r["status"] == "PASS", r["detail"]


@pytest.mark.parametrize("target", AUDIT_TARGETS)
def test_accidental_trading_all_targets(target):
    r = _eng().audit_accidental_trading(target)
    assert r["status"] == "PASS", r["detail"]


@pytest.mark.parametrize("target", AUDIT_TARGETS)
def test_engine_surface_all_targets(target):
    r = _eng().audit_engine_surface(target)
    assert r["status"] == "PASS", r["detail"]


# ═══════════════ 엔진 미노출(런타임 인스턴스) ═══════════════
def test_audit_engine_no_forbidden_methods():
    e = _eng()
    for attr in FORBIDDEN_ENGINE_METHODS:
        assert not hasattr(e, attr)


@pytest.mark.parametrize("target", AUDIT_TARGETS)
def test_target_engine_no_forbidden_methods_runtime(target):
    import importlib
    try:
        mod = importlib.import_module(f"jarvis.{target}.engine")
    except ModuleNotFoundError:
        return  # 일부 파이널라이제이션 계층은 engine 없음
    engine_classes = [getattr(mod, n) for n in dir(mod)
                      if n.endswith("Engine") and isinstance(getattr(mod, n), type)]
    for cls in engine_classes:
        for m in FORBIDDEN_ENGINE_METHODS:
            assert not hasattr(cls, m), f"{cls.__name__}.{m}"


# ═══════════════ 전체 감사 ═══════════════
def test_run_full_audit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().run_full_audit("SYSTEM", T[0], commit=True)
    assert res["all_secure"] is True
    assert res["audit"]["checks_failed"] == 0


def test_full_audit_records_findings(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.run_full_audit("SYSTEM", T[0], commit=True)
    # 3 (ledger/ownership) + 18 targets * 6 checks
    assert len(ledger.read_findings()) == 3 + 18 * 6


def test_full_audit_all_pass(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.run_full_audit("SYSTEM", T[0], commit=True)
    assert all(f["status"] == "PASS" for f in ledger.read_findings())


def test_full_audit_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().run_full_audit("SYSTEM", T[0], commit=False)
    assert ledger.read_findings() == []
    assert ledger.read_audits() == []


def test_audit_record(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().run_full_audit("SYSTEM", T[0], commit=True)
    assert res["audit"]["audit_id"].startswith("SCA:")
    assert res["audit"]["all_secure"] is True


def test_audit_targets_field(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().run_full_audit("SYSTEM", T[0], commit=True)
    assert res["audit"]["targets"] == 18


# ═══════════════ verify / replay ═══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_verify_after_audit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.run_full_audit("SYSTEM", T[0], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.run_full_audit("SYSTEM", T[0], commit=True)
    p = sp("secaud_audits.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["all_secure"] = False
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.run_full_audit("SYSTEM", T[0], commit=True)
    p = sp("secaud_findings.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:bad"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_finding_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.run_full_audit("SYSTEM", T[0], commit=True)
    assert finding_integrity()["ok"] is True


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.run_full_audit("SYSTEM", T[0], commit=True)
    assert duplicate_integrity()["ok"] is True


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.run_full_audit("SYSTEM", T[0], commit=True)
    assert lineage_integrity()["ok"] is True


def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    assert replay(e, T[9])["deterministic"] is True


# ═══════════════ report ═══════════════
def test_generate_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.run_full_audit("SYSTEM", T[0], commit=True)
    r = e.generate_report("SYSTEM", T[1], commit=True)
    assert r.report_id.startswith("SCR:")
    assert r.is_binding is False
    assert r.target_count == 18
    assert r.failed_finding_count == 0
    assert set(r.dimension_distribution) <= set(AUDIT_DIMENSIONS)


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("SYSTEM", T[0], commit=True)
    assert "EXECUTION" in r.disclaimer


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb(verb):
    assert M.is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["AUDIT", "SCAN", "VERIFY", "CHECK", "VALIDATE"])
def test_allowed_verb(verb):
    assert M.is_forbidden_verb(verb) is False


# ═══════════════ ID / hash ═══════════════
@pytest.mark.parametrize("fn,args,prefix", [
    (M.audit_id, ("s", "t"), "SCA:"),
    (M.finding_id, ("t", "LEDGER_SECURITY", 0), "SCF:"),
    (M.report_id, ("s", "t"), "SCR:"),
    (M.artifact_id, ("AUDIT", "r"), "SCT:"),
])
def test_id_prefixes(fn, args, prefix):
    assert fn(*args).startswith(prefix)


def test_content_hash_excludes_meta():
    a = content_hash({"x": 1, "previous_hash": "p", "record_hash": "r"})
    b = content_hash({"x": 1, "previous_hash": "Q", "record_hash": "Z"})
    assert a == b


# ═══════════════ summary ═══════════════
def test_summary(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.run_full_audit("SYSTEM", T[0], commit=True)
    s = e.summary(T[9])
    assert s.target_count == 18
    assert s.audit_count == 1
    assert s.finding_count > 0


# ═══════════════ CLI ═══════════════
def test_cli_audit(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.security_audit.__main__ import main
    assert main(["audit", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["all_secure"] is True


def test_cli_targets(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.security_audit.__main__ import main
    assert main(["targets"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["count"] == 18


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.security_audit.__main__ import main
    assert main(["report", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["report"]["is_binding"] is False


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.security_audit.__main__ import main
    assert main(["verify"]) == 0


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.security_audit.__main__ import main
    assert main(["summary"]) == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.security_audit.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


# ═══════════════ 격리 / ledger ═══════════════
def test_four_ledgers():
    assert len(ledger.ALL_LEDGERS) == 4


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("secaud_")


# ═══════════════ 자체 안전성 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]


@pytest.mark.parametrize("path", _SRC)
def test_self_no_forbidden_imports(path):
    forbidden = ("jarvis.execution", "jarvis.broker", "jarvis.live_trading",
                 "jarvis.portfolio_execution", "jarvis.live_portfolio")
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(f) for f in forbidden), node.module


@pytest.mark.parametrize("path", _SRC)
def test_self_no_forbidden_method_defs(path):
    tree = ast.parse(open(path).read())
    bad = ("execute", "trade", "deploy", "allocate", "approve")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC)
def test_self_no_model_id_leak(path):
    assert ("claude" + "-opus") not in open(path).read().lower()


def test_self_ledger_append_only():
    src = open(os.path.join(_PKG, "ledger.py")).read()
    assert '"a"' in src
    assert '"w"' not in src


# ═══════════════ end-to-end: 전체 생태계 보안 감사 ═══════════════
def test_end_to_end_security_audit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    # 1. 전체 감사(원장·아키텍처·런타임) — 모든 대상 안전
    res = e.run_full_audit("SYSTEM", T[0], commit=True)
    assert res["all_secure"] is True
    # 2. 변조 탐지 동작(음성 대조)
    chain = _chain([{"id": "a", "v": 1}])
    chain[0]["v"] = 999
    assert verify_hash_records(chain)["ok"] is False
    # 3. 모든 대상 엔진 미노출(런타임)
    import importlib
    for target in AUDIT_TARGETS:
        try:
            mod = importlib.import_module(f"jarvis.{target}.engine")
        except ModuleNotFoundError:
            continue
        for n in dir(mod):
            obj = getattr(mod, n)
            if isinstance(obj, type) and n.endswith("Engine"):
                for m in FORBIDDEN_ENGINE_METHODS:
                    assert not hasattr(obj, m)
    # 4. 보안 리포트 + 무결성 + 재현
    r = e.generate_report("SYSTEM", T[1], commit=True)
    assert r.failed_finding_count == 0
    assert verify_chain()["ok"] is True
    assert replay(e, T[2])["deterministic"] is True
