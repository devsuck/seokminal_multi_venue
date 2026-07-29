"""Signal Fusion v1 테스트 — 리스크조정 가중투표 + 설명가능 합성 + 원장 권한.

가드: 손실전략=0표, 소표본 수축, 상쇄=flat, 원장 write는 FUSION_AGENT 권한.
"""
from __future__ import annotations

import os

import pytest

from jarvis.fusion.fusion import FusionEngine
from jarvis.fusion.performance import perf_from_returns, risk_adjusted_score
from jarvis.fusion.types import StrategySignal
from jarvis.fusion.validate import validate_scheme
from jarvis.fusion.weighting import RiskAdjustedVoting, get_scheme


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    import jarvis.audit.log as al
    import jarvis.fusion.ledger as fl
    import jarvis.fusion.performance as pf
    monkeypatch.setattr(al, "state_path", sp)
    monkeypatch.setattr(fl, "state_path", sp)
    monkeypatch.setattr(pf, "state_path", sp)
    return tmp_path


def _perf(sid, returns):
    return perf_from_returns(sid, returns, "test")


# ── types ────────────────────────────────────────────────────
def test_signal_rejects_bad_direction():
    with pytest.raises(ValueError):
        StrategySignal("s", "AAA", 2)


def test_signal_clamps_strength():
    assert StrategySignal("s", "AAA", 1, strength=5.0).strength == 1.0
    assert StrategySignal("s", "AAA", 1, strength=-1.0).strength == 0.0


# ── performance / scoring ────────────────────────────────────
def test_losing_strategy_scores_zero():
    r = risk_adjusted_score([-0.02, -0.01, -0.03, -0.015] * 10)
    assert r["score"] == 0.0
    assert r["sharpe"] is not None and r["sharpe"] < 0


def test_underpowered_flag_and_shrink():
    small = risk_adjusted_score([0.02, 0.03, 0.025])
    big = risk_adjusted_score([0.02, 0.03, 0.025, 0.015, 0.028] * 8)
    assert small["underpowered"] is True
    assert big["underpowered"] is False
    assert small["score"] < big["score"]


# ── weighting ────────────────────────────────────────────────
def test_weights_sum_to_one_and_monotonic():
    strong = _perf("STRONG", [0.02, 0.03, 0.025, 0.015, 0.028] * 8)
    weak = _perf("WEAK", [0.001, 0.002, -0.001, 0.0015, 0.0005] * 8)
    w = RiskAdjustedVoting().weights({"STRONG": strong, "WEAK": weak})
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert w["STRONG"] > w["WEAK"]


def test_all_zero_scores_give_zero_weights():
    lose = _perf("L", [-0.02, -0.01, -0.03] * 12)
    w = RiskAdjustedVoting().weights({"L": lose})
    assert w["L"] == 0.0


# ── fusion engine ────────────────────────────────────────────
def test_single_long_gives_direction_plus_one():
    strong = _perf("STRONG", [0.02, 0.03, 0.025, 0.015, 0.028] * 8)
    fs = FusionEngine("v1_risk_adjusted").fuse([StrategySignal("STRONG", "BBB", 1)], {"STRONG": strong})
    assert fs[0].direction == 1
    assert abs(fs[0].confidence - 1.0) < 1e-9
    assert fs[0].contributions[0].strategy_id == "STRONG"


def test_opposing_equal_weight_nets_out():
    a = _perf("A", [0.02, 0.03, 0.025, 0.015, 0.028] * 8)
    b = _perf("B", [0.02, 0.03, 0.025, 0.015, 0.028] * 8)
    fs = FusionEngine().fuse(
        [StrategySignal("A", "CCC", 1), StrategySignal("B", "CCC", -1)], {"A": a, "B": b})
    assert fs[0].direction == 0
    assert fs[0].n_strategies == 2


def test_losing_strategy_contributes_zero_weight():
    strong = _perf("STRONG", [0.02, 0.03, 0.025, 0.015, 0.028] * 8)
    lose = _perf("LOSE", [-0.02, -0.01, -0.03, -0.015] * 10)
    fs = FusionEngine().fuse(
        [StrategySignal("STRONG", "DDD", 1), StrategySignal("LOSE", "DDD", -1)],
        {"STRONG": strong, "LOSE": lose})
    # 손실전략은 0표 → 합성은 STRONG 방향(+1)
    assert fs[0].direction == 1
    lose_c = next(c for c in fs[0].contributions if c.strategy_id == "LOSE")
    assert lose_c.weight == 0.0


def test_multi_instrument_grouping():
    a = _perf("A", [0.02, 0.03, 0.025, 0.015, 0.028] * 8)
    fs = FusionEngine().fuse(
        [StrategySignal("A", "AAA", 1), StrategySignal("A", "BBB", -1)], {"A": a})
    inst = {f.instrument: f.direction for f in fs}
    assert inst == {"AAA": 1, "BBB": -1}


# ── pending schemes ──────────────────────────────────────────
def test_pending_scheme_raises():
    with pytest.raises(NotImplementedError):
        get_scheme("v2_regime_aware").weights({})


# ── validation harness ───────────────────────────────────────
def test_v1_scheme_passes_validation():
    res = validate_scheme("v1_risk_adjusted")
    assert res["passed"] is True, res
    assert all(c["ok"] for c in res["checks"])


def test_pending_scheme_fails_validation():
    res = validate_scheme("v3_bayesian")
    assert res["implemented"] is False
    assert res["passed"] is False


# ── ledger + permission ──────────────────────────────────────
def test_ledger_write_requires_permission_and_reads_back():
    from jarvis.fusion.ledger import read_latest, write_signals
    strong = _perf("STRONG", [0.02, 0.03, 0.025, 0.015, 0.028] * 8)
    fs = FusionEngine().fuse([StrategySignal("STRONG", "BBB", 1)], {"STRONG": strong})
    n = write_signals(fs, "v1_risk_adjusted")
    assert n == 1
    rows = read_latest()
    assert len(rows) == 1
    assert rows[0]["instrument"] == "BBB"
    assert rows[0]["direction"] == 1
    # 감사로그에 권한 허용 기록이 남았는지
    import jarvis.audit.log as al
    audit = al.read_all()
    assert any(a.get("action") == "write_fusion_signal" and a.get("result") == "allowed"
               for a in audit)
