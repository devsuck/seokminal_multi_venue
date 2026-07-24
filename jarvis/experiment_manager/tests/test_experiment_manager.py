"""P11.4 Autonomous Experiment Manager 테스트. **AI 보조 실험 생성 — 제안 전용.**

실험 제안·생애주기(PROPOSED→REVIEWED→APPROVED_FOR_RESEARCH→COMPLETED)·계획 생성(불변·상태 제약)·연구 요청
(research_only·trading_approval=False·연구 승인 이후만)·결과 수집(불변·결론·연구 승인 이후만)·상태 추적·리포트·
verify(체인/변조/중복/생애주기/거래승인 경계)·replay·CLI·보안(금지import·실행/배포/라이브 없음·연구 승인≠거래 승인·
삭제 API 없음·불변·PROPOSAL≠EXECUTION·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.experiment_manager import ledger
from jarvis.experiment_manager import models as M
from jarvis.experiment_manager.engine import ExperimentManagerEngine
from jarvis.experiment_manager.models import (
    EXP_APPROVED_FOR_RESEARCH,
    EXP_COMPLETED,
    EXP_PROPOSED,
    EXP_REVIEWED,
    OUTCOME_INCONCLUSIVE,
    OUTCOME_REFUTED,
    OUTCOME_SUPPORTED,
    ExperimentStateError,
    IllegalExperimentTransition,
    ImmutablePlanError,
    ImmutableResultError,
    InvalidOutcome,
    UnknownExperimentError,
)

T0 = "2026-07-24T00:00:00Z"
T1 = "2026-07-24T00:01:00Z"
T2 = "2026-07-24T00:02:00Z"
T3 = "2026-07-24T00:03:00Z"
T4 = "2026-07-24T00:04:00Z"


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.experiment_manager.ledger.state_path", sp)
    return sp


def _eng():
    return ExperimentManagerEngine()


def _exp(e, title="Momentum decay", hyp="12m momentum decays", by="strat_agent", now=T0):
    return e.propose_experiment(title, hyp, by, "study decay", now, commit=True).experiment_id


def _approved(e, now=T0):
    """APPROVED_FOR_RESEARCH 상태 실험."""
    x = _exp(e, now=now)
    e.review_experiment(x, "", T1, commit=True)
    e.approve_for_research(x, "", T2, commit=True)
    return x


# ══════════════ propose / lifecycle ══════════════
def test_propose(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().propose_experiment("T", "H", "agent", "obj", T0, commit=True)
    assert ev.experiment_id.startswith("EXM:")
    assert ev.to_state == EXP_PROPOSED


def test_propose_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _eng().propose_experiment("T", "H", "agent", "o", T0, commit=False)
    b = _eng().propose_experiment("T", "H", "agent", "o2", T1, commit=False)
    assert a.experiment_id == b.experiment_id


def test_propose_no_auto_advance(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    assert e.current_state(x) == EXP_PROPOSED  # 자동 승인 없음


def test_propose_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _exp(e)
    _exp(e, now=T1)
    assert len(ledger.experiment_ids()) == 1


def test_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    e.review_experiment(x, "", T1, commit=True)
    assert e.current_state(x) == EXP_REVIEWED
    e.approve_for_research(x, "", T2, commit=True)
    assert e.current_state(x) == EXP_APPROVED_FOR_RESEARCH
    e.complete_experiment(x, "", T3, commit=True)
    assert e.current_state(x) == EXP_COMPLETED


def test_illegal_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    with pytest.raises(IllegalExperimentTransition):
        e.approve_for_research(x, "", T1, commit=True)  # PROPOSED->APPROVED 불가


def test_completed_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    e.complete_experiment(x, "", T3, commit=True)
    with pytest.raises(IllegalExperimentTransition):
        e.review_experiment(x, "", T4, commit=True)


def test_experiment_meta(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = e.propose_experiment("Title", "Hyp", "Bob", "Obj", T0, commit=True).experiment_id
    m = e.experiment_meta(x)
    assert m["title"] == "Title"
    assert m["proposer"] == "Bob"
    assert m["state"] == EXP_PROPOSED


def test_unknown_experiment(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().current_state("EXM:ghost") is None
    with pytest.raises(UnknownExperimentError):
        _eng().experiment_meta("EXM:ghost")


def test_four_states():
    assert len(M.EXPERIMENT_STATES) == 4
    assert set(M.EXPERIMENT_STATES) == {"PROPOSED", "REVIEWED", "APPROVED_FOR_RESEARCH",
                                        "COMPLETED"}


# ══════════════ generate_experiment_plan ══════════════
def test_plan_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    p = e.generate_experiment_plan(x, "cross_sectional", ["ret_12m"], "crsp", ["sharpe>1"], "3m",
                                   T0, commit=True)
    assert p.plan_id.startswith("EXL:")
    assert p.variables == ["ret_12m"]


def test_plan_in_reviewed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    e.review_experiment(x, "", T1, commit=True)
    p = e.generate_experiment_plan(x, "m", [], "d", [], "", T1, commit=True)
    assert p.experiment_id == x


def test_plan_blocked_after_approval(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    with pytest.raises(ExperimentStateError):
        e.generate_experiment_plan(x, "m", [], "d", [], "", T3, commit=True)


def test_plan_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    e.generate_experiment_plan(x, "m", ["a"], "d1", [], "", T0, commit=True)
    with pytest.raises(ImmutablePlanError):
        e.generate_experiment_plan(x, "m", ["b"], "d2", [], "", T1, commit=True)


def test_plan_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    e.generate_experiment_plan(x, "m", ["a"], "d", [], "", T0, commit=True)
    e.generate_experiment_plan(x, "m", ["a"], "d", [], "", T1, commit=True)
    assert len(ledger.experiment_plans(x)) == 1


def test_plan_multiple_methods(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    e.generate_experiment_plan(x, "m1", [], "", [], "", T0, commit=True)
    e.generate_experiment_plan(x, "m2", [], "", [], "", T0, commit=True)
    assert len(ledger.experiment_plans(x)) == 2


def test_plan_unknown_experiment(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownExperimentError):
        _eng().generate_experiment_plan("EXM:ghost", "m", [], "", [], "", T0, commit=True)


# ══════════════ create_research_request (연구 승인 ≠ 거래 승인) ══════════════
def test_request_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    r = e.create_research_request(x, "", "RESEARCH", "justified", T3, commit=True)
    assert r.request_id.startswith("EXR:")
    assert r.research_only is True
    assert r.trading_approval is False


def test_request_blocked_before_approval(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    with pytest.raises(ExperimentStateError):
        e.create_research_request(x, "", "RESEARCH", "", T1, commit=True)


def test_request_never_trading_approval(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    r = e.create_research_request(x, "", "RESEARCH", "", T3, commit=True)
    # 어떤 인자로도 trading_approval 을 켤 수 없음(항상 False)
    assert r.trading_approval is False
    assert "TRADING_APPROVAL" in r.disclaimer


def test_request_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    e.create_research_request(x, "", "RESEARCH", "", T3, commit=True)
    e.create_research_request(x, "", "RESEARCH", "", T4, commit=True)
    assert len(ledger.experiment_requests(x)) == 1


def test_request_in_completed_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    e.complete_experiment(x, "", T3, commit=True)
    r = e.create_research_request(x, "", "RESEARCH", "", T4, commit=True)
    assert r.research_only is True


# ══════════════ collect_results ══════════════
def test_results_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    r = e.collect_results(x, {"sharpe": 1.2}, ["works oos"], OUTCOME_SUPPORTED, "ok", T3,
                          commit=True)
    assert r.result_id.startswith("EXT:")
    assert r.outcome == OUTCOME_SUPPORTED


def test_results_blocked_before_approval(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    with pytest.raises(ExperimentStateError):
        e.collect_results(x, {}, [], OUTCOME_SUPPORTED, "", T1, commit=True)


def test_results_invalid_outcome(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    with pytest.raises(InvalidOutcome):
        e.collect_results(x, {}, [], "MAYBE", "", T3, commit=True)


@pytest.mark.parametrize("outcome", list(M.OUTCOMES))
def test_results_all_outcomes(tmp_path, monkeypatch, outcome):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    r = e.collect_results(x, {}, [], outcome, "", T3, commit=True)
    assert r.outcome == outcome


def test_results_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    e.collect_results(x, {"a": 1}, [], OUTCOME_SUPPORTED, "", T3, commit=True)
    with pytest.raises(ImmutableResultError):
        e.collect_results(x, {"a": 2}, [], OUTCOME_REFUTED, "", T3, commit=True)


def test_results_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    e.collect_results(x, {"a": 1}, [], OUTCOME_SUPPORTED, "", T3, commit=True)
    e.collect_results(x, {"a": 1}, [], OUTCOME_SUPPORTED, "", T3, commit=True)
    assert len(ledger.experiment_results(x)) == 1


def test_results_multiple_times(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    e.collect_results(x, {}, [], OUTCOME_SUPPORTED, "", T3, commit=True)
    e.collect_results(x, {}, [], OUTCOME_REFUTED, "", T4, commit=True)  # 다른 시각 → 다른 id
    assert len(ledger.experiment_results(x)) == 2


# ══════════════ track_experiment_status ══════════════
def test_track_status(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    st = e.track_experiment_status(x)
    assert st["state"] == EXP_APPROVED_FOR_RESEARCH
    assert len(st["history"]) == 3
    assert st["trading_approval"] is False


def test_track_status_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    e.create_research_request(x, "", "RESEARCH", "", T3, commit=True)
    e.collect_results(x, {}, [], OUTCOME_SUPPORTED, "", T3, commit=True)
    st = e.track_experiment_status(x)
    assert st["request_count"] == 1
    assert st["result_count"] == 1


# ══════════════ 리포트 ══════════════
def test_report_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    e.collect_results(x, {}, [], OUTCOME_SUPPORTED, "", T3, commit=True)
    r = e.generate_report(x, "EXPERIMENT", T4, commit=True)
    assert r.report_id.startswith("EXO:")
    assert r.result_count == 1
    assert r.trading_approval is False


def test_report_outcome_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    e.collect_results(x, {}, [], OUTCOME_SUPPORTED, "", T3, commit=True)
    e.collect_results(x, {}, [], OUTCOME_SUPPORTED, "", T4, commit=True)
    r = e.generate_report(x, "EXPERIMENT", "2026-07-24T00:05:00Z", commit=True)
    assert r.outcome_distribution[OUTCOME_SUPPORTED] == 2


def test_report_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    a = e.generate_report(x, "EXPERIMENT", T3, commit=False)
    b = e.generate_report(x, "EXPERIMENT", T3, commit=False)
    assert a.to_dict() == b.to_dict()


def test_report_has_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    r = e.generate_report(x, "EXPERIMENT", T1, commit=True)
    assert "TRADING_APPROVAL" in r.disclaimer


# ══════════════ verify / replay ══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.experiment_manager.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_after_full(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.experiment_manager.verify import verify_chain
    e = _eng()
    x = _exp(e)
    e.generate_experiment_plan(x, "m", [], "d", [], "", T0, commit=True)
    e.review_experiment(x, "", T1, commit=True)
    e.approve_for_research(x, "", T2, commit=True)
    e.create_research_request(x, "", "RESEARCH", "", T3, commit=True)
    e.collect_results(x, {}, [], OUTCOME_SUPPORTED, "", T3, commit=True)
    e.complete_experiment(x, "", T4, commit=True)
    res = verify_chain()
    assert res["ok"] is True
    assert res["lifecycle"]["ok"] is True
    assert res["trading_boundary"]["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _exp(e)
    p = sp("exm_experiments.jsonl")
    rows = [json.loads(x) for x in open(p)]
    rows[0]["title"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.experiment_manager.verify import verify_chain
    assert verify_chain()["ok"] is False


def test_verify_trading_boundary_detects_forged(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    e.create_research_request(x, "", "RESEARCH", "", T3, commit=True)
    # 원장에 trading_approval=True 위조
    p = sp("exm_requests.jsonl")
    rows = [json.loads(x2) for x2 in open(p)]
    rows[0]["trading_approval"] = True
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.experiment_manager.verify import trading_approval_boundary
    assert trading_approval_boundary()["ok"] is False


def test_verify_lifecycle_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.experiment_manager.verify import lifecycle_integrity
    e = _eng()
    _approved(e)
    assert lifecycle_integrity()["ok"] is True


def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.experiment_manager.verify import replay
    e = _eng()
    _approved(e)
    assert replay(e, T3)["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    e.create_research_request(x, "", "RESEARCH", "", T3, commit=True)
    e.collect_results(x, {}, [], OUTCOME_SUPPORTED, "", T3, commit=True)
    s = e.summary(T4)
    assert s.experiment_count == 1
    assert s.request_count == 1
    assert s.result_count == 1


# ══════════════ 조회 편의 ══════════════
def test_experiments_in_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x1 = _exp(e, "E1", "h1")
    x2 = _exp(e, "E2", "h2")
    e.review_experiment(x2, "", T1, commit=True)
    assert e.experiments_in_state(EXP_PROPOSED) == [x1]
    assert e.experiments_in_state(EXP_REVIEWED) == [x2]


# ══════════════ 보안 / 불변식 (no execution / no deployment) ══════════════
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
    e = ExperimentManagerEngine()
    for bad in ("run_live", "execute", "deploy", "trade", "allocate", "go_live", "launch_live",
                "place_order", "activate", "approve_trading"):
        assert not hasattr(e, bad), bad


def test_no_execution_in_source():
    base = os.path.dirname(os.path.dirname(__file__))
    for fn in ("engine.py", "models.py"):
        src = open(os.path.join(base, fn)).read()
        for bad in ("def run_live", "def execute", "def deploy", "def trade", "def go_live",
                    "def launch_live", "def place_order"):
            assert bad not in src, (fn, bad)


def test_forbidden_verbs_defined():
    for v in ("RUN_LIVE", "EXECUTE", "DEPLOY", "TRADE", "GO_LIVE"):
        assert M.is_forbidden_verb(v) is True
    assert M.is_forbidden_verb("PROPOSE") is False


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


def test_disclaimer_marks_not_trading():
    from jarvis.experiment_manager.engine import _DISCLAIMER
    assert "APPROVED_FOR_RESEARCH ≠ TRADING_APPROVAL" in _DISCLAIMER
    assert "PROPOSAL ≠ EXECUTION" in _DISCLAIMER


def test_all_requests_research_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    e.create_research_request(x, "", "RESEARCH", "", T3, commit=True)
    for r in ledger.read_requests():
        assert r["research_only"] is True
        assert r["trading_approval"] is False


def test_records_frozen():
    r = M.ResearchRequestRecord(request_id="EXR:x", experiment_id="EXM:e", plan_id="", scope="R",
                                justification="", research_only=True, trading_approval=False,
                                disclaimer="d", created_at=T0)
    with pytest.raises(Exception):
        r.trading_approval = True  # type: ignore


def test_only_exm_files_written(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    e.generate_experiment_plan(x, "m", [], "", [], "", T0, commit=True)
    e.review_experiment(x, "", T1, commit=True)
    e.approve_for_research(x, "", T2, commit=True)
    e.create_research_request(x, "", "RESEARCH", "", T3, commit=True)
    e.collect_results(x, {}, [], OUTCOME_SUPPORTED, "", T3, commit=True)
    e.generate_report(x, "EXPERIMENT", T4, commit=True)
    for fn in os.listdir(tmp_path):
        assert fn.startswith("exm_"), fn


# ══════════════ 커버리지: id 접두사·상수 ══════════════
def test_id_prefixes_distinct():
    ids = {M.experiment_id("t", "p", "h")[:4], M.event_id("e", "s")[:4], M.plan_id("e", "m")[:4],
           M.request_id("e", "s")[:4], M.result_id("e", T0)[:4], M.report_id("e", "s", T0)[:4]}
    assert len(ids) == 6


def test_five_owned_ledgers():
    assert len(ledger.ALL_LEDGERS) == 5
    fns = {l[0] for l in ledger.ALL_LEDGERS}
    assert len(fns) == 5
    assert all(f.startswith("exm_") for f in fns)


def test_four_outcomes():
    assert len(M.OUTCOMES) == 4


def test_can_transition_pure():
    assert M.can_transition(EXP_PROPOSED, EXP_REVIEWED) is True
    assert M.can_transition(EXP_PROPOSED, EXP_COMPLETED) is False


def test_content_hash_excludes_hash_fields():
    r = {"a": 1, "previous_hash": "p", "record_hash": "r"}
    assert M.content_hash(r) == M.content_hash({"a": 1, "previous_hash": "z", "record_hash": "q"})


def test_input_digest_deterministic():
    assert M.input_digest("a", "b") == M.input_digest("a", "b")
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


def test_research_states():
    assert M.RESEARCH_STATES == frozenset({EXP_APPROVED_FOR_RESEARCH, EXP_COMPLETED})


def test_plannable_states():
    assert M.PLANNABLE_STATES == frozenset({EXP_PROPOSED, EXP_REVIEWED})


def test_list_experiments(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    assert x in e.list_experiments()


# ══════════════ CLI ══════════════
def _run(argv, capsys):
    from jarvis.experiment_manager.__main__ import main
    rc = main(argv)
    return rc, capsys.readouterr().out


def test_cli_propose(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["propose", "--title", "T", "--hypothesis", "H", "--by", "a", "--commit"],
                   capsys)
    assert rc == 0
    assert json.loads(out)["experiment"]["to_state"] == "PROPOSED"


def test_cli_advance(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    rc, out = _run(["advance", "--exp", x, "--to", "REVIEWED", "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["experiment"]["to_state"] == "REVIEWED"


def test_cli_plan(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    rc, out = _run(["plan", "--exp", x, "--method", "m", "--vars", "a,b", "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["plan"]["variables"] == ["a", "b"]


def test_cli_request(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    rc, out = _run(["request", "--exp", x, "--scope", "RESEARCH", "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["request"]["trading_approval"] is False


def test_cli_results(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    rc, out = _run(["results", "--exp", x, "--outcome", "SUPPORTED", "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["result"]["outcome"] == "SUPPORTED"


def test_cli_status(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    rc, out = _run(["status", "--exp", x], capsys)
    assert rc == 0
    assert json.loads(out)["trading_approval"] is False


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    rc, out = _run(["report", "--exp", x, "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["report"]["trading_approval"] is False


def test_cli_experiments(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _exp(_eng())
    rc, out = _run(["experiments"], capsys)
    assert rc == 0
    assert len(json.loads(out)["experiments"]) == 1


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["verify"], capsys)
    assert rc == 0
    assert json.loads(out)["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _exp(_eng())
    rc, out = _run(["replay"], capsys)
    assert rc == 0
    assert json.loads(out)["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["summary"], capsys)
    assert rc == 0
    assert "experiment_count" in json.loads(out)


# ══════════════ 추가 커버리지 ══════════════
@pytest.mark.parametrize("frm,to,ok", [
    (EXP_PROPOSED, EXP_REVIEWED, True), (EXP_REVIEWED, EXP_APPROVED_FOR_RESEARCH, True),
    (EXP_APPROVED_FOR_RESEARCH, EXP_COMPLETED, True), (EXP_PROPOSED, EXP_APPROVED_FOR_RESEARCH, False),
    (EXP_PROPOSED, EXP_COMPLETED, False), (EXP_REVIEWED, EXP_COMPLETED, False),
    (EXP_COMPLETED, EXP_REVIEWED, False), (EXP_APPROVED_FOR_RESEARCH, EXP_REVIEWED, False),
])
def test_transition_matrix(frm, to, ok):
    assert M.can_transition(frm, to) is ok


@pytest.mark.parametrize("state", list(M.EXPERIMENT_STATES))
def test_each_state_reachable(tmp_path, monkeypatch, state):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    order = [EXP_REVIEWED, EXP_APPROVED_FOR_RESEARCH, EXP_COMPLETED]
    fns = {EXP_REVIEWED: e.review_experiment, EXP_APPROVED_FOR_RESEARCH: e.approve_for_research,
           EXP_COMPLETED: e.complete_experiment}
    t = 1
    for s in order:
        if e.current_state(x) == state:
            break
        fns[s](x, "", f"2026-07-24T00:0{t}:00Z", commit=True)
        t += 1
    assert e.current_state(x) == state


@pytest.mark.parametrize("verb", ["RUN_LIVE", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE",
                                  "GO_LIVE", "LAUNCH_LIVE", "PLACE_ORDER"])
def test_all_forbidden_verbs(verb):
    assert M.is_forbidden_verb(verb) is True


def test_propose_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().propose_experiment("T", "H", "a", "", T0, commit=False)
    assert ledger.read_experiment_events() == []


def test_plan_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    e.generate_experiment_plan(x, "m", [], "", [], "", T0, commit=False)
    assert ledger.read_plans() == []


def test_request_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    e.create_research_request(x, "", "RESEARCH", "", T3, commit=False)
    assert ledger.read_requests() == []


def test_results_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    e.collect_results(x, {}, [], OUTCOME_SUPPORTED, "", T3, commit=False)
    assert ledger.read_results() == []


def test_report_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    e.generate_report(x, "EXPERIMENT", T1, commit=False)
    assert ledger.read_reports() == []


def test_review_unknown_experiment(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownExperimentError):
        _eng().review_experiment("EXM:ghost", "", T0, commit=True)


def test_request_unknown_experiment(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownExperimentError):
        _eng().create_research_request("EXM:ghost", "", "R", "", T0, commit=True)


def test_results_unknown_experiment(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownExperimentError):
        _eng().collect_results("EXM:ghost", {}, [], OUTCOME_SUPPORTED, "", T0, commit=True)


def test_track_unknown_experiment(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownExperimentError):
        _eng().track_experiment_status("EXM:ghost")


def test_multiple_experiments_isolated(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x1 = _exp(e, "E1", "h1")
    x2 = _exp(e, "E2", "h2")
    e.generate_experiment_plan(x1, "m", [], "", [], "", T0, commit=True)
    assert len(ledger.experiment_plans(x1)) == 1
    assert len(ledger.experiment_plans(x2)) == 0


def test_experiments_in_state_approved(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    assert e.experiments_in_state(EXP_APPROVED_FOR_RESEARCH) == [x]


def test_history_grows_with_transitions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    assert len(e.track_experiment_status(x)["history"]) == 1
    e.review_experiment(x, "", T1, commit=True)
    assert len(e.track_experiment_status(x)["history"]) == 2


def test_plan_success_criteria_stored(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    p = e.generate_experiment_plan(x, "m", [], "d", ["sharpe>1", "t>2"], "", T0, commit=True)
    assert p.success_criteria == ["sharpe>1", "t>2"]


def test_result_findings_stored(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    r = e.collect_results(x, {}, ["f1", "f2"], OUTCOME_INCONCLUSIVE, "", T3, commit=True)
    assert r.findings == ["f1", "f2"]


def test_report_state_transitions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    r1 = e.generate_report(x, "EXPERIMENT", T1, commit=True)
    assert r1.lifecycle_state == EXP_PROPOSED
    e.review_experiment(x, "", T1, commit=True)
    r2 = e.generate_report(x, "EXPERIMENT", T2, commit=True)
    assert r2.lifecycle_state == EXP_REVIEWED


def test_request_records_research_only_field(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    r = e.create_research_request(x, "planid", "RESEARCH", "why", T3, commit=True)
    d = r.to_dict()
    assert d["research_only"] is True
    assert d["trading_approval"] is False
    assert d["plan_id"] == "planid"


def test_summary_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _approved(e)
    assert e.summary(T3).to_dict() == e.summary(T3).to_dict()


def test_plan_horizon_stored(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    p = e.generate_experiment_plan(x, "m", [], "", [], "quarterly", T0, commit=True)
    assert p.horizon == "quarterly"


def test_no_trading_approval_ever_true(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    e.create_research_request(x, "", "RESEARCH", "", T3, commit=True)
    e.complete_experiment(x, "", T4, commit=True)
    e.generate_report(x, "EXPERIMENT", "2026-07-24T00:06:00Z", commit=True)
    for r in ledger.read_requests() + ledger.read_reports():
        assert r["trading_approval"] is False


def test_plan_empty_variables(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    p = e.generate_experiment_plan(x, "m", None, "", None, "", T0, commit=True)
    assert p.variables == []
    assert p.success_criteria == []


def test_experiments_in_state_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().experiments_in_state(EXP_PROPOSED) == []


def test_report_experiment_id_field(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _exp(e)
    r = e.generate_report(x, "EXPERIMENT", T1, commit=True)
    assert r.experiment_id == x


def test_result_metrics_stored(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = _approved(e)
    r = e.collect_results(x, {"sharpe": 1.5, "maxdd": -0.1}, [], OUTCOME_SUPPORTED, "", T3,
                          commit=True)
    assert r.metrics["sharpe"] == 1.5


def test_experiment_id_varies():
    assert M.experiment_id("t1", "p", "h") != M.experiment_id("t2", "p", "h")
    assert M.plan_id("e", "m1") != M.plan_id("e", "m2")


# ══════════════ 통합 시나리오 ══════════════
def test_end_to_end_experiment(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    x = e.propose_experiment("Momentum decay study", "12m momentum decays after 2000",
                             "strategy_agent", "test decay", T0, commit=True).experiment_id
    plan = e.generate_experiment_plan(x, "cross_sectional_sort", ["ret_12m", "ret_1m"], "crsp",
                                      ["sharpe>0.5", "t>2"], "monthly", T0, commit=True)
    e.review_experiment(x, "design sound", T1, commit=True)
    e.approve_for_research(x, "research only", T2, commit=True)
    assert e.current_state(x) == EXP_APPROVED_FOR_RESEARCH
    req = e.create_research_request(x, plan.plan_id, "RESEARCH", "backtest only", T3, commit=True)
    assert req.research_only is True and req.trading_approval is False
    res = e.collect_results(x, {"sharpe": 0.6, "t": 2.3}, ["decays post-2000"], OUTCOME_SUPPORTED,
                            "confirmed", T3, commit=True)
    e.complete_experiment(x, "done", T4, commit=True)
    rep = e.generate_report(x, "EXPERIMENT", "2026-07-24T00:05:00Z", commit=True)
    assert rep.lifecycle_state == EXP_COMPLETED
    assert rep.result_count == 1
    assert rep.trading_approval is False
    from jarvis.experiment_manager.verify import verify_chain
    v = verify_chain()
    assert v["ok"] is True
    assert v["lifecycle"]["ok"] and v["trading_boundary"]["ok"]
    # 라이브 실행/거래 승인 흔적 없음
    assert all(not r["trading_approval"] for r in ledger.read_requests())
