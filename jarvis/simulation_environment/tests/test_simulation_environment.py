"""P10.8 Research Simulation Environment 테스트. **비실행 분석 전용.**

시나리오 레지스트리(불변)·생명주기(CREATED→CONFIGURED→USED→ARCHIVED, 차단전이)·시뮬레이션 런
(CREATED→RUNNING→COMPLETED→REVIEWED→ARCHIVED)·파라미터/레짐·결정적 결과·스트레스 스윕·비교(자동
추천 없음)·계보·verify(체인/변조/중복/계보/dangling/cycle/결정성)·replay·상위 READ ONLY 보호·CLI·
보안(금지import·실행/거래/배포/자본배분/권한 없음·상위 원장 무변경·삭제 API 없음·불변·result≠deployment·
append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from jarvis.simulation_environment import ledger
from jarvis.simulation_environment import models as M
from jarvis.simulation_environment.engine import ResearchSimulationEngine
from jarvis.simulation_environment.models import (
    ARCHIVED,
    COMPLETED,
    CONFIGURED,
    CREATED,
    CUSTOM,
    HIGH_VOLATILITY,
    LOW_LIQUIDITY,
    MARKET_STRESS,
    NORMAL,
    PARAMETER_SHIFT,
    REVIEWED,
    RUNNING,
    USED,
    IllegalTransition,
    ImmutableRunError,
    ImmutableScenarioError,
    UnknownRun,
    UnknownScenario,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.simulation_environment.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchSimulationEngine()


def _scn(eng, name="base", stype=NORMAL, commit=True):
    return eng.register_scenario(name, stype, "desc", {"k": name}, T0, commit=commit)


def _run(eng, scn_ref, cand="rg:ST1", params=None, seed="0", commit=True):
    return eng.create_simulation(cand, scn_ref, params or {}, "dg:DS1", seed, T0, commit=commit)


def _two_runs_with_results(eng):
    s = _scn(eng)
    ra = _run(eng, s.scenario_id, cand="rg:ST1", seed="1")
    rb = _run(eng, s.scenario_id, cand="rg:ST2", seed="2")
    eng.run_simulation_record(ra.run_id, T1, commit=True)
    eng.run_simulation_record(rb.run_id, T1, commit=True)
    return s, ra, rb


# ── Scenario Registry ──
def test_register_scenario(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _scn(eng)
    assert s.status == CREATED and s.scenario_type == NORMAL
    assert eng.scenario_state(s.scenario_id) == CREATED


def test_scenario_id_deterministic():
    a = M.scenario_id("n", NORMAL)
    assert a == M.scenario_id("n", NORMAL) and a.startswith("SSC:")


def test_scenario_commit_persists(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _scn(_eng(), commit=True)
    assert len(ledger.read_scenario_events()) == 1


def test_scenario_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _scn(_eng(), commit=False)
    assert ledger.read_scenario_events() == []


def test_scenario_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_scenario("s", NORMAL, "d", {"a": 1}, T0, commit=True)
    with pytest.raises(ImmutableScenarioError):
        eng.register_scenario("s", NORMAL, "d", {"a": 2}, T0, commit=True)


def test_scenario_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _scn(eng)
    _scn(eng)
    assert len(ledger.distinct_scenarios()) == 1


@pytest.mark.parametrize("stype", list(M.SCENARIO_TYPES))
def test_scenario_all_types(tmp_path, monkeypatch, stype):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = eng.register_scenario(f"s_{stype}", stype, "", {}, T0, commit=True)
    assert s.scenario_type == stype


def test_scenario_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _scn(eng)
    eng.transition_scenario(s.scenario_id, CONFIGURED, T1, commit=True)
    eng.transition_scenario(s.scenario_id, USED, T1, commit=True)
    eng.transition_scenario(s.scenario_id, ARCHIVED, T2, commit=True)
    assert eng.scenario_state(s.scenario_id) == ARCHIVED


def test_scenario_invalid_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _scn(eng)
    with pytest.raises(IllegalTransition):
        eng.transition_scenario(s.scenario_id, USED, T1, commit=True)  # CREATED→USED 차단


def test_scenario_archived_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _scn(eng)
    for to in (CONFIGURED, USED, ARCHIVED):
        eng.transition_scenario(s.scenario_id, to, T1, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition_scenario(s.scenario_id, CREATED, T2, commit=True)


def test_scenario_transition_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownScenario):
        _eng().transition_scenario("GHOST", CONFIGURED, T1, commit=True)


def test_scenario_transition_table():
    assert M.can_transition_scenario("", CREATED)
    assert M.can_transition_scenario(CREATED, CONFIGURED)
    assert M.can_transition_scenario(CONFIGURED, USED)
    assert not M.can_transition_scenario(CREATED, USED)
    assert not M.can_transition_scenario(ARCHIVED, USED)


def test_scenario_artifact_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _scn(eng)
    assert any(a["artifact_type"] == M.ART_SCENARIO and a["ref_id"] == s.scenario_id
               for a in ledger.read_artifacts())


# ── Simulation Run ──
def test_create_simulation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _scn(eng)
    r = _run(eng, s.scenario_id)
    assert r.status == CREATED and r.scenario_reference == s.scenario_id
    assert eng.run_state(r.run_id) == CREATED


def test_create_simulation_unknown_scenario(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    with pytest.raises(UnknownScenario):
        eng.create_simulation("rg:ST1", "GHOST", {}, "", "0", T0, commit=True)


def test_run_immutable_inputs(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _scn(eng)
    # 동일 run_id 지만 내용 상이는 발생 불가(run_id 가 입력 해시) — idempotent 확인
    r1 = _run(eng, s.scenario_id, params={"x": 1})
    r2 = _run(eng, s.scenario_id, params={"x": 1})
    assert r1.run_id == r2.run_id
    assert len(ledger.distinct_runs()) == 1


def test_run_different_params_different_run(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _scn(eng)
    r1 = _run(eng, s.scenario_id, params={"lookback": 50})
    r2 = _run(eng, s.scenario_id, params={"lookback": 100})
    assert r1.run_id != r2.run_id


def test_run_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _scn(eng)
    r = _run(eng, s.scenario_id)
    eng.transition_run(r.run_id, RUNNING, T1, commit=True)
    eng.transition_run(r.run_id, COMPLETED, T1, commit=True)
    eng.transition_run(r.run_id, REVIEWED, T2, commit=True)
    eng.transition_run(r.run_id, ARCHIVED, T2, commit=True)
    assert eng.run_state(r.run_id) == ARCHIVED


def test_run_invalid_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _scn(eng)
    r = _run(eng, s.scenario_id)
    with pytest.raises(IllegalTransition):
        eng.transition_run(r.run_id, COMPLETED, T1, commit=True)  # CREATED→COMPLETED 차단


def test_run_transition_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownRun):
        _eng().transition_run("GHOST", RUNNING, T1, commit=True)


def test_run_transition_table():
    assert M.can_transition_run("", CREATED)
    assert M.can_transition_run(CREATED, RUNNING)
    assert M.can_transition_run(RUNNING, COMPLETED)
    assert M.can_transition_run(COMPLETED, REVIEWED)
    assert not M.can_transition_run(CREATED, REVIEWED)


def test_run_artifact_parent_scenario(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _scn(eng)
    r = _run(eng, s.scenario_id)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    ra = arts[M.artifact_id(M.ART_RUN, r.run_id)]
    assert ra["parent_artifact"] == M.artifact_id(M.ART_SCENARIO, s.scenario_id)
    assert ra["parent_artifact"] in arts


# ── Parameter / Regime ──
def test_attach_parameters(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = eng.attach_parameters("lookback_sweep", M.LOOKBACK, {"values": [50, 100, 200]}, T0,
                              commit=True)
    assert p.category == M.LOOKBACK
    assert len(ledger.read_parameters()) == 1


def test_parameter_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.attach_parameters("p", M.COST_SHOCK, {"mult": 2}, T0, commit=True)
    eng.attach_parameters("p", M.COST_SHOCK, {"mult": 2}, T0, commit=True)
    assert len(ledger.read_parameters()) == 1


@pytest.mark.parametrize("cat", list(M.PARAMETER_CATEGORIES))
def test_parameter_categories(tmp_path, monkeypatch, cat):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = eng.attach_parameters(f"p_{cat}", cat, {"v": 1}, T0, commit=True)
    assert p.category == cat


def test_define_regime(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = eng.define_regime("bull_2020", M.BULL, {"drift": 0.1}, T0, commit=True)
    assert r.regime == M.BULL
    assert len(ledger.read_regimes()) == 1


@pytest.mark.parametrize("reg", list(M.REGIMES))
def test_all_regimes(tmp_path, monkeypatch, reg):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = eng.define_regime(f"r_{reg}", reg, {}, T0, commit=True)
    assert r.regime == reg


def test_regime_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.define_regime("r", M.BEAR, {}, T0, commit=True)
    eng.define_regime("r", M.BEAR, {}, T0, commit=True)
    assert len(ledger.read_regimes()) == 1


# ── 결정적 결과 ──
def test_derive_metrics_deterministic():
    m1 = M.derive_metrics("run:seed")
    m2 = M.derive_metrics("run:seed")
    assert m1 == m2
    assert set(m1) == set(M.RESULT_METRICS)


def test_derive_metrics_varies_by_input():
    assert M.derive_metrics("a") != M.derive_metrics("b")


def test_derive_metrics_ranges():
    m = M.derive_metrics("x")
    assert -0.2 <= m["return"] <= 0.4
    assert 0.05 <= m["volatility"] <= 0.4
    assert -0.5 <= m["max_drawdown"] <= -0.02
    assert 0.0 <= m["stability_score"] <= 1.0


def test_run_simulation_record(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _scn(eng)
    r = _run(eng, s.scenario_id, seed="7")
    res = eng.run_simulation_record(r.run_id, T1, commit=True)
    assert res.run_id == r.run_id
    assert set(res.metrics) == set(M.RESULT_METRICS)
    assert len(ledger.read_results()) == 1


def test_run_simulation_result_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _scn(eng)
    r = _run(eng, s.scenario_id, seed="7")
    res1 = eng.run_simulation_record(r.run_id, T1, commit=True)
    res2 = eng.run_simulation_record(r.run_id, T1, commit=True)  # idempotent
    assert res1.metrics == res2.metrics
    assert len(ledger.read_results()) == 1


def test_run_record_advances_run_and_scenario(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _scn(eng)
    r = _run(eng, s.scenario_id)
    eng.run_simulation_record(r.run_id, T1, commit=True)
    assert eng.run_state(r.run_id) == COMPLETED
    assert eng.scenario_state(s.scenario_id) == USED


def test_run_record_missing_run(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownRun):
        _eng().run_simulation_record("GHOST", T1, commit=True)


def test_record_result_explicit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _scn(eng)
    r = _run(eng, s.scenario_id)
    res = eng.record_result(r.run_id, {"return": 0.1, "sharpe": 1.2}, T1, commit=True)
    assert res.metrics["return"] == 0.1 and res.deterministic_input.startswith("explicit:")


def test_record_result_missing_run(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownRun):
        _eng().record_result("GHOST", {"return": 0.1}, T1, commit=True)


def test_result_artifact_parent_run(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _scn(eng)
    r = _run(eng, s.scenario_id)
    res = eng.run_simulation_record(r.run_id, T1, commit=True)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    ra = arts[M.artifact_id(M.ART_RESULT, res.result_id)]
    assert ra["parent_artifact"] == M.artifact_id(M.ART_RUN, r.run_id)
    assert ra["parent_artifact"] in arts


# ── Stress: parameter sweep ──
def test_parameter_sweep(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _scn(eng, "sens", PARAMETER_SHIFT)
    out = eng.parameter_sweep("rg:ST1", s.scenario_id, "lookback", [50, 100, 200],
                              M.LOOKBACK, "dg:DS1", T1, commit=True)
    assert len(out) == 3
    assert len({o["run_id"] for o in out}) == 3  # 값마다 다른 런
    assert len(ledger.read_results()) == 3


def test_parameter_sweep_sensitivity_varies(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _scn(eng, "sens", PARAMETER_SHIFT)
    out = eng.parameter_sweep("rg:ST1", s.scenario_id, "lookback", [50, 100], M.LOOKBACK,
                              "dg:DS1", T1, commit=True)
    # 서로 다른 seed → 서로 다른 결정적 결과(민감도)
    assert out[0]["metrics"] != out[1]["metrics"]


def test_parameter_sweep_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _scn(eng, "sens", PARAMETER_SHIFT)
    o1 = eng.parameter_sweep("rg:ST1", s.scenario_id, "lookback", [50], M.LOOKBACK, "dg:DS1",
                             T1, commit=True)
    m1 = o1[0]["metrics"]
    eng2 = _eng()
    m2 = M.derive_metrics(f"{o1[0]['run_id']}:50")
    assert m1 == m2


def test_stress_market_regime_scenario(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_scenario("stress_2008", MARKET_STRESS, "", {}, T0, commit=True)
    eng.define_regime("crisis", M.BEAR, {"vol": 0.5}, T0, commit=True)
    assert len(ledger.read_regimes()) == 1


# ── Comparison ──
def test_compare_results(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s, ra, rb = _two_runs_with_results(eng)
    c = eng.compare_results(ra.run_id, rb.run_id, T2, commit=True)
    assert set(c.dimensions) == {"performance", "stability", "risk", "sensitivity"}
    assert c.dimensions["performance"]["symbol"] in (">", "<", "≈")


def test_compare_no_recommendation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s, ra, rb = _two_runs_with_results(eng)
    c = eng.compare_results(ra.run_id, rb.run_id, T2, commit=True)
    assert "자동 추천" in c.note and "recommendation" not in c.to_dict()


def test_compare_symmetric_id(tmp_path, monkeypatch):
    assert M.comparison_id("A", "B") == M.comparison_id("B", "A")


def test_compare_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s, ra, rb = _two_runs_with_results(eng)
    eng.compare_results(ra.run_id, rb.run_id, T2, commit=True)
    eng.compare_results(rb.run_id, ra.run_id, T2, commit=True)
    assert len(ledger.read_comparisons()) == 1


def test_compare_symbol_helper():
    assert M.compare_symbol(0.1) == ">"
    assert M.compare_symbol(-0.1) == "<"
    assert M.compare_symbol(0.0) == "≈"


def test_compare_risk_lower_is_better(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _scn(eng)
    ra = _run(eng, s.scenario_id, cand="rg:A", seed="1")
    rb = _run(eng, s.scenario_id, cand="rg:B", seed="2")
    eng.record_result(ra.run_id, {"volatility": 0.1, "sharpe": 1.0, "stability_score": 0.5,
                                  "turnover": 1.0}, T1, commit=True)
    eng.record_result(rb.run_id, {"volatility": 0.3, "sharpe": 1.0, "stability_score": 0.5,
                                  "turnover": 1.0}, T1, commit=True)
    c = eng.compare_results(ra.run_id, rb.run_id, T2, commit=True)
    # risk dim = b.vol - a.vol = 0.3-0.1 = 0.2 > 0 → a 가 더 낮은 리스크(">" = a 우위)
    assert c.dimensions["risk"]["symbol"] == ">"


# ── source READ ONLY ──
def _seed(sp, filename, rows):
    with open(sp(filename), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_list_source_candidates(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "rg_strategies.jsonl", [{"strategy_id": "ST1"}, {"strategy_id": "ST2"}])
    refs = _eng().list_source_candidates("STRATEGY")
    assert refs == ["research_governance:ST1", "research_governance:ST2"]


def test_list_source_limit(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "ai_signals.jsonl", [{"signal_id": f"S{i}"} for i in range(5)])
    assert len(_eng().list_source_candidates("SIGNAL", limit=2)) == 2


def test_list_source_unknown_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().list_source_candidates("NOPE") == []


def test_list_source_does_not_mutate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "pr_portfolios.jsonl", [{"portfolio_id": "P1"}])
    before = hashlib.sha256(open(sp("pr_portfolios.jsonl"), "rb").read()).hexdigest()
    _eng().list_source_candidates("PORTFOLIO")
    after = hashlib.sha256(open(sp("pr_portfolios.jsonl"), "rb").read()).hexdigest()
    assert before == after


def test_source_map_covers_five_layers():
    assert set(ledger.SOURCE_LEDGERS) == {"STRATEGY", "SIGNAL", "PORTFOLIO", "GRAPH", "DECISION"}


# ── Report ──
def test_report_totals(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s, ra, rb = _two_runs_with_results(eng)
    eng.compare_results(ra.run_id, rb.run_id, T2, commit=True)
    rep = eng.generate_report(T2)
    assert rep.scenario_count == 1 and rep.run_count == 2
    assert rep.result_count == 2 and rep.comparison_count == 1


def test_report_distributions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s, ra, rb = _two_runs_with_results(eng)
    rep = eng.generate_report(T2)
    assert rep.run_state_distribution.get(COMPLETED) == 2
    assert rep.scenario_type_distribution.get(NORMAL) == 1


def test_report_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _two_runs_with_results(eng)
    assert eng.generate_report(T2).to_dict() == eng.generate_report(T2).to_dict()


def test_report_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    rep = _eng().generate_report(T0)
    assert rep.scenario_count == 0 and rep.run_count == 0


# ── verify ──
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.simulation_environment.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_full_scenario_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.simulation_environment.verify import verify_chain
    eng = _eng()
    s, ra, rb = _two_runs_with_results(eng)
    eng.compare_results(ra.run_id, rb.run_id, T2, commit=True)
    res = verify_chain()
    assert res["ok"] is True
    assert res["lineage"]["ok"] is True and res["determinism"]["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.simulation_environment.verify import verify_chain
    eng = _eng()
    _scn(eng)
    recs = ledger.read_scenario_events()
    recs[0]["name"] = "TAMPERED"
    with open(sp("sim_scenarios.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_chain_break(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.simulation_environment.verify import verify_ledger
    eng = _eng()
    _scn(eng, "a")
    _scn(eng, "b")
    recs = ledger.read_scenario_events()
    recs[1]["previous_hash"] = "GENESIS"
    with open(sp("sim_scenarios.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_ledger(ledger.SCENARIOS)["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.simulation_environment.verify import verify_ledger
    eng = _eng()
    _scn(eng)
    recs = ledger.read_scenario_events()
    dup = dict(recs[0])
    dup["previous_hash"] = recs[0]["record_hash"]
    with open(sp("sim_scenarios.jsonl"), "a") as f:
        f.write(json.dumps(dup) + "\n")
    assert verify_ledger(ledger.SCENARIOS)["ok"] is False


def test_verify_detects_dangling_result(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.simulation_environment.verify import lineage_validation
    rec = {"result_id": "SRS:x", "run_id": "SRN:ghost", "metrics": {}, "deterministic_input": "e",
           "created_at": T0, "previous_hash": "GENESIS"}
    rec["record_hash"] = M.content_hash(rec)
    with open(sp("sim_results.jsonl"), "w") as f:
        f.write(json.dumps(rec) + "\n")
    res = lineage_validation()
    assert res["ok"] is False
    assert any("dangling_result_run" in i for i in res["issues"])


def test_verify_detects_cycle(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.simulation_environment.verify import lineage_validation
    a1 = {"artifact_id": "A1", "artifact_type": "X", "ref_id": "r", "parent_artifact": "A2",
          "created_at": T0, "previous_hash": "GENESIS"}
    a1["record_hash"] = M.content_hash(a1)
    a2 = {"artifact_id": "A2", "artifact_type": "X", "ref_id": "r", "parent_artifact": "A1",
          "created_at": T0, "previous_hash": a1["record_hash"]}
    a2["record_hash"] = M.content_hash(a2)
    with open(sp("sim_artifacts.jsonl"), "w") as f:
        f.write(json.dumps(a1) + "\n")
        f.write(json.dumps(a2) + "\n")
    assert any("circular_dependency" in i for i in lineage_validation()["issues"])


def test_verify_detects_nondeterministic_result(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.simulation_environment.verify import result_determinism
    # deterministic_input 이 있지만 metrics 가 파생값과 불일치(변조)
    rec = {"result_id": "SRS:x", "run_id": "SRN:1", "metrics": {"return": 999.0},
           "deterministic_input": "SRN:1:0", "created_at": T0, "previous_hash": "GENESIS"}
    rec["record_hash"] = M.content_hash(rec)
    with open(sp("sim_results.jsonl"), "w") as f:
        f.write(json.dumps(rec) + "\n")
    res = result_determinism()
    assert res["ok"] is False
    assert any("nondeterministic_result" in i for i in res["issues"])


def test_detect_cycle_helper():
    assert M.detect_cycle([("a", "b"), ("b", "a")]) == ["a", "b", "a"]
    assert M.detect_cycle([("a", "b")]) == []


# ── replay ──
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.simulation_environment.verify import replay
    eng = _eng()
    _two_runs_with_results(eng)
    assert replay(eng, T2)["deterministic"] is True


# ── content hash ──
def test_content_hash_excludes_chain_fields():
    a = {"x": 1, "previous_hash": "A", "record_hash": "B", "report_hash": "C"}
    b = {"x": 1, "previous_hash": "Z", "record_hash": "Z", "report_hash": "Z"}
    assert M.content_hash(a) == M.content_hash(b)


def test_params_hash_stable():
    assert M.params_hash({"a": 1, "b": 2}) == M.params_hash({"b": 2, "a": 1})


# ── CLI ──
def test_cli_scenario_and_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.simulation_environment.__main__ import main
    rc = main(["scenario", "--name", "base", "--type", NORMAL, "--commit"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["scenario"]["scenario_type"] == NORMAL
    main(["summary"])
    assert json.loads(capsys.readouterr().out)["scenario_count"] == 1


def test_cli_full_workflow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.simulation_environment.__main__ import main
    main(["scenario", "--name", "base", "--type", NORMAL, "--commit"])
    sid = json.loads(capsys.readouterr().out)["scenario"]["scenario_id"]
    main(["run", "--candidate", "rg:ST1", "--scenario-id", sid, "--seed", "1", "--commit"])
    ra = json.loads(capsys.readouterr().out)["run"]["run_id"]
    main(["run", "--candidate", "rg:ST2", "--scenario-id", sid, "--seed", "2", "--commit"])
    rb = json.loads(capsys.readouterr().out)["run"]["run_id"]
    main(["result", "--run-id", ra, "--commit"])
    main(["result", "--run-id", rb, "--commit"])
    capsys.readouterr()
    main(["compare", "--run-a", ra, "--run-b", rb, "--commit"])
    c = json.loads(capsys.readouterr().out)["comparison"]
    assert "note" in c and set(c["dimensions"]) == {"performance", "stability", "risk",
                                                     "sensitivity"}
    rc = main(["verify"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_result_explicit_metrics(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.simulation_environment.__main__ import main
    main(["scenario", "--name", "b", "--type", NORMAL, "--commit"])
    sid = json.loads(capsys.readouterr().out)["scenario"]["scenario_id"]
    main(["run", "--candidate", "rg:X", "--scenario-id", sid, "--commit"])
    rid = json.loads(capsys.readouterr().out)["run"]["run_id"]
    capsys.readouterr()
    main(["result", "--run-id", rid, "--metrics-json", json.dumps({"return": 0.2}), "--commit"])
    out = json.loads(capsys.readouterr().out)["result"]
    assert out["metrics"]["return"] == 0.2


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.simulation_environment.__main__ import main
    main(["scenario", "--name", "b", "--type", NORMAL, "--commit"])
    capsys.readouterr()
    rc = main(["replay"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_verify_empty_zero(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.simulation_environment.__main__ import main
    assert main(["verify"]) == 0
    capsys.readouterr()


# ── 보안·불변·READ ONLY 가드 ──
def test_no_forbidden_imports():
    import jarvis.simulation_environment.engine as eng_mod
    import jarvis.simulation_environment.models as mdl_mod
    import jarvis.simulation_environment.ledger as led_mod
    import jarvis.simulation_environment.verify as ver_mod
    src = ""
    for m in (eng_mod, mdl_mod, led_mod, ver_mod):
        with open(m.__file__) as f:
            src += f.read()
    _j = "jarvis."
    forbidden = [_j + "live_execution", _j + "broker", _j + "order",
                 _j + "portfolio.", _j + "risk_governor", _j + "permission",
                 "place_order(", "submit_order(", "execute_trade(", "deploy_strategy(",
                 "allocate_capital(", "promote_model(", "activate_live("]
    for token in forbidden:
        assert token not in src, f"forbidden reference: {token}"


def test_no_execution_authority_api():
    api = set(dir(ResearchSimulationEngine))
    for banned in ("execute", "trade", "place_order", "allocate", "deploy", "promote",
                   "activate_live", "approve_for_trading", "submit_order"):
        assert banned not in api


def test_result_not_deployment(tmp_path, monkeypatch):
    """결과·비교에 배포·선택·승인 필드가 없어야 한다 — 연구 기록일 뿐."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s, ra, rb = _two_runs_with_results(eng)
    res = ledger.read_results()[0]
    for banned in ("deployed", "selected", "approved", "deployable", "live"):
        assert banned not in res


