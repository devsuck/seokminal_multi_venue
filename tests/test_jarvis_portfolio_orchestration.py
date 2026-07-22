"""P2.4 Portfolio Orchestration Layer 테스트.

Scheduler · Journal · Turnover · StateMachine · 통합 dry-run.
가드: append-only · audit · 결정성 · 불법전이 거부 · dry-run 무변경.
"""
from __future__ import annotations

import os

import pytest

from jarvis.portfolio.decision_engine import CurrentPortfolio
from jarvis.portfolio.journal import PortfolioDecisionRecord, read_all as journal_read, record_decision
from jarvis.portfolio.orchestrator import PortfolioOrchestrator
from jarvis.portfolio.scheduler import (
    EvaluationContext,
    SchedulerConfig,
    should_evaluate,
)
from jarvis.portfolio.state import (
    IllegalPortfolioTransition,
    PortfolioState,
    PortfolioStateMachine,
)
from jarvis.portfolio.turnover import (
    TurnoverConfig,
    check_turnover,
    current_period_turnover,
)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    import jarvis.audit.log as al
    import jarvis.portfolio.journal as jm
    import jarvis.portfolio.state as stt
    import jarvis.portfolio.turnover as tv
    monkeypatch.setattr(al, "state_path", sp)
    monkeypatch.setattr(jm, "state_path", sp)
    monkeypatch.setattr(tv, "state_path", sp)
    # state machine reads path at init → patch module state_path
    monkeypatch.setattr(stt, "state_path", sp)
    return tmp_path, sp


# ─────────────────────── Scheduler ───────────────────────────
def test_scheduler_daily_trigger():
    ctx = EvaluationContext(now="2026-07-22", last_eval="2026-07-21")
    d = should_evaluate(ctx, SchedulerConfig(frequency="daily"))
    assert d.should_run and d.trigger_type == "time"


def test_scheduler_weekly_trigger():
    due = should_evaluate(EvaluationContext(now="2026-07-22", last_eval="2026-07-15"),
                          SchedulerConfig(frequency="weekly"))
    not_due = should_evaluate(EvaluationContext(now="2026-07-18", last_eval="2026-07-15"),
                              SchedulerConfig(frequency="weekly"))
    assert due.should_run is True
    assert not_due.should_run is False


def test_scheduler_no_trigger():
    ctx = EvaluationContext(now="2026-07-22", last_eval="2026-07-22")
    d = should_evaluate(ctx, SchedulerConfig(frequency="daily"))
    assert d.should_run is False and d.trigger_type == "none"


def test_scheduler_regime_change_trigger():
    ctx = EvaluationContext(now="2026-07-22", last_eval="2026-07-22",  # 시간상 미도래
                            current_regime="bear_high_vol", previous_regime="bull_low_vol")
    d = should_evaluate(ctx, SchedulerConfig(frequency="daily"))
    assert d.should_run and "regime_change" in d.triggers


def test_scheduler_drift_trigger():
    ctx = EvaluationContext(now="2026-07-22", last_eval="2026-07-22", weight_drift=0.15)
    d = should_evaluate(ctx, SchedulerConfig(drift_trigger=0.10))
    assert d.should_run and "drift" in d.triggers


def test_scheduler_drawdown_and_new_strategy():
    dd = should_evaluate(EvaluationContext(now="2026-07-22", last_eval="2026-07-22",
                                           current_drawdown=0.15, previous_drawdown=0.05),
                         SchedulerConfig(drawdown_trigger=0.10))
    assert "drawdown" in dd.triggers
    ns = should_evaluate(EvaluationContext(now="2026-07-22", last_eval="2026-07-22",
                                           active_strategies=["A", "B"], previous_active=["A"]))
    assert "new_strategy" in ns.triggers


# ─────────────────────── Journal ─────────────────────────────
def _rec(decision="HOLD"):
    return PortfolioDecisionRecord(timestamp="T", inputs={"regime": "bull_low_vol"},
                                   before={"A": 0.5}, after={"A": 0.6}, decision=decision,
                                   reasons=["r"], blockers=[])


def test_journal_append_only_and_audit():
    record_decision(_rec("REBALANCE"))
    record_decision(_rec("HOLD"))
    rows = journal_read()
    assert len(rows) == 2 and rows[0]["decision"] == "REBALANCE"
    import jarvis.audit.log as al
    audit = al.read_all()
    assert any(a.get("action") == "write_portfolio_journal" and a.get("result") == "written"
               for a in audit)


def test_journal_rejects_bad_decision():
    with pytest.raises(ValueError):
        record_decision(_rec("MAYBE"))


def test_journal_deterministic_output():
    assert _rec("HOLD").to_dict() == _rec("HOLD").to_dict()


# ─────────────────────── Turnover ────────────────────────────
def test_turnover_within_budget():
    rows = [{"timestamp": "2026-07-05", "turnover": 0.05}]
    c = check_turnover(0.10, "2026-07-22", TurnoverConfig(budget=0.20), rows=rows)
    assert c.approved is True and c.current_turnover == 0.05


def test_turnover_exceed_budget():
    rows = [{"timestamp": "2026-07-05", "turnover": 0.18}]
    c = check_turnover(0.10, "2026-07-22", TurnoverConfig(budget=0.20), rows=rows)
    assert c.approved is False and "budget_exceeded" in c.reason


