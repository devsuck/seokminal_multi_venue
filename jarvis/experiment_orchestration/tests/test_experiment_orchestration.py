"""P31 experiment_orchestration 테스트 — 계획/요청 생애주기·스케줄·의존성(순환)·실행요청(사람승인·실행금지)·
이력·계보·verify·replay·CLI·보안·READ ONLY 상위. ORCHESTRATION ≠ EXECUTION."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.experiment_orchestration import ledger
from jarvis.experiment_orchestration import models as M
from jarvis.experiment_orchestration.engine import ExperimentOrchestrationEngine
from jarvis.experiment_orchestration.models import (
    DEPENDENCY_TYPES,
    FORBIDDEN_VERBS,
    HISTORY_OUTCOMES,
    PLAN_STATES,
    REQUEST_STATES,
    P_ARCHIVED,
    P_CONCLUDED,
    P_DRAFT,
    P_READY,
    P_SCHEDULED,
    R_APPROVED,
    R_REJECTED,
    R_REQUESTED,
    R_SUBMITTED,
    ApproverRequired,
    DependencyCycleError,
    IllegalPlanTransition,
    IllegalRequestTransition,
    UnknownEntityError,
    can_plan_transition,
    can_request_transition,
    content_hash,
    topological_order,
)
from jarvis.experiment_orchestration.verify import (
    dependency_integrity,
    duplicate_integrity,
    execution_prevention_integrity,
    lineage_integrity,
    plan_lifecycle_integrity,
    replay,
    request_lifecycle_integrity,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.experiment_orchestration.ledger.state_path", sp)
    return sp


def _eng():
    return ExperimentOrchestrationEngine()


def _plan(e, name="regime-backtest", now=T[0]):
    return e.create_plan(name, "test regime filter", now, commit=True).plan_id


# ═══════════════ plan lifecycle ═══════════════
def test_create_plan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().create_plan("p", "obj", T[0], commit=True)
    assert ev.to_state == P_DRAFT
    assert ev.plan_id.startswith("EOP:")
    assert ev.plan_event_id.startswith("EOE:")


def test_plan_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    plan = _plan(e)
    e.schedule_plan(plan, "2026-08-01", "HIGH", "morning", T[1], commit=True)  # → SCHEDULED
    e.mark_ready(plan, now=T[2], commit=True)
    e.conclude_plan(plan, now=T[3], commit=True)
    e.archive_plan(plan, now=T[4], commit=True)
    assert e.plan_state(plan) == P_ARCHIVED


def test_plan_no_skip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    plan = _plan(e)
    with pytest.raises(IllegalPlanTransition):
        e.conclude_plan(plan, now=T[1], commit=True)  # DRAFT→CONCLUDED skip


def test_plan_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.create_plan("p", now=T[0], commit=True).plan_id
    b = e.create_plan("p", now=T[1], commit=True).plan_id
    assert a == b
    assert len(ledger.plan_events(a)) == 1


def test_plan_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().mark_ready("EOP:nope", now=T[1], commit=True)


@pytest.mark.parametrize("frm,to,ok", [
    (P_DRAFT, P_SCHEDULED, True), (P_DRAFT, P_READY, False),
    (P_SCHEDULED, P_READY, True), (P_READY, P_CONCLUDED, True),
    (P_CONCLUDED, P_ARCHIVED, True), (P_CONCLUDED, P_SCHEDULED, True),
    (P_ARCHIVED, P_SCHEDULED, False),
])
def test_plan_transition_matrix(frm, to, ok):
    assert can_plan_transition(frm, to) is ok


@pytest.mark.parametrize("s", PLAN_STATES)
def test_plan_states(s):
    assert s in PLAN_STATES


# ═══════════════ schedule ═══════════════
def test_schedule_plan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    plan = _plan(e)
    s = e.schedule_plan(plan, "2026-08-01", "HIGH", "am", T[1], commit=True)
    assert s.schedule_id.startswith("EOS:")
    assert e.plan_state(plan) == P_SCHEDULED


def test_schedule_unknown_plan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().schedule_plan("EOP:nope", now=T[0], commit=True)


# ═══════════════ dependency (cycle prevention) ═══════════════
def test_add_dependency(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _plan(e, "a")
    b = _plan(e, "b", now=T[1])
    d = e.add_dependency(a, b, "SEQUENTIAL", T[2], commit=True)
    assert d.dependency_id.startswith("EOD:")


def test_dependency_bad_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _plan(e, "a")
    b = _plan(e, "b", now=T[1])
    with pytest.raises(ValueError):
        e.add_dependency(a, b, "NOPE", T[2], commit=True)


def test_dependency_cycle_prevented(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _plan(e, "a")
    b = _plan(e, "b", now=T[1])
    e.add_dependency(a, b, "SEQUENTIAL", T[2], commit=True)
    with pytest.raises(DependencyCycleError):
        e.add_dependency(b, a, "SEQUENTIAL", T[3], commit=True)  # cycle


def test_dependency_unknown_plan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _plan(e, "a")
    with pytest.raises(UnknownEntityError):
        e.add_dependency(a, "EOP:nope", now=T[2], commit=True)


def test_resolve_dependencies(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _plan(e, "a")
    b = _plan(e, "b", now=T[1])
    e.add_dependency(a, b, "SEQUENTIAL", T[2], commit=True)
    res = e.resolve_dependencies(a)
    assert res["ready"] is False  # b not concluded
    e.schedule_plan(b, now=T[3], commit=True)
    e.mark_ready(b, now=T[4], commit=True)
    e.conclude_plan(b, now=T[5], commit=True)
    assert e.resolve_dependencies(a)["ready"] is True


@pytest.mark.parametrize("dt", DEPENDENCY_TYPES)
def test_dependency_types(dt):
    assert dt in DEPENDENCY_TYPES


def test_topological_order():
    order = topological_order(["a", "b", "c"], [("a", "b"), ("b", "c")])
    assert order.index("a") < order.index("b") < order.index("c")


def test_topological_order_cycle():
    assert topological_order(["a", "b"], [("a", "b"), ("b", "a")]) == []


# ═══════════════ execution request (human approval, no execution) ═══════════════
def test_create_execution_request(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    plan = _plan(e)
    r = e.create_execution_request(plan, "researcher-1", T[1], commit=True)
    assert r.request_id.startswith("EOQ:")
    assert r.to_state == R_REQUESTED
    assert r.is_executed is False


def test_request_full_approve(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    plan = _plan(e)
    req = e.create_execution_request(plan, "r1", T[1], commit=True).request_id
    e.submit_request(req, now=T[2], commit=True)
    e.approve_request(req, "lead-1", now=T[3], commit=True)
    assert e.request_state(req) == R_APPROVED
    # 승인돼도 실행되지 않음
    assert all(ev["is_executed"] is False for ev in ledger.request_events(req))


def test_request_reject(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    plan = _plan(e)
    req = e.create_execution_request(plan, "r1", T[1], commit=True).request_id
    e.submit_request(req, now=T[2], commit=True)
    e.reject_request(req, "lead", now=T[3], commit=True)
    assert e.request_state(req) == R_REJECTED


def test_request_approve_requires_approver(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    plan = _plan(e)
    req = e.create_execution_request(plan, "r1", T[1], commit=True).request_id
    e.submit_request(req, now=T[2], commit=True)
    with pytest.raises(ApproverRequired):
        e.approve_request(req, "", now=T[3], commit=True)


def test_request_no_skip_to_approved(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    plan = _plan(e)
    req = e.create_execution_request(plan, "r1", T[1], commit=True).request_id
    with pytest.raises(IllegalRequestTransition):
        e.approve_request(req, "lead", now=T[2], commit=True)  # REQUESTED→APPROVED skip


def test_request_never_executed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    plan = _plan(e)
    req = e.create_execution_request(plan, "r1", T[1], commit=True).request_id
    e.submit_request(req, now=T[2], commit=True)
    e.approve_request(req, "lead", now=T[3], commit=True)
    for ev in ledger.read_request_events():
        assert ev["is_executed"] is False


@pytest.mark.parametrize("frm,to,ok", [
    (R_REQUESTED, R_SUBMITTED, True), (R_REQUESTED, R_APPROVED, False),
    (R_SUBMITTED, R_APPROVED, True), (R_SUBMITTED, R_REJECTED, True),
    (R_APPROVED, R_REJECTED, False),
])
def test_request_transition_matrix(frm, to, ok):
    assert can_request_transition(frm, to) is ok


@pytest.mark.parametrize("s", REQUEST_STATES)
def test_request_states(s):
    assert s in REQUEST_STATES


# ═══════════════ history ═══════════════
def test_record_history(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    plan = _plan(e)
    h = e.record_history(plan, "setup", "RECORDED", "config prepared", T[1], commit=True)
    assert h.history_id.startswith("EOH:")


def test_history_bad_outcome(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    plan = _plan(e)
    with pytest.raises(ValueError):
        e.record_history(plan, "p", "EXECUTED", now=T[1], commit=True)


@pytest.mark.parametrize("o", HISTORY_OUTCOMES)
def test_history_outcomes(o):
    assert o in HISTORY_OUTCOMES


# ═══════════════ integration READ ONLY ═══════════════
def test_source_layers_present():
    for k in ("strategy_generation", "autonomous_research", "research_automation",
              "production_readiness", "simulation"):
        assert k in ledger.SOURCE_LAYERS


def test_source_count_readonly(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("rsg_candidates.jsonl")
    with open(p, "w") as f:
        for i in range(3):
            f.write(json.dumps({"candidate_event_id": f"c{i}"}) + "\n")
    before = open(p).read()
    assert ledger.source_count("strategy_generation") == 3
    assert open(p).read() == before


# ═══════════════ verify ═══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_verify_after_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _plan(e, "a")
    b = _plan(e, "b", now=T[1])
    e.schedule_plan(a, now=T[2], commit=True)
    e.add_dependency(a, b, "DATA", T[3], commit=True)
    req = e.create_execution_request(a, "r", T[4], commit=True).request_id
    e.submit_request(req, now=T[5], commit=True)
    e.approve_request(req, "lead", now=T[6], commit=True)
    e.record_history(a, "setup", now=T[7], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _plan(e)
    p = sp("exo_plans.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["name"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _plan(e, "a")
    e.schedule_plan(a, now=T[1], commit=True)
    p = sp("exo_plans.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:bad"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _plan(e)
    p = sp("exo_plans.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    with open(p, "a") as f:
        f.write(json.dumps(rows[0]) + "\n")
    assert verify_chain()["ok"] is False


def test_plan_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    plan = _plan(e)
    e.schedule_plan(plan, now=T[1], commit=True)
    assert plan_lifecycle_integrity()["ok"] is True


def test_request_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    plan = _plan(e)
    req = e.create_execution_request(plan, "r", T[1], commit=True).request_id
    e.submit_request(req, now=T[2], commit=True)
    assert request_lifecycle_integrity()["ok"] is True


def test_execution_prevention_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    plan = _plan(e)
    e.create_execution_request(plan, "r", T[1], commit=True)
    assert execution_prevention_integrity()["ok"] is True


def test_execution_prevention_detects_executed(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    plan = _plan(e)
    e.create_execution_request(plan, "r", T[1], commit=True)
    p = sp("exo_requests.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["is_executed"] = True
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert execution_prevention_integrity()["ok"] is False


def test_dependency_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _plan(e, "a")
    b = _plan(e, "b", now=T[1])
    e.add_dependency(a, b, "SEQUENTIAL", T[2], commit=True)
    assert dependency_integrity()["ok"] is True


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _plan(e, "a")
    _plan(e, "b", now=T[1])
    assert duplicate_integrity()["ok"] is True


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    plan = _plan(e)
    e.schedule_plan(plan, now=T[1], commit=True)
    assert lineage_integrity()["ok"] is True


# ═══════════════ replay ═══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _plan(e)
    assert replay(e, T[9])["deterministic"] is True


# ═══════════════ report ═══════════════
def test_generate_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    plan = _plan(e)
    e.schedule_plan(plan, now=T[1], commit=True)
    req = e.create_execution_request(plan, "r", T[2], commit=True).request_id
    e.submit_request(req, now=T[3], commit=True)
    e.approve_request(req, "lead", now=T[4], commit=True)
    r = e.generate_report("SYSTEM", T[5], commit=True)
    assert r.report_id.startswith("EOR:")
    assert r.is_binding is False
    assert r.plan_count == 1
    assert r.approved_request_count == 1


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("SYSTEM", T[0], commit=True)
    assert "EXECUTION" in r.disclaimer


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb(verb):
    assert M.is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["ORCHESTRATE", "SCHEDULE", "PLAN", "REQUEST", "RECORD"])
def test_allowed_verb(verb):
    assert M.is_forbidden_verb(verb) is False


def test_forbidden_execute_experiment():
    assert "EXECUTE_EXPERIMENT" in FORBIDDEN_VERBS
    assert "RUN_EXPERIMENT" in FORBIDDEN_VERBS


def test_forbidden_empty():
    assert M.is_forbidden_verb("") is False


# ═══════════════ ID / hash ═══════════════
@pytest.mark.parametrize("fn,args,prefix", [
    (M.plan_id, ("n",), "EOP:"),
    (M.plan_event_id, ("p", "DRAFT", 0), "EOE:"),
    (M.schedule_id, ("p", 0), "EOS:"),
    (M.dependency_id, ("p", "d"), "EOD:"),
    (M.request_id, ("p", 0), "EOQ:"),
    (M.request_event_id, ("r", "REQUESTED", 0), "EOX:"),
    (M.history_id, ("p", 0), "EOH:"),
    (M.report_id, ("s", "t"), "EOR:"),
    (M.artifact_id, ("PLAN", "r"), "EOA:"),
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
    plan = _plan(e)
    e.schedule_plan(plan, now=T[1], commit=True)
    s = e.summary(T[9])
    assert s.plan_count == 1
    assert s.schedule_count == 1


# ═══════════════ CLI ═══════════════
def test_cli_plan(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.experiment_orchestration.__main__ import main
    assert main(["plan", "--name", "p", "--objective", "o", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["plan"]["to_state"] == "DRAFT"


def test_cli_request(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.experiment_orchestration.__main__ import main
    main(["plan", "--name", "p", "--commit"])
    plan = json.loads(capsys.readouterr().out)["plan"]["plan_id"]
    assert main(["request", "--plan", plan, "--requester", "r", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["request"]["is_executed"] is False


def test_cli_schedule(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.experiment_orchestration.__main__ import main
    main(["plan", "--name", "p", "--commit"])
    plan = json.loads(capsys.readouterr().out)["plan"]["plan_id"]
    assert main(["schedule", "--plan", plan, "--priority", "HIGH", "--commit"]) == 0


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.experiment_orchestration.__main__ import main
    assert main(["report", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["report"]["is_binding"] is False


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.experiment_orchestration.__main__ import main
    assert main(["verify"]) == 0


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.experiment_orchestration.__main__ import main
    assert main(["summary"]) == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.experiment_orchestration.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


# ═══════════════ 격리 / ledger ═══════════════
def test_records_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().create_plan("p", now=T[0], commit=True)
    with pytest.raises(Exception):
        ev.name = "x"


def test_seven_ledgers():
    assert len(ledger.ALL_LEDGERS) == 7


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("exo_")


def test_required_ledgers_present():
    names = {f for f, _ in ledger.ALL_LEDGERS}
    for req in ("exo_plans.jsonl", "exo_schedules.jsonl", "exo_dependencies.jsonl",
                "exo_requests.jsonl", "exo_history.jsonl", "exo_reports.jsonl",
                "exo_artifacts.jsonl"):
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
    bad = ("execute", "deploy", "trade", "allocate", "run_experiment", "execute_experiment",
           "execute_trade", "place_order", "allocate_capital", "deploy_strategy", "launch_experiment")
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
    for attr in ("execute", "deploy", "trade", "run_experiment", "execute_experiment"):
        assert not hasattr(e, attr)


# ═══════════════ end-to-end ═══════════════
def test_end_to_end(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("rsg_candidates.jsonl"), "w") as f:
        f.write(json.dumps({"candidate_event_id": "sgc:1"}) + "\n")
    e = _eng()
    # 실험 계획 조정(실행 없음)
    setup = e.create_plan("data-prep", "prepare regime dataset", T[0], commit=True).plan_id
    main_plan = e.create_plan("regime-backtest", "backtest regime overlay", T[1], commit=True).plan_id
    # 의존성(순환 방지)
    e.add_dependency(main_plan, setup, "DATA", T[2], commit=True)
    # 스케줄
    e.schedule_plan(setup, "2026-08-01", "HIGH", "am", T[3], commit=True)
    e.schedule_plan(main_plan, "2026-08-02", "NORMAL", "am", T[4], commit=True)
    # setup 완료 → main 의존성 해소
    e.mark_ready(setup, now=T[5], commit=True)
    e.conclude_plan(setup, now=T[6], commit=True)
    assert e.resolve_dependencies(main_plan)["ready"] is True
    # 실행 요청 → 제출 → 사람 승인(실행 아님)
    req = e.create_execution_request(main_plan, "researcher-1", T[7], commit=True).request_id
    e.submit_request(req, now=T[8], commit=True)
    e.approve_request(req, "lead-1", now=T[9], commit=True)  # APPROVED ≠ EXECUTED
    assert e.request_state(req) == "APPROVED"
    # 사람이 외부에서 실행 후 이력 기록
    e.record_history(main_plan, "backtest", "OBSERVED", "sharpe 1.3 (human-run)", T[10], commit=True)
    e.mark_ready(main_plan, now=T[11], commit=True)
    e.conclude_plan(main_plan, now=T[12], commit=True)
    r = e.generate_report("SYSTEM", T[13], commit=True)
    assert r.plan_count == 2
    assert r.approved_request_count == 1
    assert r.is_binding is False  # ORCHESTRATION ≠ EXECUTION
    # 어떤 요청도 실행되지 않음
    assert all(ev["is_executed"] is False for ev in ledger.read_request_events())
    assert open(sp("rsg_candidates.jsonl")).read()  # 상위 원장 불변
    assert verify_chain()["ok"] is True
    assert replay(e, T[14])["deterministic"] is True