def test_no_deploy_or_select_method():
    eng = ResearchSimulationEngine()
    assert not hasattr(eng, "deploy_run")
    assert not hasattr(eng, "select_winner")
    assert not hasattr(eng, "promote_result")


def test_live_execution_disabled_invariant():
    import jarvis.config as _cfg
    assert _cfg.live_execution_enabled() is False
    assert _cfg.AUTONOMY_LEVEL < _cfg.MIN_LIVE_LEVEL


def test_no_delete_or_update_api():
    import importlib
    for mod_name in ("engine", "ledger"):
        m = importlib.import_module(f"jarvis.simulation_environment.{mod_name}")
        for attr in dir(m):
            low = attr.lower()
            assert not low.startswith("delete_")
            assert not low.startswith("update_")
            assert not low.startswith("remove_")


def test_ledgers_namespaced_sim_prefix():
    for filename, _ in ledger.ALL_LEDGERS:
        assert filename.startswith("sim_")


def test_no_collision_with_simulation_prefix():
    """sim_ 원장이 기존 execution paper-sim(simulation_) 및 타 레이어와 겹치지 않아야 한다."""
    ours = {fn for fn, _ in ledger.ALL_LEDGERS}
    known = {"simulation_orders.jsonl", "simulation_fills.jsonl", "simulation_reports.jsonl",
             "rg_strategies.jsonl", "ai_signals.jsonl", "pr_portfolios.jsonl",
             "kg_entities.jsonl", "di_candidates.jsonl", "arg_agents.jsonl"}
    assert ours.isdisjoint(known)
    assert all(fn.startswith("sim_") and not fn.startswith("simulation_") for fn in ours)


