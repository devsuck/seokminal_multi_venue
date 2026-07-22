"""P8.4 Execution Cost & Slippage Accounting 테스트.

commission·exchange fee·slippage BUY/SELL·spread·total·cost_bps·기대비교·warning/failure·
부분체결집계·중복방지·결정적해시·리플레이·체인무결성·브로커write없음·집행미import·포지션불변.
"""
from __future__ import annotations

import os

from jarvis.execution_cost.calculator import calculate, cost_bps, slippage_bps, spread_bps
from jarvis.execution_cost.engine import CostAccountingEngine, cost_input_from_fills
from jarvis.execution_cost.models import (
    EXPECTED,
    FAILED,
    WARNING,
    CostRates,
    CostThresholds,
    ExecutionCostInput,
)

_NOW = "2026-07-22T00:00:00Z"


def _inp(side="BUY", qty=100.0, exp=100.0, fill=100.0, oid="ECR:1"):
    return ExecutionCostInput(order_id=oid, symbol="A", side=side, quantity=qty,
                              expected_price=exp, fill_price=fill, gross_value=round(qty * fill, 8),
                              timestamp=_NOW)


def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.execution_cost.ledger.state_path",
                        lambda name: os.path.join(tmp_path, name))


# ── 1. commission calculation ──
def test_commission_calculation():
    comps = calculate(_inp(fill=100.0), CostRates(commission_rate=0.001))   # gross 10000 × 0.001
    assert comps.commission == 10.0


# ── 2. exchange fee calculation ──
def test_exchange_fee_calculation():
    comps = calculate(_inp(fill=100.0), CostRates(exchange_fee_rate=0.0002))   # 10000 × 0.0002
    assert comps.exchange_fee == 2.0


def test_fx_and_market_impact():
    comps = calculate(_inp(fill=100.0), CostRates(fx_rate_cost=0.0003, market_impact_rate=0.0001))
    assert comps.fx_cost == 3.0 and comps.market_impact_cost == 1.0


# ── 3. slippage BUY ──
def test_slippage_buy():
    # 기대 100, 체결 101 → (101-100)/100*10000 = 100bps
    assert slippage_bps("BUY", 100.0, 101.0) == 100.0
    comps = calculate(_inp(side="BUY", exp=100.0, fill=101.0))   # gross 10100
    assert comps.slippage_cost == round(100.0 / 10000 * 10100.0, 8)   # 101.0


# ── 4. slippage SELL ──
def test_slippage_sell():
    # 기대 100, 체결 99 → (100-99)/100*10000 = 100bps(불리)
    assert slippage_bps("SELL", 100.0, 99.0) == 100.0
    # 유리한 체결(SELL 비싸게)은 음수
    assert slippage_bps("SELL", 100.0, 101.0) == -100.0


# ── 5. spread calculation ──
def test_spread_calculation():
    # 체결 101, mid 100 → |101-100|/100*10000 = 100bps
    assert spread_bps(101.0, 100.0) == 100.0
    comps = calculate(_inp(fill=101.0), mid_price=100.0)   # gross 10100
    assert comps.spread_cost == round(100.0 / 10000 * 10100.0, 8)


# ── 6. total cost aggregation ──
def test_total_cost_aggregation():
    comps = calculate(_inp(side="BUY", exp=100.0, fill=100.0),
                      CostRates(commission_rate=0.001, exchange_fee_rate=0.0002,
                                fx_rate_cost=0.0003, market_impact_rate=0.0001),
                      mid_price=100.0)
    # slippage 0, spread 0. total = 10+2+3+1 = 16
    assert comps.slippage_cost == 0.0 and comps.spread_cost == 0.0
    assert comps.total_cost == 16.0


# ── 7. cost bps calculation ──
def test_cost_bps_calculation():
    # total 10 on gross 10000 → 10bps
    assert cost_bps(10.0, 10000.0) == 10.0


