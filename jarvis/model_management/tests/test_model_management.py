"""P43 model_management 테스트 — 모델 생애주기·버전·검증·성능·메타·비교·재현·
verify·replay·CLI·보안·READ ONLY 상위. MANAGED ≠ DEPLOYED."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.model_management import ledger
from jarvis.model_management import models as M
from jarvis.model_management.engine import ModelManagementEngine
from jarvis.model_management.models import (
    FORBIDDEN_VERBS,
    MODEL_STATES,
    MODEL_TYPES,
    VALIDATION_CHECKS,
    M_ARCHIVED,
    M_AVAILABLE,
    M_REGISTERED,
    M_VALIDATED,
    IllegalModelTransition,
    UnknownEntityError,
    can_model_transition,
    content_hash,
    metric_delta,
)
from jarvis.model_management.verify import (
    duplicate_integrity,
    lineage_integrity,
    model_lifecycle_integrity,
    replay,
    validation_integrity,
    verify_chain,
    version_lineage_integrity,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.model_management.ledger.state_path", sp)
    return sp


def _eng():
    return ModelManagementEngine()


def _mdl(e, name="regime-classifier", mtype="CLASSIFIER", now=T[0]):
    return e.register_model(name, mtype, now, commit=True).model_id


# ═══════════════ model lifecycle ═══════════════
def test_register_model(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().register_model("m", "REGRESSOR", T[0], commit=True)
    assert ev.to_state == M_REGISTERED
    assert ev.model_id.startswith("MMM:")
    assert ev.model_event_id.startswith("MME:")


def test_model_bad_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().register_model("m", "NOPE", now=T[0], commit=True)


def test_model_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mdl = _mdl(e)
    e.mark_validated(mdl, now=T[1], commit=True)
    e.mark_available(mdl, now=T[2], commit=True)
    e.archive_model(mdl, now=T[3], commit=True)
    assert e.model_state(mdl) == M_ARCHIVED


def test_model_no_skip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mdl = _mdl(e)
    with pytest.raises(IllegalModelTransition):
        e.mark_available(mdl, now=T[1], commit=True)  # REGISTERED→AVAILABLE skip


def test_model_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.register_model("m", "RANKER", now=T[0], commit=True).model_id
    b = e.register_model("m", "RANKER", now=T[1], commit=True).model_id
    assert a == b
    assert len(ledger.model_events(a)) == 1


def test_model_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().mark_validated("MMM:nope", now=T[1], commit=True)


def test_models_in_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mdl = _mdl(e)
    e.mark_validated(mdl, now=T[1], commit=True)
    assert mdl in e.models_in_state(M_VALIDATED)


@pytest.mark.parametrize("frm,to,ok", [
    (M_REGISTERED, M_VALIDATED, True), (M_REGISTERED, M_AVAILABLE, False),
    (M_VALIDATED, M_AVAILABLE, True), (M_AVAILABLE, M_ARCHIVED, True),
    (M_ARCHIVED, M_VALIDATED, False), (M_REGISTERED, M_ARCHIVED, False),
])
def test_model_transition_matrix(frm, to, ok):
    assert can_model_transition(frm, to) is ok


@pytest.mark.parametrize("s", MODEL_STATES)
def test_model_states(s):
    assert s in MODEL_STATES


@pytest.mark.parametrize("mt", MODEL_TYPES)
def test_model_types(tmp_path, monkeypatch, mt):
    _iso(tmp_path, monkeypatch)
    ev = _eng().register_model(f"m-{mt}", mt, now=T[0], commit=True)
    assert ev.model_type == mt


# ═══════════════ version ═══════════════
def test_create_version(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mdl = _mdl(e)
    v = e.create_version(mdl, "v1", {"weights": [1, 2]}, "sklearn", T[1], commit=True)
    assert v.version_id.startswith("MMV:")
    assert v.content_hash.startswith("sha256:")
    assert v.framework == "sklearn"


def test_version_lineage_parent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mdl = _mdl(e)
    v1 = e.create_version(mdl, "v1", {"x": 1}, now=T[1], commit=True)
    v2 = e.create_version(mdl, "v2", {"x": 2}, now=T[2], commit=True)
    assert v2.parent_version == v1.version_id


def test_version_unknown_model(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().create_version("MMM:nope", "v1", now=T[0], commit=True)


def test_version_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mdl = _mdl(e)
    a = e.create_version(mdl, "v1", {"x": 1}, now=T[1], commit=True).version_id
    b = e.create_version(mdl, "v1", {"x": 9}, now=T[2], commit=True).version_id
    assert a == b
    assert len(ledger.versions_for(mdl)) == 1


# ═══════════════ validation ═══════════════
def test_validate_model(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mdl = _mdl(e)
    v = e.validate_model(mdl, "ACCURACY", True, 0.92, "oos test", "", T[1], commit=True)
    assert v.validation_id.startswith("MML:")
    assert v.passed is True


def test_validate_advances_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mdl = _mdl(e)
    e.validate_model(mdl, "ROBUSTNESS", True, 0.9, now=T[1], commit=True)
    assert e.model_state(mdl) == M_VALIDATED


def test_validate_bad_check(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mdl = _mdl(e)
    with pytest.raises(ValueError):
        e.validate_model(mdl, "NOPE", now=T[1], commit=True)


def test_validate_clamped(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mdl = _mdl(e)
    v = e.validate_model(mdl, "CALIBRATION", True, 5.0, now=T[1], commit=True)
    assert v.score == 1.0


@pytest.mark.parametrize("c", VALIDATION_CHECKS)
def test_validation_checks(c):
    assert c in VALIDATION_CHECKS


# ═══════════════ performance ═══════════════
def test_record_performance(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mdl = _mdl(e)
    p = e.record_performance(mdl, "auc", 0.87, "dinf:v1", "", T[1], commit=True)
    assert p.performance_id.startswith("MMP:")
    assert p.value == 0.87


def test_performance_unknown_model(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().record_performance("MMM:nope", "m", 1, now=T[0], commit=True)


def test_performance_history(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mdl = _mdl(e)
    e.record_performance(mdl, "auc", 0.80, now=T[1], commit=True)
    e.record_performance(mdl, "auc", 0.85, now=T[2], commit=True)
    assert len(ledger.performance_for(mdl)) == 2


# ═══════════════ metadata ═══════════════
def test_record_metadata(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mdl = _mdl(e)
    m = e.record_metadata(mdl, "author", "quant-team", T[1], commit=True)
    assert m.metadata_id.startswith("MMD:")
    assert m.value == "quant-team"


def test_metadata_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mdl = _mdl(e)
    a = e.record_metadata(mdl, "k", "1", T[1], commit=True).metadata_id
    b = e.record_metadata(mdl, "k", "2", T[2], commit=True).metadata_id
    assert a == b


# ═══════════════ compare ═══════════════
def test_compare_models(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _mdl(e, "a")
    b = _mdl(e, "b")
    e.record_performance(a, "auc", 0.80, now=T[1], commit=True)
    e.record_performance(b, "auc", 0.90, now=T[2], commit=True)
    c = e.compare_models(a, b)
    assert c["metric_deltas"]["auc"] == 0.1


def test_compare_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _mdl(e)
    with pytest.raises(UnknownEntityError):
        e.compare_models(a, "MMM:nope")


def test_compare_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _mdl(e, "a")
    b = _mdl(e, "b")
    e.record_performance(a, "m", 1.0, now=T[1], commit=True)
    e.record_performance(b, "m", 2.0, now=T[2], commit=True)
    assert e.compare_models(a, b) == e.compare_models(a, b)


def test_metric_delta_helper():
    assert metric_delta(1.0, 1.5) == 0.5
    assert metric_delta("x", 1) == 0.0


# ═══════════════ integration READ ONLY ═══════════════
def test_source_layers_present():
    for k in ("experiment_tracking", "data_infrastructure", "model_governance"):
        assert k in ledger.SOURCE_LAYERS


def test_source_count_readonly(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("expt_experiments.jsonl")
    with open(p, "w") as f:
        for i in range(3):
            f.write(json.dumps({"experiment_id": f"e{i}"}) + "\n")
    before = open(p).read()
    assert ledger.source_count("experiment_tracking") == 3
    assert open(p).read() == before


# ═══════════════ verify ═══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_verify_after_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mdl = _mdl(e)
    e.create_version(mdl, "v1", {"x": 1}, now=T[1], commit=True)
    e.validate_model(mdl, "ACCURACY", True, 0.9, now=T[2], commit=True)
    e.record_performance(mdl, "auc", 0.85, now=T[3], commit=True)
    e.record_metadata(mdl, "k", "v", T[4], commit=True)
    e.mark_available(mdl, now=T[5], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _mdl(e)
    p = sp("mdl_models.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["name"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    mdl = _mdl(e)
    e.create_version(mdl, "v1", {"x": 1}, now=T[1], commit=True)
    e.create_version(mdl, "v2", {"x": 2}, now=T[2], commit=True)
    p = sp("mdl_versions.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:bad"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _mdl(e)
    p = sp("mdl_models.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    with open(p, "a") as f:
        f.write(json.dumps(rows[0]) + "\n")
    assert verify_chain()["ok"] is False


def test_model_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mdl = _mdl(e)
    e.mark_validated(mdl, now=T[1], commit=True)
    assert model_lifecycle_integrity()["ok"] is True


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mdl(e, "a")
    _mdl(e, "b")
    assert duplicate_integrity()["ok"] is True


def test_version_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mdl = _mdl(e)
    e.create_version(mdl, "v1", {"x": 1}, now=T[1], commit=True)
    e.create_version(mdl, "v2", {"x": 2}, now=T[2], commit=True)
    assert version_lineage_integrity()["ok"] is True


def test_validation_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mdl = _mdl(e)
    e.validate_model(mdl, "STABILITY", True, 0.9, now=T[1], commit=True)
    assert validation_integrity()["ok"] is True


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mdl = _mdl(e)
    e.create_version(mdl, "v1", {"x": 1}, now=T[1], commit=True)
    assert lineage_integrity()["ok"] is True


# ═══════════════ replay ═══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mdl = _mdl(e)
    e.create_version(mdl, "v1", {"x": 1}, now=T[1], commit=True)
    assert replay(e, T[9])["deterministic"] is True


# ═══════════════ report ═══════════════
def test_generate_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mdl = _mdl(e, mtype="FORECASTER")
    e.validate_model(mdl, "ACCURACY", True, 0.9, now=T[1], commit=True)
    e.mark_available(mdl, now=T[2], commit=True)
    r = e.generate_report("SYSTEM", T[3], commit=True)
    assert r.report_id.startswith("MMR:")
    assert r.is_binding is False
    assert r.model_count == 1
    assert r.available_model_count == 1
    assert r.type_distribution.get("FORECASTER") == 1


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("SYSTEM", T[0], commit=True)
    assert "DEPLOYED" in r.disclaimer


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb(verb):
    assert M.is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["REGISTER", "VALIDATE", "COMPARE", "ARCHIVE", "RECORD"])
def test_allowed_verb(verb):
    assert M.is_forbidden_verb(verb) is False


def test_forbidden_deploy_model():
    assert "DEPLOY_MODEL" in FORBIDDEN_VERBS
    assert "SERVE_LIVE" in FORBIDDEN_VERBS


def test_forbidden_empty():
    assert M.is_forbidden_verb("") is False


# ═══════════════ ID / hash ═══════════════
@pytest.mark.parametrize("fn,args,prefix", [
    (M.model_id, ("n",), "MMM:"),
    (M.model_event_id, ("m", "REGISTERED", 0), "MME:"),
    (M.version_id, ("m", "v1"), "MMV:"),
    (M.validation_id, ("m", "ACCURACY", 0), "MML:"),
    (M.performance_id, ("m", "auc", 0), "MMP:"),
    (M.metadata_id, ("m", "k"), "MMD:"),
    (M.report_id, ("s", "t"), "MMR:"),
    (M.artifact_id, ("MODEL", "r"), "MMA:"),
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
    mdl = _mdl(e)
    e.create_version(mdl, "v1", {"x": 1}, now=T[1], commit=True)
    s = e.summary(T[9])
    assert s.model_count == 1
    assert s.version_count == 1


def test_list_models(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mdl(e, "a")
    _mdl(e, "b")
    assert len(e.list_models()) == 2


# ═══════════════ CLI ═══════════════
def test_cli_model(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.model_management.__main__ import main
    assert main(["model", "--name", "m", "--type", "CLASSIFIER", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["model"]["to_state"] == "REGISTERED"


def test_cli_version_and_validate(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.model_management.__main__ import main
    main(["model", "--name", "m", "--type", "REGRESSOR", "--commit"])
    mdl = json.loads(capsys.readouterr().out)["model"]["model_id"]
    assert main(["version", "--model", mdl, "--version", "v1", "--framework", "torch",
                 "--commit"]) == 0
    capsys.readouterr()
    assert main(["validate", "--model", mdl, "--check", "ACCURACY", "--passed", "--score", "0.9",
                 "--commit"]) == 0


def test_cli_perf(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.model_management.__main__ import main
    main(["model", "--name", "m", "--type", "RANKER", "--commit"])
    mdl = json.loads(capsys.readouterr().out)["model"]["model_id"]
    assert main(["perf", "--model", mdl, "--metric", "ndcg", "--value", "0.7", "--commit"]) == 0


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.model_management.__main__ import main
    assert main(["report", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["report"]["is_binding"] is False


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.model_management.__main__ import main
    assert main(["verify"]) == 0


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.model_management.__main__ import main
    assert main(["summary"]) == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.model_management.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


# ═══════════════ 격리 / ledger ═══════════════
def test_records_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().register_model("m", "CLASSIFIER", now=T[0], commit=True)
    with pytest.raises(Exception):
        ev.name = "x"


def test_seven_ledgers():
    assert len(ledger.ALL_LEDGERS) == 7


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("mdl_")


def test_required_ledgers_present():
    names = {f for f, _ in ledger.ALL_LEDGERS}
    for req in ("mdl_models.jsonl", "mdl_versions.jsonl", "mdl_validations.jsonl",
                "mdl_performance.jsonl", "mdl_metadata.jsonl", "mdl_reports.jsonl",
                "mdl_artifacts.jsonl"):
        assert req in names


# ═══════════════ 보안 스캔 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN_IMPORTS = (
    "jarvis.execution", "jarvis.broker", "jarvis.live_trading", "jarvis.portfolio_execution",
    "jarvis.live_portfolio", "jarvis.portfolio", "jarvis.order", "jarvis.deployment", "jarvis.live",
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
    bad = ("execute", "trade", "deploy", "allocate", "approve", "deploy_model", "serve_live",
           "execute_trade", "place_order", "allocate_capital", "deploy_strategy", "activate_live")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert ("claude" + "-opus") not in open(path).read().lower()


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
    for attr in ("execute", "trade", "deploy", "allocate", "approve"):
        assert not hasattr(e, attr)


# ═══════════════ end-to-end ═══════════════
def test_end_to_end(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("expt_experiments.jsonl"), "w") as f:
        f.write(json.dumps({"experiment_id": "xte:1"}) + "\n")
    e = _eng()
    # 모델 등록 → 버전 → 검증(→VALIDATED) → 성능 → 메타 → 가용
    mdl = e.register_model("regime-forecaster", "FORECASTER", T[0], commit=True).model_id
    v1 = e.create_version(mdl, "v1", {"weights": list(range(100))}, "torch", T[1], commit=True)
    v2 = e.create_version(mdl, "v2", {"weights": list(range(110))}, "torch", T[2], commit=True)
    assert v2.parent_version == v1.version_id
    e.validate_model(mdl, "ACCURACY", True, 0.91, "oos", v2.version_id, T[3], commit=True)
    e.validate_model(mdl, "LEAKAGE", True, 1.0, "no leak", v2.version_id, T[4], commit=True)
    assert e.model_state(mdl) == M_VALIDATED
    e.record_performance(mdl, "rmse", 0.045, "dinf:test", v2.version_id, T[5], commit=True)
    e.record_metadata(mdl, "owner", "quant-research", T[6], commit=True)
    e.mark_available(mdl, now=T[7], commit=True)
    assert e.model_state(mdl) == M_AVAILABLE  # 연구용 가용 — 라이브 아님
    # 두번째 모델 + 비교
    mdl2 = e.register_model("regime-forecaster-v2", "FORECASTER", T[8], commit=True).model_id
    e.record_performance(mdl2, "rmse", 0.038, now=T[9], commit=True)
    c = e.compare_models(mdl, mdl2)
    assert "rmse" in c["metric_deltas"]
    r = e.generate_report("SYSTEM", T[10], commit=True)
    assert r.available_model_count == 1
    assert r.version_count == 2
    assert r.is_binding is False  # MANAGED ≠ DEPLOYED
    assert open(sp("expt_experiments.jsonl")).read()  # 상위 원장 불변
    assert verify_chain()["ok"] is True
    assert replay(e, T[11])["deterministic"] is True