def test_turnover_reset_next_period():
    rows = [{"timestamp": "2026-06-30", "turnover": 0.18}]   # 전월
    assert current_period_turnover("2026-07-22", rows, "monthly") == 0.0
    c = check_turnover(0.10, "2026-07-22", TurnoverConfig(budget=0.20), rows=rows)
    assert c.approved is True                                 # 새 기간 예산 리셋


# ─────────────────────── State Machine ───────────────────────
def test_state_valid_transitions():
    sm = PortfolioStateMachine()
    assert sm.current() == "INITIALIZING"
    sm.transition(PortfolioState.MONITORING, "boot", "T")
    sm.transition(PortfolioState.REBALANCE_PENDING, "reb", "T")
    sm.transition(PortfolioState.REBALANCED, "done", "T")
    sm.transition(PortfolioState.MONITORING, "back", "T")
    assert sm.current() == "MONITORING"
    assert len(sm.history()) == 4


def test_state_invalid_transition_rejected():
    sm = PortfolioStateMachine()
    with pytest.raises(IllegalPortfolioTransition):
        sm.transition(PortfolioState.REBALANCED, "skip", "T")   # INITIALIZING→REBALANCED 불법
    import jarvis.audit.log as al
    assert any(a.get("layer") == "portfolio_state" and a.get("result") == "denied"
               for a in al.read_all())


def test_state_deterministic_replay():
    sm = PortfolioStateMachine()
    sm.transition(PortfolioState.MONITORING, "b", "T")
    sm.transition(PortfolioState.RISK_REDUCTION, "risk", "T")
    # 새 인스턴스가 같은 원장에서 동일 상태 폴드
    sm2 = PortfolioStateMachine()
    assert sm2.current() == "RISK_REDUCTION"
    assert [e["new_state"] for e in sm2.history()] == ["MONITORING", "RISK_REDUCTION"]


# ─────────────────────── Integration ─────────────────────────
N = 40
DATES = [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(N)]


class FakeMatrix:
    def __init__(self, series):
        self._d = DATES
        self._s = series

    def calendar(self):
        return list(self._d)

    def aligned(self, cal):
        idx = [self._d.index(d) for d in cal]
        return cal, {k: [v[i] for i in idx] for k, v in self._s.items()}

    def build(self):
        from jarvis.portfolio.returns_matrix import StrategyReturnSeries
        out = {}
        for k, v in self._s.items():
            out[k] = StrategyReturnSeries(k, self._d, v, [1.0] * len(v), [1.0] * len(v),
                                          any(abs(x) > 1e-12 for x in v), "test")
        return out

    def correlation(self, calendar=None):
        from jarvis.fusion.backtest import avg_pairwise_corr
        return avg_pairwise_corr(self._s)


def _two_strat_matrix():
    a = [0.01 if i % 2 == 0 else -0.008 for i in range(N)]
    b = [-0.006 if i % 3 == 0 else 0.007 for i in range(N)]
    return FakeMatrix({"A": a, "B": b})


def _fake_regime(label="bull_low_vol"):
    return lambda returns: {"current_regime": label}


def test_integration_dry_run_no_mutation():
    mat = _two_strat_matrix()
    cur = CurrentPortfolio({"A": 0.4, "B": 0.6}, last_rebalance="2026-06-01")
    res = PortfolioOrchestrator().evaluate(
        mat, cur, now="2026-07-22", ts="2026-07-22T00:00:00Z",
        regime_detector=_fake_regime("bull_low_vol"), dry_run=True)
    assert res["dry_run"] is True and res["mutated"] is False
    assert res["decision"] in {"REBALANCE", "HOLD", "RISK_REDUCTION", "BLOCKED"}
    # dry-run → 어떤 원장도 안 씀
    from jarvis.portfolio.journal import read_all as jr
    from jarvis.portfolio.state import PortfolioStateMachine as SM
    assert jr() == []
    assert SM().current() == "INITIALIZING"


def test_integration_commit_writes_journal_and_state():
    mat = _two_strat_matrix()
    cur = CurrentPortfolio({"A": 0.4, "B": 0.6}, last_rebalance="2026-06-01")
    res = PortfolioOrchestrator().evaluate(
        mat, cur, now="2026-07-22", ts="2026-07-22T00:00:00Z",
        regime_detector=_fake_regime("bull_low_vol"), dry_run=False)
    assert res["mutated"] is True
    from jarvis.portfolio.journal import read_all as jr
    from jarvis.portfolio.state import PortfolioStateMachine as SM
    assert len(jr()) == 1                                   # 저널 1건
    assert SM().current() != "INITIALIZING"                # 상태 전이됨


def test_integration_deterministic():
    mat = _two_strat_matrix()
    cur = CurrentPortfolio({"A": 0.4, "B": 0.6}, last_rebalance="2026-06-01")
    kw = dict(now="2026-07-22", ts="2026-07-22T00:00:00Z",
              regime_detector=_fake_regime("bear_high_vol"), dry_run=True)
    r1 = PortfolioOrchestrator().evaluate(mat, cur, **kw)
    r2 = PortfolioOrchestrator().evaluate(mat, cur, **kw)
    assert r1["record"] == r2["record"]
