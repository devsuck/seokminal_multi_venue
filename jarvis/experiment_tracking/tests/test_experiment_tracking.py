"""P42 experiment_tracking 테스트 — 실험·실행·파라미터·결과·아티팩트·비교·요약·재현·
verify·replay·CLI·보안·READ ONLY 상위. TRACK ≠ EXECUTE."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.experiment_tracking import ledger
from jarvis.experiment_tracking import models as M
from jarvis.experiment_tracking.engine import ExperimentTrackingEngine
from jarvis.experiment_tracking.models import (
    ARTIFACT_TYPES,
    FORBIDDEN_VERBS,
    RUN_STATUSES,
    UnknownEntityError,
    content_hash,
    metric_delta,
)
from jarvis.experiment_tracking.verify import (
    duplicate_integrity,
    lineage_integrity,
    reference_integrity,
    replay,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.experiment_tracking.ledger.state_path", sp)
    return sp


def _eng():
    return ExperimentTrackingEngine()


def _exp(e, name="regime-study", now=T[0]):
    return e.create_experiment(name, "test regime filter", [], now, commit=True).experiment_id


def _run(e, exp, now=T[1]):
    return e.record_run(exp, "dinf:v1", "git:abc123", "", now, commit=True).run_id


# ═══════════════ experiment ═══════════════
def test_create_experiment(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ex = _eng().create_experiment("exp", "obj", ["alpha"], T[0], commit=True)
    assert ex.experiment_id.startswith("XTE:")
    assert ex.tags == ["alpha"]


def test_experiment_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.create_experiment("e", now=T[0], commit=True).experiment_id
    b = e.create_experiment("e", now=T[1], commit=True).experiment_id
    assert a == b
    assert len(ledger.read_experiments()) == 1


def test_experiment_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _exp(e)
    assert any(a["artifact_type"] == "EXPERIMENT" for a in ledger.read_artifacts())


def test_list_experiments(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _exp(e, "a")
    _exp(e, "b")
    assert len(e.list_experiments()) == 2


# ═══════════════ run ═══════════════
def test_record_run(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    r = e.record_run(exp, "dinf:v1", "git:abc", "baseline", T[1], commit=True)
    assert r.run_id.startswith("XTR:")
    assert r.status == "RECORDED"
    assert r.dataset_version == "dinf:v1"
    assert r.code_version == "git:abc"


def test_run_unknown_experiment(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().record_run("XTE:nope", now=T[0], commit=True)


def test_run_status_always_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    e.record_run(exp, now=T[1], commit=True)
    e.record_run(exp, now=T[2], commit=True)
    for r in ledger.read_runs():
        assert r["status"] == "RECORDED"  # 추적만 — 실행 아님


def test_run_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    run = _run(e, exp)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    run_art = next(a for a in arts.values() if a["ref_id"] == run)
    assert run_art["parent_artifact"] == M.artifact_id(M.ART_EXPERIMENT, exp)


def test_multiple_runs(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    e.record_run(exp, now=T[1], commit=True)
    e.record_run(exp, now=T[2], commit=True)
    assert len(ledger.runs_for(exp)) == 2


@pytest.mark.parametrize("s", RUN_STATUSES)
def test_run_statuses(s):
    assert s in RUN_STATUSES


# ═══════════════ parameters ═══════════════
def test_record_parameter(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    run = _run(e, exp)
    p = e.record_parameter(run, "lookback", 20, T[2], commit=True)
    assert p.parameter_id.startswith("XTP:")
    assert p.value == "20"


def test_parameter_unknown_run(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().record_parameter("XTR:nope", "k", "v", now=T[0], commit=True)


def test_parameter_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    run = _run(e, exp)
    a = e.record_parameter(run, "k", "1", T[2], commit=True).parameter_id
    b = e.record_parameter(run, "k", "2", T[3], commit=True).parameter_id
    assert a == b
    assert len(ledger.parameters_for(run)) == 1


# ═══════════════ results ═══════════════
def test_record_result(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    run = _run(e, exp)
    r = e.record_result(run, "sharpe", 1.42, T[2], commit=True)
    assert r.result_id.startswith("XTM:")
    assert r.value == 1.42


def test_result_unknown_run(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().record_result("XTR:nope", "m", 1, now=T[0], commit=True)


def test_result_multiple_metrics(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    run = _run(e, exp)
    e.record_result(run, "sharpe", 1.4, T[2], commit=True)
    e.record_result(run, "drawdown", -0.15, T[3], commit=True)
    assert len(ledger.results_for(run)) == 2


# ═══════════════ artifacts ═══════════════
def test_attach_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    run = _run(e, exp)
    a = e.attach_artifact(run, "s3://model.pkl", "MODEL", T[2], commit=True)
    assert a.artifact_id.startswith("XTA:")
    assert a.artifact_type == "ATTACHED"


def test_attach_bad_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    run = _run(e, exp)
    with pytest.raises(ValueError):
        e.attach_artifact(run, "ref", "NOPE", now=T[2], commit=True)


def test_attach_unknown_run(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().attach_artifact("XTR:nope", "ref", now=T[0], commit=True)


@pytest.mark.parametrize("at", ARTIFACT_TYPES)
def test_artifact_types(at):
    assert at in ARTIFACT_TYPES


# ═══════════════ compare runs ═══════════════
def test_compare_runs(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    ra = e.record_run(exp, now=T[1], commit=True).run_id
    rb = e.record_run(exp, now=T[2], commit=True).run_id
    e.record_result(ra, "sharpe", 1.0, T[3], commit=True)
    e.record_result(rb, "sharpe", 1.5, T[4], commit=True)
    c = e.compare_runs(ra, rb, T[5], commit=True)
    assert c.comparison_id.startswith("XTC:")
    assert c.metric_deltas["sharpe"] == 0.5


def test_compare_unknown_run(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    run = _run(e, exp)
    with pytest.raises(UnknownEntityError):
        e.compare_runs(run, "XTR:nope", now=T[2], commit=True)


def test_compare_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    ra = e.record_run(exp, now=T[1], commit=True).run_id
    rb = e.record_run(exp, now=T[2], commit=True).run_id
    e.record_result(ra, "m", 2.0, T[3], commit=True)
    e.record_result(rb, "m", 5.0, T[4], commit=True)
    c1 = e.compare_runs(ra, rb, T[5], commit=False)
    c2 = e.compare_runs(ra, rb, T[5], commit=False)
    assert c1.to_dict() == c2.to_dict()


def test_metric_delta_helper():
    assert metric_delta(1.0, 1.5) == 0.5
    assert metric_delta("x", 1) == 0.0


# ═══════════════ summary ═══════════════
def test_generate_summary(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    ra = e.record_run(exp, now=T[1], commit=True).run_id
    rb = e.record_run(exp, now=T[2], commit=True).run_id
    e.record_result(ra, "sharpe", 1.0, T[3], commit=True)
    e.record_result(rb, "sharpe", 1.5, T[4], commit=True)
    s = e.generate_summary(exp)
    assert s["run_count"] == 2
    assert s["best_by_metric"]["sharpe"]["run_id"] == rb  # 1.5 > 1.0


def test_summary_unknown_experiment(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().generate_summary("XTE:nope")


# ═══════════════ integration READ ONLY ═══════════════
def test_source_layers_present():
    for k in ("data_infrastructure", "strategy_generation", "simulation"):
        assert k in ledger.SOURCE_LAYERS


def test_source_count_readonly(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("dinf_datasets.jsonl")
    with open(p, "w") as f:
        for i in range(3):
            f.write(json.dumps({"dataset_event_id": f"e{i}"}) + "\n")
    before = open(p).read()
    assert ledger.source_count("data_infrastructure") == 3
    assert open(p).read() == before


# ═══════════════ verify ═══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_verify_after_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    run = _run(e, exp)
    e.record_parameter(run, "k", "v", T[2], commit=True)
    e.record_result(run, "m", 1.0, T[3], commit=True)
    e.attach_artifact(run, "ref", "LOG", T[4], commit=True)
    run2 = e.record_run(exp, now=T[5], commit=True).run_id
    e.record_result(run2, "m", 2.0, T[6], commit=True)
    e.compare_runs(run, run2, T[7], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _exp(e)
    p = sp("expt_experiments.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["name"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    e.record_run(exp, now=T[1], commit=True)
    e.record_run(exp, now=T[2], commit=True)
    p = sp("expt_runs.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:bad"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _exp(e)
    p = sp("expt_experiments.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    with open(p, "a") as f:
        f.write(json.dumps(rows[0]) + "\n")
    assert verify_chain()["ok"] is False


def test_reference_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    run = _run(e, exp)
    e.record_result(run, "m", 1.0, T[2], commit=True)
    assert reference_integrity()["ok"] is True


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _exp(e, "a")
    _exp(e, "b")
    assert duplicate_integrity()["ok"] is True


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    run = _run(e, exp)
    e.attach_artifact(run, "ref", "MODEL", T[2], commit=True)
    assert lineage_integrity()["ok"] is True


# ═══════════════ replay ═══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    _run(e, exp)
    assert replay(e, T[9])["deterministic"] is True


# ═══════════════ report ═══════════════
def test_generate_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    run = _run(e, exp)
    e.record_parameter(run, "k", "v", T[2], commit=True)
    e.record_result(run, "m", 1.0, T[3], commit=True)
    r = e.generate_report("SYSTEM", T[4], commit=True)
    assert r.report_id.startswith("XTO:")
    assert r.is_binding is False
    assert r.experiment_count == 1
    assert r.run_count == 1
    assert r.status_distribution.get("RECORDED") == 1


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("SYSTEM", T[0], commit=True)
    assert "EXECUTE" in r.disclaimer


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb(verb):
    assert M.is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["TRACK", "RECORD", "COMPARE", "LOG", "SUMMARIZE"])
def test_allowed_verb(verb):
    assert M.is_forbidden_verb(verb) is False


def test_forbidden_empty():
    assert M.is_forbidden_verb("") is False


# ═══════════════ ID / hash ═══════════════
@pytest.mark.parametrize("fn,args,prefix", [
    (M.experiment_id, ("n",), "XTE:"),
    (M.run_id, ("e", 0), "XTR:"),
    (M.parameter_id, ("r", "k"), "XTP:"),
    (M.result_id, ("r", "m"), "XTM:"),
    (M.comparison_id, ("a", "b"), "XTC:"),
    (M.report_id, ("s", "t"), "XTO:"),
    (M.artifact_id, ("RUN", "r"), "XTA:"),
])
def test_id_prefixes(fn, args, prefix):
    assert fn(*args).startswith(prefix)


def test_comparison_id_symmetric():
    assert M.comparison_id("a", "b") == M.comparison_id("b", "a")


def test_content_hash_excludes_meta():
    a = content_hash({"x": 1, "previous_hash": "p", "record_hash": "r"})
    b = content_hash({"x": 1, "previous_hash": "Q", "record_hash": "Z"})
    assert a == b


# ═══════════════ summary ═══════════════
def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    run = _run(e, exp)
    e.record_result(run, "m", 1.0, T[2], commit=True)
    s = e.summary(T[9])
    assert s.experiment_count == 1
    assert s.run_count == 1
    assert s.result_count == 1


# ═══════════════ CLI ═══════════════
def test_cli_experiment(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.experiment_tracking.__main__ import main
    assert main(["experiment", "--name", "exp", "--objective", "o", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["experiment"]["experiment_id"].startswith("XTE:")


def test_cli_run_and_result(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.experiment_tracking.__main__ import main
    main(["experiment", "--name", "e", "--commit"])
    exp = json.loads(capsys.readouterr().out)["experiment"]["experiment_id"]
    main(["run", "--experiment", exp, "--dataset-version", "v1", "--commit"])
    run = json.loads(capsys.readouterr().out)["run"]["run_id"]
    assert main(["result", "--run", run, "--metric", "sharpe", "--value", "1.4", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["result"]["value"] == 1.4


def test_cli_compare(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.experiment_tracking.__main__ import main
    main(["experiment", "--name", "e", "--commit"])
    exp = json.loads(capsys.readouterr().out)["experiment"]["experiment_id"]
    main(["run", "--experiment", exp, "--commit"])
    ra = json.loads(capsys.readouterr().out)["run"]["run_id"]
    main(["run", "--experiment", exp, "--commit"])
    rb = json.loads(capsys.readouterr().out)["run"]["run_id"]
    assert main(["compare", "--run-a", ra, "--run-b", rb, "--commit"]) == 0


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.experiment_tracking.__main__ import main
    assert main(["report", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["report"]["is_binding"] is False


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.experiment_tracking.__main__ import main
    assert main(["verify"]) == 0


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.experiment_tracking.__main__ import main
    assert main(["summary"]) == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.experiment_tracking.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


# ═══════════════ 격리 / ledger ═══════════════
def test_records_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ex = _eng().create_experiment("e", now=T[0], commit=True)
    with pytest.raises(Exception):
        ex.name = "x"


def test_seven_ledgers():
    assert len(ledger.ALL_LEDGERS) == 7


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("expt_")


def test_required_ledgers_present():
    names = {f for f, _ in ledger.ALL_LEDGERS}
    for req in ("expt_experiments.jsonl", "expt_runs.jsonl", "expt_parameters.jsonl",
                "expt_results.jsonl", "expt_comparisons.jsonl", "expt_reports.jsonl",
                "expt_artifacts.jsonl"):
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
    bad = ("execute", "trade", "deploy", "allocate", "approve", "run_experiment", "execute_trade",
           "place_order", "allocate_capital", "deploy_strategy", "activate_live", "broker_execution")
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


# ═══════════════ 추가 커버리지 ═══════════════
@pytest.mark.parametrize("at", ARTIFACT_TYPES)
def test_attach_each_artifact_type(tmp_path, monkeypatch, at):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    run = _run(e, exp)
    a = e.attach_artifact(run, f"ref-{at}", at, T[2], commit=True)
    assert a.artifact_type == "ATTACHED"


def test_run_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    e.record_run(exp, now=T[1], commit=False)
    assert ledger.read_runs() == []


def test_experiment_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().create_experiment("e", now=T[0], commit=False)
    assert ledger.read_experiments() == []


def test_result_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    run = _run(e, exp)
    a = e.record_result(run, "m", 1.0, T[2], commit=True).result_id
    b = e.record_result(run, "m", 9.9, T[3], commit=True).result_id
    assert a == b
    assert len(ledger.results_for(run)) == 1


def test_compare_disjoint_metrics(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    ra = e.record_run(exp, now=T[1], commit=True).run_id
    rb = e.record_run(exp, now=T[2], commit=True).run_id
    e.record_result(ra, "sharpe", 1.0, T[3], commit=True)
    e.record_result(rb, "sortino", 2.0, T[4], commit=True)
    c = e.compare_runs(ra, rb, T[5], commit=True)
    assert "sharpe" in c.metric_deltas
    assert "sortino" in c.metric_deltas


def test_summary_empty_experiment(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    s = e.generate_summary(exp)
    assert s["run_count"] == 0
    assert s["best_by_metric"] == {}


def test_run_tracks_versions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    r = e.record_run(exp, "dinf:v42", "git:deadbeef", "", T[1], commit=True)
    assert r.dataset_version == "dinf:v42"
    assert r.code_version == "git:deadbeef"


def test_all_source_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert set(ledger.all_source_counts()) == set(ledger.SOURCE_LAYERS)


def test_parameter_tracks_value(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    exp = _exp(e)
    run = _run(e, exp)
    p = e.record_parameter(run, "learning_rate", 0.001, T[2], commit=True)
    assert p.key == "learning_rate"
    assert p.value == "0.001"


# ═══════════════ end-to-end ═══════════════
def test_end_to_end(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("dinf_datasets.jsonl"), "w") as f:
        f.write(json.dumps({"dataset_event_id": "dinf:1"}) + "\n")
    e = _eng()
    # 실험 등록 → 두 run 기록(외부 실행 결과) → 파라미터·결과·아티팩트 → 비교 → 요약
    exp = e.create_experiment("regime-overlay-study", "does regime filter improve sharpe",
                              ["alpha", "regime"], T[0], commit=True).experiment_id
    baseline = e.record_run(exp, "dinf:v1", "git:base", "baseline", T[1], commit=True).run_id
    e.record_parameter(baseline, "lookback", 20, T[2], commit=True)
    e.record_result(baseline, "sharpe", 1.10, T[3], commit=True)
    e.record_result(baseline, "max_drawdown", -0.22, T[4], commit=True)
    e.attach_artifact(baseline, "s3://baseline-model.pkl", "MODEL", T[5], commit=True)
    variant = e.record_run(exp, "dinf:v1", "git:variant", "regime-gated", T[6], commit=True).run_id
    e.record_parameter(variant, "lookback", 20, T[7], commit=True)
    e.record_result(variant, "sharpe", 1.45, T[8], commit=True)
    e.record_result(variant, "max_drawdown", -0.15, T[9], commit=True)
    # 비교(결정적) — 선택/승인 아님
    c = e.compare_runs(baseline, variant, T[10], commit=True)
    assert c.metric_deltas["sharpe"] == 0.35
    assert c.metric_deltas["max_drawdown"] == 0.07
    # 요약: 최고 지표
    s = e.generate_summary(exp)
    assert s["run_count"] == 2
    assert s["best_by_metric"]["sharpe"]["run_id"] == variant
    # 리포트
    r = e.generate_report("SYSTEM", T[11], commit=True)
    assert r.run_count == 2
    assert r.comparison_count == 1
    assert r.is_binding is False  # TRACK ≠ EXECUTE
    # 모든 run 은 기록 상태(실행 아님)
    assert all(x["status"] == "RECORDED" for x in ledger.read_runs())
    assert open(sp("dinf_datasets.jsonl")).read()  # 상위 원장 불변
    assert verify_chain()["ok"] is True
    assert replay(e, T[12])["deterministic"] is True