# ── 8. expected cost comparison + status ──
def test_expected_status():
    eng = CostAccountingEngine(CostRates(commission_rate=0.001),   # cost_bps=10
                               CostThresholds(expected_cost_bps=10.0, warning_multiplier=1.5,
                                              failure_multiplier=3.0))
    r = eng.calculate(_inp(fill=100.0), _NOW, mid_price=100.0)   # 순수 commission → 10bps
    assert r.cost_bps == 10.0 and r.status == EXPECTED
    assert r.variance_bps == 0.0


# ── 9. warning threshold ──
def test_warning_threshold():
    eng = CostAccountingEngine(CostRates(commission_rate=0.002),   # 20bps
                               CostThresholds(expected_cost_bps=10.0, warning_multiplier=1.5,
                                              failure_multiplier=3.0))
    r = eng.calculate(_inp(fill=100.0), _NOW, mid_price=100.0)   # 20bps: >15, <=30
    assert r.cost_bps == 20.0 and r.status == WARNING


# ── 10. failure threshold ──
def test_failure_threshold():
    eng = CostAccountingEngine(CostRates(commission_rate=0.004),   # 40bps
                               CostThresholds(expected_cost_bps=10.0, warning_multiplier=1.5,
                                              failure_multiplier=3.0))
    r = eng.calculate(_inp(fill=100.0), _NOW, mid_price=100.0)   # 40bps: >30
    assert r.cost_bps == 40.0 and r.status == FAILED
    assert r.variance_bps == 30.0


# ── 11. partial fill aggregation ──
def test_partial_fill_aggregation():
    fills = [{"fill_id": "F:1", "quantity": 40.0, "fill_price": 100.0, "fee": 0.0,
              "timestamp": "2026-07-22T00:00:01Z"},
             {"fill_id": "F:2", "quantity": 60.0, "fill_price": 110.0, "fee": 0.0,
              "timestamp": "2026-07-22T00:00:02Z"}]
    inp = cost_input_from_fills("ECR:1", "A", "BUY", 100.0, fills)
    # wap = (4000+6600)/100 = 106, gross = 100*106 = 10600
    assert inp.fill_price == 106.0 and inp.quantity == 100.0 and inp.gross_value == 10600.0


def test_partial_fill_dedup():
    fills = [{"fill_id": "F:1", "quantity": 50.0, "fill_price": 100.0, "fee": 0.0, "timestamp": "t"},
             {"fill_id": "F:1", "quantity": 50.0, "fill_price": 100.0, "fee": 0.0, "timestamp": "t"}]
    inp = cost_input_from_fills("ECR:1", "A", "BUY", 100.0, fills)
    assert inp.quantity == 50.0   # 중복 fill_id 제거


