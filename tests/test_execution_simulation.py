"""P7.5 Execution Simulation & Dry-Run Control 테스트.

READY→sim · BLOCKED intent 거부 · missing price · deterministic hash · slippage ·
fee · sell validation · duplicate prevention · append-only · replay · no gateway import ·
no broker call · no position mutation · no permission escalation.
"""
from __future__ import annotations

import os

from jarvis.execution_control.models import ExecutionIntent
from jarvis.execution_simulation.engine import SimulationEngine
from jarvis.execution_simulation.models import BLOCKED, REJECTED, SIMULATED

_NOW = "2026-07-22T00:00:00Z"


class _Decision:
    def __init__(self, status):
        self.status = status


def _intent(side="BUY", qty=100.0, symbol="A", iid="EI:1"):
    return ExecutionIntent(intent_id=iid, strategy="A", symbol=symbol, side=side,
                           quantity=qty, target_weight=0.4, source_proposal_id="PP:1",
                           created_at=_NOW, expiry="")


def _price(p=100.0):
    return lambda sym, now: p


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.execution_simulation.ledger.state_path",
                        lambda name: os.path.join(tmp_path, name))


# ── 1. READY intent creates simulation ──
def test_ready_intent_creates_simulation():
    eng = SimulationEngine()
    r = eng.simulate(_intent(), _Decision("READY"), _price(), _NOW)
    assert r.status == SIMULATED
    assert r.order is not None and r.fill is not None
    assert r.order["symbol"] == "A" and r.order["side"] == "BUY"
    assert r.fill["filled_quantity"] == 100.0
    assert r.simulation_id.startswith("SIM:")


# ── 2. BLOCKED intent rejected ──
def test_blocked_decision_rejected():
    eng = SimulationEngine()
    r = eng.simulate(_intent(), _Decision("BLOCKED"), _price(), _NOW)
    assert r.status == REJECTED
    assert r.order is None and r.fill is None
    assert r.assumptions["reason"] == "decision_not_ready"


# ── 3. missing price blocks ──
def test_missing_price_blocks():
    eng = SimulationEngine()
    r = eng.simulate(_intent(), _Decision("READY"), lambda s, n: None, _NOW)
    assert r.status == BLOCKED
    assert r.order is None and r.fill is None
    assert r.assumptions["reason"] == "missing_price"


# ── 4. deterministic simulation hash ──
def test_deterministic_hash():
    eng = SimulationEngine()
    r1 = eng.simulate(_intent(), _Decision("READY"), _price(), _NOW, slippage_bps=10, fee_bps=5)
    r2 = eng.simulate(_intent(), _Decision("READY"), _price(), _NOW, slippage_bps=10, fee_bps=5)
    assert r1.hash == r2.hash and r1.to_dict() == r2.to_dict()
    r3 = eng.simulate(_intent(), _Decision("READY"), _price(), _NOW, slippage_bps=20, fee_bps=5)
    assert r3.hash != r1.hash   # 가정이 바뀌면 해시도 바뀜


# ── 5. slippage calculation ──
def test_slippage_calculation():
    eng = SimulationEngine()
    # ref 100, 10bps, BUY → 100.10
    rb = eng.simulate(_intent(side="BUY"), _Decision("READY"), _price(100.0), _NOW,
                      slippage_bps=10.0)
    assert rb.fill["fill_price"] == 100.10
    assert round(rb.fill["slippage"], 8) == 0.10
    # SELL → 99.90 (불리하게 싸게)
    rs = eng.simulate(_intent(side="SELL", qty=0.0), _Decision("READY"), _price(100.0), _NOW,
                      slippage_bps=10.0, quantity=0.0)
    assert rs.fill["fill_price"] == 99.90
    # ideal fill(0bps) → 정확히 ref
    ri = eng.simulate(_intent(side="BUY"), _Decision("READY"), _price(100.0), _NOW,
                      slippage_bps=0.0)
    assert ri.fill["fill_price"] == 100.0 and ri.fill["slippage"] == 0.0


# ── 6. fee calculation ──
def test_fee_calculation():
    eng = SimulationEngine()
    # ref 100, BUY qty 100, 0bps slippage, 5bps fee → notional 10000 × 5/10000 = 5.0
    r = eng.simulate(_intent(qty=100.0), _Decision("READY"), _price(100.0), _NOW, fee_bps=5.0)
    assert r.fill["fees"] == 5.0
    # 수수료 0 → 0
    r0 = eng.simulate(_intent(qty=100.0), _Decision("READY"), _price(100.0), _NOW, fee_bps=0.0)
    assert r0.fill["fees"] == 0.0


