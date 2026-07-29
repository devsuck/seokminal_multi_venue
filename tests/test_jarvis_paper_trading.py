"""P6.3 Paper Trading Infrastructure 테스트.

price injection · missing price · NAV · exposure · unrealized/realized PnL ·
drawdown · attribution · turnover · stale price · dry-run · rebuild · JSONL 무결성 ·
게이트웨이 무호출 · risk governor 불변.
"""
from __future__ import annotations

import os

import pytest

from jarvis.paper_execution.engine import PaperExecutionEngine
from jarvis.paper_execution.market_data import StaticPriceProvider
from jarvis.paper_execution.valuation import valuate, valuate_current


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    import jarvis.audit.log as al
    import jarvis.paper_execution.ledger as pl
    import jarvis.paper_execution.valuation as vv
    monkeypatch.setattr(al, "state_path", sp)
    monkeypatch.setattr(pl, "state_path", sp)
    monkeypatch.setattr(vv, "state_path", sp)
    return sp


_ALLOW = {"decision": "ALLOW", "failed_checks": []}


def _seed_position(strategy="S1", weight=0.5, price=100.0, capital=10000.0, pid="PP:1"):
    """P6.2로 포지션 생성(BUY)."""
    eng = PaperExecutionEngine(capital=capital)
    eng.execute_proposal(
        {"proposal_id": pid, "strategy": strategy, "allocation": {strategy: weight},
         "created_at": "2026-07-22T00:00:00Z"},
        True, _ALLOW, lambda s, ts: price, "2026-07-22T01:00:00Z", commit=True)


def _positions():
    from jarvis.paper_execution.ledger import current_positions
    return list(current_positions().values())


# ── 1. price provider injection ──
def test_price_provider_injection():
    prov = StaticPriceProvider({"S1": 120.0}, "2026-07-22T02:00:00Z")
    snap = prov.get("S1", "2026-07-22T02:00:00Z")
    assert snap.symbol == "S1" and snap.price == 120.0


# ── 2. missing price handling ──
def test_missing_price_handled():
    prov = StaticPriceProvider({"S1": 120.0})
    assert prov.get("UNKNOWN", "t") is None
    # valuation: 결측 → 평단 flat mark + stale에 기록
    _seed_position(strategy="S2", weight=0.5, price=100.0, capital=10000.0)
    snap = valuate(_positions(), StaticPriceProvider({}), 10000.0, "2026-07-22T02:00:00Z")
    assert "S2" in snap.stale_symbols
    assert abs(snap.unrealized_pnl) < 1e-6            # flat mark → 미실현 0


# ── 3. NAV ──
def test_nav_calculation():
    _seed_position(weight=0.5, price=100.0, capital=10000.0)   # 50주 @100, cash 5000
    # mark 120 → market_value 6000, cash 5000 → NAV 11000
    snap = valuate(_positions(), StaticPriceProvider({"S1": 120.0}), 10000.0, "t")
    assert abs(snap.nav - 11000.0) < 1e-3
    assert abs(snap.cash_balance - 5000.0) < 1e-3


# ── 4. exposure ──
def test_exposure_calculation():
    _seed_position(weight=0.5, price=100.0, capital=10000.0)
    snap = valuate(_positions(), StaticPriceProvider({"S1": 100.0}), 10000.0, "t")
    # market_value 5000, NAV 10000 → gross 0.5
    assert abs(snap.gross_exposure - 0.5) < 1e-6
    assert abs(snap.net_exposure - 0.5) < 1e-6


# ── 5. unrealized PnL ──
def test_unrealized_pnl():
    _seed_position(weight=0.5, price=100.0, capital=10000.0)   # 50주 @100
    snap = valuate(_positions(), StaticPriceProvider({"S1": 130.0}), 10000.0, "t")
    assert abs(snap.unrealized_pnl - 50 * 30) < 1e-3   # 50*(130-100)=1500


# ── 6. realized PnL ──
def test_realized_pnl_flows_to_valuation():
    eng = PaperExecutionEngine(capital=10000.0)
    eng.execute_proposal({"proposal_id": "PP:b", "strategy": "S1", "allocation": {"S1": 1.0},
                          "created_at": "t"}, True, _ALLOW, lambda s, ts: 100.0, "t", commit=True)
    eng.execute_proposal({"proposal_id": "PP:s", "strategy": "S1", "allocation": {"S1": 0.0},
                          "created_at": "t"}, True, _ALLOW, lambda s, ts: 150.0, "t", commit=True)
    snap = valuate(_positions(), StaticPriceProvider({"S1": 150.0}), 10000.0, "t")
    assert abs(snap.realized_pnl - 100 * 50) < 1e-3    # 100*(150-100)=5000


# ── 7. drawdown ──
def test_drawdown_calculation():
    _seed_position(weight=1.0, price=100.0, capital=10000.0)   # 100주
    # peak nav = 12000 (mark 120), 현재 mark 90 → nav 9000 → dd = (12000-9000)/12000=0.25
    snap = valuate(_positions(), StaticPriceProvider({"S1": 90.0}), 10000.0, "t",
                   prev_nav=12000.0, peak_nav=12000.0)
    assert abs(snap.drawdown - 0.25) < 1e-6
    assert abs(snap.daily_return - (9000 - 12000) / 12000) < 1e-6