# ── 12. duplicate prevention ──
def test_duplicate_prevention(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.execution_cost.ledger import read_events
    eng = CostAccountingEngine(CostRates(commission_rate=0.001))
    eng.calculate(_inp(), _NOW, mid_price=100.0, commit=True)
    eng.calculate(_inp(), _NOW, mid_price=100.0, commit=True)   # 동일 → 재추가 안 됨
    assert len(read_events()) == 1


# ── 13. deterministic hash ──
def test_deterministic_hash():
    eng = CostAccountingEngine(CostRates(commission_rate=0.001))
    r1 = eng.calculate(_inp(), _NOW, mid_price=100.0)
    r2 = eng.calculate(_inp(), _NOW, mid_price=100.0)
    assert r1.report_hash == r2.report_hash and r1.to_dict() == r2.to_dict()
    r3 = eng.calculate(_inp(fill=101.0), _NOW, mid_price=100.0)
    assert r3.report_hash != r1.report_hash


def test_input_hash_present():
    eng = CostAccountingEngine()
    r = eng.calculate(_inp(), _NOW)
    assert r.input_hash.startswith("sha256:") and r.input_hash != r.report_hash


# ── 14. replay recovery ──
def test_replay_recovery(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.execution_cost.verify import replay
    eng = CostAccountingEngine(CostRates(commission_rate=0.001))
    committed = eng.calculate(_inp(), _NOW, mid_price=100.0, commit=True)
    res = replay(eng, _inp(), _NOW, mid_price=100.0)
    assert res["deterministic"] and res["report_hash"] == committed.report_hash


# ── 15. ledger integrity (hash chain) ──
def test_ledger_integrity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.execution_cost.ledger import read_events
    from jarvis.execution_cost.verify import verify_chain
    eng = CostAccountingEngine(CostRates(commission_rate=0.001))
    eng.calculate(_inp(oid="ECR:a"), _NOW, mid_price=100.0, commit=True)
    eng.calculate(_inp(oid="ECR:b"), _NOW, mid_price=100.0, commit=True)
    evs = read_events()
    assert evs[0]["previous_hash"] == "GENESIS"
    assert evs[1]["previous_hash"] == evs[0]["cost_hash"]
    assert verify_chain()["ok"]


def test_corrupted_ledger_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.execution_cost.verify import verify_chain
    eng = CostAccountingEngine(CostRates(commission_rate=0.001))
    eng.calculate(_inp(oid="ECR:a"), _NOW, mid_price=100.0, commit=True)
    eng.calculate(_inp(oid="ECR:b"), _NOW, mid_price=100.0, commit=True)
    import json
    p = os.path.join(tmp_path, "execution_cost_events.jsonl")
    lines = open(p).read().splitlines()
    row = json.loads(lines[1]); row["previous_hash"] = "sha256:tampered"
    lines[1] = json.dumps(row)
    open(p, "w").write("\n".join(lines) + "\n")
    res = verify_chain()
    assert not res["ok"] and res["reason"] == "previous_hash_broken"


# ── 16. no broker write / no execution gateway import ──
def test_no_broker_write_no_execution_import():
    import importlib
    import inspect
    for m in ("models", "calculator", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.execution_cost.{m}"))
        assert "jarvis.execution.gateway" not in src
        assert "jarvis.execution.arm" not in src
        assert "submit_order" not in src and "place_order" not in src
        assert "adapter.submit" not in src and "broker_execution" not in src
    eng = inspect.getsource(importlib.import_module("jarvis.execution_cost.engine"))
    assert "jarvis.risk" not in eng and "jarvis.registry" not in eng
    assert "jarvis.portfolio" not in eng and "jarvis.paper_execution" not in eng


# ── 17. no autonomous trigger ──
def test_no_autonomous_trigger():
    import importlib
    import inspect
    for m in ("engine", "calculator", "__main__", "verify"):
        src = inspect.getsource(importlib.import_module(f"jarvis.execution_cost.{m}"))
        assert "LiveExecutionEngine" not in src
        assert "live_execution.engine" not in src


# ── 18. no position mutation ──
def test_no_position_mutation(tmp_path, monkeypatch):
    import hashlib

    def sp(name):
        return os.path.join(tmp_path, name)
    import jarvis.paper_execution.ledger as pel
    monkeypatch.setattr(pel, "state_path", sp)
    from jarvis.paper_execution.engine import PaperExecutionEngine
    PaperExecutionEngine(capital=10000).execute_proposal(
        {"proposal_id": "PP:1", "strategy": "A", "allocation": {"A": 0.5}, "created_at": "t"},
        True, {"decision": "ALLOW"}, lambda s, ts: 100.0, "t", commit=True)
    pos = sp("paper_positions.jsonl")
    before = hashlib.sha256(open(pos, "rb").read()).hexdigest()
    monkeypatch.setattr("jarvis.execution_cost.ledger.state_path", sp)
    CostAccountingEngine(CostRates(commission_rate=0.001)).calculate(_inp(), _NOW, mid_price=100.0,
                                                                     commit=True)
    assert hashlib.sha256(open(pos, "rb").read()).hexdigest() == before   # 페이퍼 불변


# ── 19. no permission escalation ──
def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    assert not any("execution_cost" in a for a in ACTION_PERMISSIONS)
    assert not any("cost_accounting" in a for a in ACTION_PERMISSIONS)