# ── 7. sell validation ──
def test_sell_validation_no_position(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    eng = SimulationEngine()
    # 시뮬 포지션 0 → SELL 50 거부
    r = eng.simulate(_intent(side="SELL", qty=50.0), _Decision("READY"), _price(), _NOW)
    assert r.status == REJECTED and r.assumptions["reason"] == "invalid_sell_quantity"


def test_sell_valid_within_simulated_position(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    eng = SimulationEngine()
    # BUY 100 커밋 → 시뮬 포지션 100
    eng.simulate(_intent(side="BUY", qty=100.0, iid="EI:buy"), _Decision("READY"),
                 _price(), _NOW, commit=True)
    from jarvis.execution_simulation.ledger import simulated_position
    assert simulated_position("A") == 100.0
    # SELL 60 ≤ 100 → 허용
    r = eng.simulate(_intent(side="SELL", qty=60.0, iid="EI:sell"), _Decision("READY"),
                     _price(), "2026-07-22T01:00:00Z")
    assert r.status == SIMULATED
    # SELL 200 > 100 → 거부
    r2 = eng.simulate(_intent(side="SELL", qty=200.0, iid="EI:sell2"), _Decision("READY"),
                      _price(), "2026-07-22T02:00:00Z")
    assert r2.status == REJECTED


def test_invalid_buy_quantity():
    eng = SimulationEngine()
    r = eng.simulate(_intent(side="BUY", qty=0.0), _Decision("READY"), _price(), _NOW,
                     quantity=0.0)
    assert r.status == REJECTED and r.assumptions["reason"] == "invalid_buy_quantity"


# ── 8. duplicate simulation prevention ──
def test_duplicate_simulation_prevented(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    eng = SimulationEngine()
    first = eng.simulate(_intent(), _Decision("READY"), _price(), _NOW, commit=True)
    second = eng.simulate(_intent(), _Decision("READY"), _price(), _NOW, commit=True)
    assert first is not None and second is None   # 동일 simulation_id → 중복 방지
    from jarvis.execution_simulation.ledger import read_reports
    assert len(read_reports()) == 1


# ── 9. append-only integrity ──
def test_append_only_integrity(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    from jarvis.execution_simulation.ledger import read_fills, read_orders, read_reports
    eng = SimulationEngine()
    eng.simulate(_intent(iid="EI:a"), _Decision("READY"), _price(), _NOW, commit=True)
    eng.simulate(_intent(iid="EI:b"), _Decision("READY"), _price(), "2026-07-22T01:00:00Z",
                 commit=True)
    assert len(read_orders()) == 2 and len(read_fills()) == 2 and len(read_reports()) == 2


# ── 10. replay consistency ──
def test_replay_consistency(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    eng = SimulationEngine()
    committed = eng.simulate(_intent(), _Decision("READY"), _price(), _NOW,
                             slippage_bps=10, fee_bps=5, commit=True)
    # 원장에서 재현(재계산) → 동일 해시/내용
    replay = eng.simulate(_intent(), _Decision("READY"), _price(), _NOW,
                          slippage_bps=10, fee_bps=5, commit=False)
    assert replay.hash == committed.hash and replay.to_dict() == committed.to_dict()


# ── 11. no gateway import / no broker call ──
def test_no_execution_import():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.execution_simulation.{m}"))
        stripped = src.replace("jarvis.execution_control", "").replace("jarvis.execution_simulation", "")
        assert "jarvis.execution" not in stripped   # 집행 게이트웨이/ARM 미import
        assert "gateway" not in src
        assert "place_order" not in src and "submit_order" not in src
        assert "create_order" not in src


def test_no_broker_call():
    import importlib
    import inspect
    src = inspect.getsource(importlib.import_module("jarvis.execution_simulation.engine"))
    for banned in ("broker", ".buy(", ".sell(", "cancel_order", "order_client"):
        assert banned not in src
    # 리스크/레지스트리/페이퍼 원장 변경 없음(직접 import 없음)
    assert "jarvis.risk" not in src and "jarvis.registry" not in src
    assert "jarvis.paper_execution" not in src


# ── 12. no position mutation ──
def test_no_paper_position_mutation(tmp_path, monkeypatch):
    import hashlib

    def sp(name):
        return os.path.join(tmp_path, name)
    import jarvis.paper_execution.ledger as pel
    monkeypatch.setattr(pel, "state_path", sp)
    from jarvis.paper_execution.engine import PaperExecutionEngine
    PaperExecutionEngine(capital=10000).execute_proposal(
        {"proposal_id": "PP:1", "strategy": "A", "allocation": {"A": 0.5}, "created_at": "t"},
        True, {"decision": "ALLOW"}, lambda s, ts: 100.0, "t", commit=True)
    pos_path = sp("paper_positions.jsonl")
    before = hashlib.sha256(open(pos_path, "rb").read()).hexdigest()
    # 시뮬 실행(격리 원장)
    monkeypatch.setattr("jarvis.execution_simulation.ledger.state_path", sp)
    eng = SimulationEngine()
    eng.simulate(_intent(), _Decision("READY"), _price(), _NOW, commit=True)
    assert hashlib.sha256(open(pos_path, "rb").read()).hexdigest() == before   # 페이퍼 원장 불변


# ── 13. no permission escalation ──
def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    assert not any("simulation" in a for a in ACTION_PERMISSIONS)
    assert not any("simulated_order" in a for a in ACTION_PERMISSIONS)


# ── 14. SimulatedOrder is NOT a real order ──
def test_simulated_order_is_not_real_order():
    eng = SimulationEngine()
    r = eng.simulate(_intent(), _Decision("READY"), _price(), _NOW)
    okeys = set(r.order)
    assert okeys == {"simulation_id", "intent_id", "symbol", "side", "quantity",
                     "reference_price", "created_at"}
    # 실집행 필드 부재
    for f in ("order_id", "broker", "venue", "gateway", "filled", "account", "status"):
        assert f not in okeys
