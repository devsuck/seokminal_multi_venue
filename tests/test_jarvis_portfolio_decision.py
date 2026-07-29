"""P2.3 Portfolio Decision Engine 테스트 — 리밸런스 제안(제안전용).

케이스: 소편차 무리밸런스 · 유의미 리밸런스 · 비용>편익 · 쿨다운 차단 · 결정성.
가드: no-lookahead · 보유미상 보수폴백 · 원장 권한/감사.
"""
from __future__ import annotations

import os

from jarvis.portfolio.decision_engine import (
    CurrentPortfolio,
    RebalanceConfig,
    propose_rebalance,
)
from jarvis.portfolio.risk_scaler import RiskAdjustedAllocation


def _ra(weights: dict) -> RiskAdjustedAllocation:
    return RiskAdjustedAllocation(
        strategy_weights=weights, gross_exposure=sum(weights.values()),
        volatility_target=0.15, current_volatility=0.1, drawdown_adjustment=1.0,
        regime_multiplier=1.0, rationale="t", timestamp="T")


def _dec(props):
    return {p.strategy_id: (p.decision, p.delta) for p in props}


# ── 소편차 → 리밸런스 없음 ───────────────────────────────────
def test_no_rebalance_when_delta_small():
    ra = _ra({"A": 0.50, "B": 0.50})
    cur = CurrentPortfolio({"A": 0.49, "B": 0.51})   # |Δ|=0.01 < min_delta
    dec = propose_rebalance(ra, cur, now="2026-07-22", ts="T")
    assert dec.any_rebalance is False
    assert all(p.decision == "hold" for p in dec.proposals)
    assert all("below_threshold" in p.rationale for p in dec.proposals)


# ── 유의미 편차 → 리밸런스 ───────────────────────────────────
def test_rebalance_when_meaningful():
    ra = _ra({"A": 0.70, "B": 0.30})
    cur = CurrentPortfolio({"A": 0.40, "B": 0.60})   # |Δ|=0.30
    dec = propose_rebalance(ra, cur, now="2026-07-22", ts="T")
    assert dec.any_rebalance is True
    d = _dec(dec.proposals)
    assert d["A"][0] == "rebalance" and d["B"][0] == "rebalance"
    assert abs(dec.total_turnover - 0.30) < 1e-9      # (|+.3|+|-.3|)/2


# ── 비용 > 편익 → 보류 ───────────────────────────────────────
def test_cost_exceeds_benefit_holds():
    # cb 임계 = cost_rate/benefit_coeff = 0.05/1 = 0.05. Δ=0.03 → min 통과, 비용>편익.
    cfg = RebalanceConfig(min_delta=0.01, cost_bps=500, benefit_coeff=1.0)
    ra = _ra({"A": 0.53, "B": 0.47})
    cur = CurrentPortfolio({"A": 0.50, "B": 0.50})   # |Δ|=0.03
    dec = propose_rebalance(ra, cur, cfg, now="2026-07-22", ts="T")
    assert dec.any_rebalance is False
    assert all("cost_exceeds_benefit" in p.rationale for p in dec.proposals)
    # 같은 config에서 큰 편차는 리밸런스
    dec2 = propose_rebalance(_ra({"A": 0.65, "B": 0.35}),
                             CurrentPortfolio({"A": 0.50, "B": 0.50}), cfg,
                             now="2026-07-22", ts="T")
    assert dec2.any_rebalance is True


# ── 쿨다운 차단 ──────────────────────────────────────────────
def test_cooldown_blocks_repeated_rebalance():
    ra = _ra({"A": 0.70, "B": 0.30})
    cur = CurrentPortfolio({"A": 0.40, "B": 0.60}, last_rebalance="2026-07-20")  # 2일 전
    dec = propose_rebalance(ra, cur, now="2026-07-22", ts="T")  # cooldown 7d
    assert dec.cooldown_active is True
    assert dec.any_rebalance is False
    assert all("cooldown" in p.rationale for p in dec.proposals)
    # 쿨다운 경과 후엔 허용
    cur2 = CurrentPortfolio({"A": 0.40, "B": 0.60}, last_rebalance="2026-07-01")
    dec2 = propose_rebalance(ra, cur2, now="2026-07-22", ts="T")
    assert dec2.cooldown_active is False and dec2.any_rebalance is True


# ── 결정성 ───────────────────────────────────────────────────
def test_deterministic():
    ra = _ra({"A": 0.70, "B": 0.30})
    cur = CurrentPortfolio({"A": 0.40, "B": 0.60})
    a = propose_rebalance(ra, cur, now="2026-07-22", ts="T")
    b = propose_rebalance(ra, cur, now="2026-07-22", ts="T")
    assert a.to_dict() == b.to_dict()


# ── 보유 미상 보수 폴백 ──────────────────────────────────────
def test_missing_holdings_conservative():
    ra = _ra({"A": 0.70, "B": 0.30})
    dec = propose_rebalance(ra, None, now="2026-07-22", ts="T")
    assert dec.any_rebalance is False
    assert all(p.decision == "hold" and p.current_weight is None for p in dec.proposals)
    assert dec.diagnostics["reason"] == "missing_holdings_conservative"


def test_holdings_known_false_also_conservative():
    ra = _ra({"A": 1.0})
    cur = CurrentPortfolio({}, known=False)
    dec = propose_rebalance(ra, cur, now="2026-07-22", ts="T")
    assert dec.any_rebalance is False and dec.proposals[0].current_weight is None


# ── enter / exit 분류 ────────────────────────────────────────
def test_enter_and_exit_classification():
    ra = _ra({"A": 0.60, "C": 0.40})               # B 이탈, C 신규
    cur = CurrentPortfolio({"A": 0.30, "B": 0.70})
    dec = propose_rebalance(ra, cur, now="2026-07-22", ts="T")
    r = {p.strategy_id: p.rationale for p in dec.proposals if p.decision == "rebalance"}
    assert "enter" in r.get("C", "")
    assert "exit" in r.get("B", "")


# ── 원장 권한 + 감사 ─────────────────────────────────────────
def test_ledger_write_requires_permission_and_audits(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    import jarvis.audit.log as al
    import jarvis.portfolio.rebalance_ledger as rl
    monkeypatch.setattr(al, "state_path", sp)
    monkeypatch.setattr(rl, "state_path", sp)

    ra = _ra({"A": 0.70, "B": 0.30})
    dec = propose_rebalance(ra, CurrentPortfolio({"A": 0.40, "B": 0.60}), now="2026-07-22", ts="T")
    out = rl.write_proposal(dec)
    assert out["written"] is True
    rows = rl.read_latest()
    assert len(rows) == 1 and rows[0]["orders_placed"] is False and rows[0]["executed"] is False
    audit = al.read_all()
    assert any(a.get("action") == "write_rebalance_proposal" and a.get("result") == "written"
               for a in audit)
    assert any(a.get("action") == "propose_rebalance" and a.get("result") == "allowed"
               for a in audit)
