"""P6.2 Paper Execution 테스트 — 시뮬 체결(라이브 아님).

approved→order · blocked→nothing · duplicate 방지 · 결정적 id · buy/sell 회계 ·
평단·실현/미실현 PnL · dry-run 무변경 · append-only · 권한 · 게이트웨이 무호출 ·
risk governor 불변 · 결정적 재구축.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.paper_execution.engine import PaperExecutionEngine, portfolio_status
from jarvis.paper_execution.models import execution_id


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    import jarvis.audit.log as al
    import jarvis.paper_execution.ledger as pl
    monkeypatch.setattr(al, "state_path", sp)
    monkeypatch.setattr(pl, "state_path", sp)
    return sp


_ALLOW = {"decision": "ALLOW", "failed_checks": []}
_BLOCK = {"decision": "BLOCK", "failed_checks": ["permission_level:autonomy(5<6)"]}


def _prop(pid="PP:1", strategy="S1", weight=0.5):
    return {"proposal_id": pid, "source": "test", "strategy": strategy,
            "allocation": {strategy: weight}, "created_at": "2026-07-22T00:00:00Z"}


def _price(px):
    return lambda s, ts: px


# ── 1. approved → order ──
def test_approved_proposal_creates_order():
    eng = PaperExecutionEngine(capital=10000.0)
    rep = eng.execute_proposal(_prop(weight=0.5), True, _ALLOW, _price(100.0),
                               "2026-07-22T01:00:00Z", commit=True)
    assert rep.orders_created == 1 and rep.fills_created == 1
    # 목표 0.5 × 10000 / 100 = 50 수량
    pos = rep.positions_after[0]
    assert abs(pos["quantity"] - 50.0) < 1e-6


# ── 2. blocked → nothing ──
def test_blocked_proposal_creates_nothing():
    eng = PaperExecutionEngine()
    rep = eng.execute_proposal(_prop(), True, _BLOCK, _price(100.0), "T", commit=True)
    assert rep.orders_created == 0 and rep.note == "gate_not_allow"


def test_unapproved_creates_nothing():
    eng = PaperExecutionEngine()
    rep = eng.execute_proposal(_prop(), False, _ALLOW, _price(100.0), "T", commit=True)
    assert rep.orders_created == 0 and rep.note == "not_approved"


# ── 3. duplicate 방지 ──
def test_duplicate_execution_prevented():
    eng = PaperExecutionEngine(capital=10000.0)
    eng.execute_proposal(_prop(pid="PP:dup"), True, _ALLOW, _price(100.0), "T", commit=True)
    rep2 = eng.execute_proposal(_prop(pid="PP:dup"), True, _ALLOW, _price(100.0), "T", commit=True)
    assert rep2.orders_created == 0 and rep2.note == "already_executed"


# ── 4. 결정적 id ──
def test_deterministic_execution_id():
    assert execution_id("PP:x") == execution_id("PP:x")
    eng = PaperExecutionEngine()
    r = eng.execute_proposal(_prop(pid="PP:x"), True, _ALLOW, _price(100.0), "T", commit=False)
    assert r.execution_id == execution_id("PP:x")


# ── 5. buy/sell 회계 ──
def test_buy_then_sell_accounting():
    eng = PaperExecutionEngine(capital=10000.0)
    # BUY 목표 0.5 → 50주 @100
    eng.execute_proposal(_prop(pid="PP:b", weight=0.5), True, _ALLOW, _price(100.0), "T", commit=True)
    # 목표 0.2 @120 → target=0.2*10000/120=16.667주 → 33.333주 매도 @120
    eng.execute_proposal(_prop(pid="PP:s", weight=0.2), True, _ALLOW, _price(120.0), "T", commit=True)
    st = portfolio_status(10000.0)
    pos = st["positions"][0]
    assert abs(pos["quantity"] - (0.2 * 10000 / 120)) < 1e-4   # 50 → 16.667
    # 실현손익 = 33.333 * (120-100) = 666.67
    assert abs(pos["realized_pnl"] - (50 - 0.2 * 10000 / 120) * 20) < 1e-2


# ── 6. 평단 ──
def test_average_price_calculation():
    eng = PaperExecutionEngine(capital=10000.0)
    # BUY 목표 0.3 @100 → 30주 평단100
    eng.execute_proposal(_prop(pid="PP:a1", weight=0.3), True, _ALLOW, _price(100.0), "T", commit=True)
    # BUY 목표 늘림: 목표 0.8 @200 → target 40주 → 10주 추가매수 @200
    eng.execute_proposal(_prop(pid="PP:a2", weight=0.8), True, _ALLOW, _price(200.0), "T", commit=True)
    pos = portfolio_status(10000.0)["positions"][0]
    # 평단 = (30*100 + 10*200)/40 = 125
    assert abs(pos["average_price"] - 125.0) < 1e-6
    assert abs(pos["quantity"] - 40.0) < 1e-6


# ── 7. 실현 PnL ──
def test_realized_pnl():
    eng = PaperExecutionEngine(capital=10000.0)
    eng.execute_proposal(_prop(pid="PP:r1", weight=1.0), True, _ALLOW, _price(100.0), "T", commit=True)  # 100주
    eng.execute_proposal(_prop(pid="PP:r2", weight=0.0), True, _ALLOW, _price(150.0), "T", commit=True)  # 전량매도
    pos = portfolio_status(10000.0)["positions"][0]
    assert abs(pos["quantity"]) < 1e-6                  # 청산
    assert abs(pos["realized_pnl"] - 100 * 50) < 1e-3   # 100*(150-100)=5000


# ── 8. 미실현 PnL ──
def test_unrealized_pnl():
    eng = PaperExecutionEngine(capital=10000.0)
    rep = eng.execute_proposal(_prop(pid="PP:u", weight=0.5), True, _ALLOW, _price(100.0), "T", commit=True)
    # 체결 직후 미실현 = 50*(100-100)=0
    assert abs(rep.pnl_summary["unrealized"]) < 1e-6
    assert abs(rep.pnl_summary["realized"]) < 1e-6


# ── 9. dry-run 무변경 ──
def test_dry_run_no_mutation(_isolate):
    eng = PaperExecutionEngine()
    eng.execute_proposal(_prop(), True, _ALLOW, _price(100.0), "T", commit=False)
    import jarvis.paper_execution.ledger as pl
    assert pl.read_orders() == [] and pl.read_reports() == []


# ── 10. append-only 무결성 ──
def test_ledger_append_only():
    eng = PaperExecutionEngine(capital=10000.0)
    eng.execute_proposal(_prop(pid="PP:l1"), True, _ALLOW, _price(100.0), "T", commit=True)
    eng.execute_proposal(_prop(pid="PP:l2", strategy="S2"), True, _ALLOW, _price(100.0), "T", commit=True)
    import jarvis.paper_execution.ledger as pl
    assert len(pl.read_reports()) == 2
    assert all(r["capital"] == "paper" for r in pl.read_orders())


# ── 11. 권한 ──
def test_permission_enforcement():
    from jarvis.agents import RESEARCH_AGENT
    from jarvis.permissions import PermissionDenied
    eng = PaperExecutionEngine()
    with pytest.raises(PermissionDenied):
        eng.execute_proposal(_prop(), True, _ALLOW, _price(100.0), "T", commit=True,
                             principal=RESEARCH_AGENT)   # RESEARCH_ONLY < PAPER_ONLY


# ── 12. 게이트웨이 무호출 ──
def test_no_execution_gateway_invocation(monkeypatch):
    called = {"x": False}
    import jarvis.execution.gateway as gw
    monkeypatch.setattr(gw.ExecutionGateway, "execute",
                        lambda *a, **k: called.__setitem__("x", True))
    eng = PaperExecutionEngine(capital=10000.0)
    eng.execute_proposal(_prop(), True, _ALLOW, _price(100.0), "T", commit=True)
    assert called["x"] is False


# ── 13. risk governor 불변 ──
def test_risk_governor_not_invoked(monkeypatch):
    import jarvis.risk.governor as rg
    monkeypatch.setattr(rg.RiskGovernor, "check",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("governor called")))
    eng = PaperExecutionEngine(capital=10000.0)
    eng.execute_proposal(_prop(), True, _ALLOW, _price(100.0), "T", commit=True)  # governor 미호출


# ── 14. 결정적 재구축 ──
def test_deterministic_rebuild():
    eng = PaperExecutionEngine(capital=10000.0)
    eng.execute_proposal(_prop(pid="PP:b", weight=0.5), True, _ALLOW, _price(100.0), "T", commit=True)
    eng.execute_proposal(_prop(pid="PP:s", weight=0.2), True, _ALLOW, _price(120.0), "T", commit=True)
    from jarvis.paper_execution.verify import verify
    res = verify()
    assert res["ok"] is True and res["deterministic"] is True and res["mismatches"] == []