# ── 8. attribution ──
def test_attribution_correctness():
    _seed_position(strategy="WIN", weight=1.0, price=100.0, capital=10000.0, pid="PP:w")
    _seed_position(strategy="LOSE", weight=1.0, price=100.0, capital=10000.0, pid="PP:l")
    # WIN mark 150 (+), LOSE mark 80 (-) — valuation 후 attribution
    from jarvis.paper_execution.performance import attribution
    from jarvis.paper_execution.ledger import read_fills
    # 포지션에 mark 반영: valuate로 marked positions 생성
    snap = valuate(_positions(), StaticPriceProvider({"WIN": 150.0, "LOSE": 80.0}), 20000.0, "t")
    attr = attribution(snap.positions, read_fills(), 20000.0, "t")
    ids_win = {w["strategy_id"] for w in attr["winners"]}
    ids_lose = {l["strategy_id"] for l in attr["losers"]}
    assert "WIN" in ids_win and "LOSE" in ids_lose
    assert abs(sum(s["contribution_pct"] for s in attr["strategies"]) - 100.0) < 1e-3


# ── 9. turnover ──
def test_turnover_calculation():
    _seed_position(weight=0.5, price=100.0, capital=10000.0)   # 50주 @100 = 5000 notional
    from jarvis.paper_execution.performance import attribution_current
    attr = attribution_current("t", 10000.0)
    # turnover = 5000/10000 = 0.5
    assert abs(attr["turnover"] - 0.5) < 1e-6


# ── 10. stale price detection ──
def test_stale_price_detection():
    _seed_position(weight=0.5, price=100.0, capital=10000.0)
    from jarvis.paper_execution.monitoring import monitor, RiskThresholds
    old = StaticPriceProvider({"S1": (100.0, "2026-07-01T00:00:00Z")})  # 3주 전 가격
    rep = monitor("2026-07-22T00:00:00Z", provider=old, capital=10000.0,
                  thresholds=RiskThresholds(stale_price_hours=24))
    assert rep.stale_prices >= 1
    assert any("stale_prices" in w for w in rep.warnings)


# ── 11. dry-run no mutation ──
def test_dry_run_no_mutation(_isolate):
    _seed_position(weight=0.5, price=100.0, capital=10000.0)
    valuate_current("t", capital=10000.0, commit=False)
    from jarvis.paper_execution.valuation import read_valuations
    assert read_valuations() == []                     # dry-run → paper_portfolio 무기록


# ── 12. deterministic rebuild ──
def test_deterministic_rebuild():
    _seed_position(weight=0.5, price=100.0, capital=10000.0)
    from jarvis.paper_execution.verify import verify
    assert verify()["ok"] is True
    # valuation 결정성: 같은 입력 두 번 → 동일 NAV
    prov = StaticPriceProvider({"S1": 111.0})
    a = valuate(_positions(), prov, 10000.0, "t")
    b = valuate(_positions(), prov, 10000.0, "t")
    assert a.to_dict() == b.to_dict()


# ── 13. JSONL integrity (append-only + capital=paper) ──
def test_jsonl_integrity(_isolate):
    _seed_position(weight=0.5, price=100.0, capital=10000.0)
    valuate_current("t1", capital=10000.0, commit=True)
    valuate_current("t2", capital=10000.0, commit=True)
    from jarvis.paper_execution.valuation import read_valuations
    rows = read_valuations()
    assert len(rows) == 2 and all(r["capital"] == "paper" for r in rows)


# ── 14. no execution gateway usage ──
def test_no_execution_gateway_usage(monkeypatch):
    import jarvis.execution.gateway as gw
    called = {"x": False}
    monkeypatch.setattr(gw.ExecutionGateway, "execute", lambda *a, **k: called.__setitem__("x", True))
    _seed_position(weight=0.5, price=100.0, capital=10000.0)
    valuate_current("t", capital=10000.0, commit=True)
    from jarvis.paper_execution.monitoring import monitor
    monitor("t", capital=10000.0)
    assert called["x"] is False


# ── 15. no risk governor modification ──
def test_no_risk_governor_invocation(monkeypatch):
    import jarvis.risk.governor as rg
    monkeypatch.setattr(rg.RiskGovernor, "check",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("governor called")))
    _seed_position(weight=0.5, price=100.0, capital=10000.0)
    valuate_current("t", capital=10000.0, commit=True)   # governor 미호출


# ── 권한 게이팅 ──
def test_valuation_commit_requires_permission():
    from jarvis.agents import RESEARCH_AGENT
    from jarvis.permissions import PermissionDenied
    _seed_position(weight=0.5, price=100.0, capital=10000.0)
    with pytest.raises(PermissionDenied):
        valuate_current("t", capital=10000.0, commit=True, principal=RESEARCH_AGENT)