def test_source_ledgers_read_only_not_owned():
    owned = {fn for fn, _ in ledger.ALL_LEDGERS}
    for rt, (layer, fn, idf) in ledger.SOURCE_LEDGERS.items():
        assert fn not in owned


def test_existing_source_ledgers_untouched(tmp_path, monkeypatch):
    """상위 P10.2~P10.7 원장을 시드한 뒤 전체 워크플로를 돌려도 원본 SHA256 불변."""
    sp = _iso(tmp_path, monkeypatch)
    seeds = {"rg_strategies.jsonl": [{"strategy_id": "ST1"}],
             "ai_signals.jsonl": [{"signal_id": "SG1"}],
             "pr_portfolios.jsonl": [{"portfolio_id": "PF1"}],
             "kg_entities.jsonl": [{"entity_id": "KGE:1"}],
             "di_candidates.jsonl": [{"candidate_id": "DIC:1"}]}
    hashes = {}
    for fn, rows in seeds.items():
        _seed(sp, fn, rows)
        hashes[fn] = hashlib.sha256(open(sp(fn), "rb").read()).hexdigest()
    eng = _eng()
    refs = eng.list_source_candidates("STRATEGY")
    s = _scn(eng)
    r = _run(eng, s.scenario_id, cand=refs[0] if refs else "rg:ST1")
    eng.run_simulation_record(r.run_id, T1, commit=True)
    eng.generate_report(T2, commit=True)
    for fn, h in hashes.items():
        assert hashlib.sha256(open(sp(fn), "rb").read()).hexdigest() == h


def test_engine_only_appends_sim_files(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    s, ra, rb = _two_runs_with_results(eng)
    eng.compare_results(ra.run_id, rb.run_id, T2, commit=True)
    created = [f for f in os.listdir(tmp_path) if f.endswith(".jsonl")]
    assert created and all(f.startswith("sim_") for f in created)


def test_config_unchanged_after_simulation(tmp_path, monkeypatch):
    """시뮬레이션 실행 후 config/AUTONOMY_LEVEL/live gate 불변."""
    import jarvis.config as _cfg
    lvl_before = _cfg.AUTONOMY_LEVEL
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _two_runs_with_results(eng)
    assert _cfg.AUTONOMY_LEVEL == lvl_before
    assert _cfg.live_execution_enabled() is False


# ── 추가: ID/헬퍼/계보 세부 ──
def test_run_id_deterministic():
    a = M.run_id("c", "s", "ph", "d", "0")
    assert a == M.run_id("c", "s", "ph", "d", "0") and a.startswith("SRN:")


def test_run_id_varies_by_seed():
    assert M.run_id("c", "s", "ph", "d", "0") != M.run_id("c", "s", "ph", "d", "1")


def test_regime_id_deterministic():
    assert M.regime_id("n", M.BULL).startswith("SRG:")
    assert M.regime_id("n", M.BULL) == M.regime_id("n", M.BULL)


def test_parameter_id_varies():
    assert M.parameter_id("n", M.LOOKBACK, {"a": 1}) != M.parameter_id("n", M.LOOKBACK, {"a": 2})


def test_result_id_from_run():
    assert M.result_id("SRN:x").startswith("SRS:")


def test_artifact_id_prefix():
    assert M.artifact_id(M.ART_RUN, "x").startswith("SIA:")


def test_scenario_metadata_hash_immutable_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s1 = eng.register_scenario("s", NORMAL, "d", {"a": 1}, T0, commit=True)
    s2 = eng.register_scenario("s", NORMAL, "d", {"a": 1}, T0, commit=True)
    assert s1.metadata_hash == s2.metadata_hash  # 동일 내용 idempotent


def test_report_artifact_recorded_on_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s, ra, rb = _two_runs_with_results(eng)
    eng.compare_results(ra.run_id, rb.run_id, T2, commit=True)
    eng.generate_report(T2, commit=True)
    assert any(a["artifact_type"] == M.ART_REPORT for a in ledger.read_artifacts())


def test_compare_with_missing_results_no_crash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = _scn(eng)
    ra = _run(eng, s.scenario_id, cand="rg:A", seed="1")
    rb = _run(eng, s.scenario_id, cand="rg:B", seed="2")
    # 결과 미기록 상태에서 비교 → 0 값으로 안전 처리
    c = eng.compare_results(ra.run_id, rb.run_id, T2, commit=True)
    assert c.dimensions["performance"]["a"] == 0.0


def test_list_source_all_five_types(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "rg_strategies.jsonl", [{"strategy_id": "S"}])
    _seed(sp, "ai_signals.jsonl", [{"signal_id": "G"}])
    _seed(sp, "pr_portfolios.jsonl", [{"portfolio_id": "P"}])
    _seed(sp, "kg_entities.jsonl", [{"entity_id": "E"}])
    _seed(sp, "di_candidates.jsonl", [{"candidate_id": "C"}])
    eng = _eng()
    total = sum(len(eng.list_source_candidates(rt))
                for rt in ("STRATEGY", "SIGNAL", "PORTFOLIO", "GRAPH", "DECISION"))
    assert total == 5


def test_full_scenario_lineage_intact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.simulation_environment.verify import lineage_validation
    eng = _eng()
    s, ra, rb = _two_runs_with_results(eng)
    eng.compare_results(ra.run_id, rb.run_id, T2, commit=True)
    res = lineage_validation()
    assert res["ok"] is True and not res["issues"]


def test_result_metrics_names_complete():
    assert set(M.RESULT_METRICS) == {"return", "volatility", "sharpe", "max_drawdown",
                                     "turnover", "stability_score", "confidence"}
