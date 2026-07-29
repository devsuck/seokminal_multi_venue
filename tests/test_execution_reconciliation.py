"""P7.6 Execution Reconciliation & Fill Validation 테스트.

perfect→PASS · quantity WARNING/FAILED · price · fee · slippage · timing · missing sim ·
deterministic hash · replay · append-only · no gateway import · no broker · no mutation ·
no permission escalation.
"""
from __future__ import annotations

import os

from jarvis.execution_reconciliation.engine import (
    ExecutionReconciliationEngine,
    perfect_expectation,
)
from jarvis.execution_reconciliation.models import (
    FAILED,
    PASS,
    WARNING,
    ExecutionExpectation,
    ValidationThresholds,
)

_NOW = "2026-07-22T00:00:00Z"


def _sim(qty=100.0, fill_price=100.1, fees=5.005, slippage=0.1, ref=100.0,
         slip_bps=10.0, fee_bps=5.0, ts=_NOW, status="SIMULATED"):
    return {"simulation_id": "SIM:1", "status": status,
            "order": {"simulation_id": "SIM:1", "intent_id": "EI:1", "symbol": "A",
                      "side": "BUY", "quantity": qty, "reference_price": ref, "created_at": _NOW},
            "fill": {"simulation_id": "SIM:1", "fill_price": fill_price, "filled_quantity": qty,
                     "slippage": slippage, "fees": fees, "timestamp": ts},
            "assumptions": {"slippage_bps": slip_bps, "fee_bps": fee_bps, "reference_price": ref}}


def _exp(sim=None, **over):
    sim = sim or _sim()
    e = perfect_expectation(sim, _NOW)
    if over:
        d = e.to_dict()
        d.update(over)
        e = ExecutionExpectation(**d)
    return e


# ── 1. perfect simulation PASS ──
def test_perfect_simulation_pass():
    eng = ExecutionReconciliationEngine()
    sim = _sim()
    r = eng.validate(perfect_expectation(sim, _NOW), sim, _NOW)
    assert r.status == PASS
    assert all(c["status"] == PASS for c in r.checks)
    assert r.validation_id.startswith("VR:") and r.hash.startswith("sha256:")


def test_five_checks_present():
    eng = ExecutionReconciliationEngine()
    sim = _sim()
    r = eng.validate(perfect_expectation(sim, _NOW), sim, _NOW)
    names = [c["name"] for c in r.checks]
    for req in ("quantity", "price", "fee", "slippage", "timing"):
        assert req in names


# ── 2. quantity drift WARNING ──
def test_quantity_drift_warning():
    eng = ExecutionReconciliationEngine(ValidationThresholds(quantity_tolerance=1.0, fail_multiplier=3.0))
    sim = _sim(qty=100.0)
    # 기대 102 vs 실제 100 → dev 2 (>1 허용, ≤3 배수) → WARNING
    r = eng.validate(_exp(sim, expected_quantity=102.0), sim, _NOW)
    q = next(c for c in r.checks if c["name"] == "quantity")
    assert q["status"] == WARNING and r.status == WARNING


# ── 3. quantity drift FAILED ──
def test_quantity_drift_failed():
    eng = ExecutionReconciliationEngine(ValidationThresholds(quantity_tolerance=1.0, fail_multiplier=3.0))
    sim = _sim(qty=100.0)
    # 기대 110 vs 100 → dev 10 (>3 배수) → FAILED
    r = eng.validate(_exp(sim, expected_quantity=110.0), sim, _NOW)
    assert r.status == FAILED


# ── 4. price deviation detection ──
def test_price_deviation_detection():
    eng = ExecutionReconciliationEngine(ValidationThresholds(price_tolerance_bps=10.0, fail_multiplier=3.0))
    sim = _sim(fill_price=100.1)
    # 기대가 100.0 vs 체결 100.1 → 10bps → 경계(PASS). 기대 99.0 → ~110bps → FAILED
    r = eng.validate(_exp(sim, expected_price=99.0), sim, _NOW)
    p = next(c for c in r.checks if c["name"] == "price")
    assert p["status"] == FAILED and r.status == FAILED


# ── 5. fee deviation detection ──
def test_fee_deviation_detection():
    eng = ExecutionReconciliationEngine(ValidationThresholds(fee_tolerance_bps=5.0, fail_multiplier=3.0))
    sim = _sim(qty=100.0, fill_price=100.1, fees=5.005)
    # notional≈10010. 기대 fee 0 vs 실제 5.005 → ~5bps → 경계 WARNING권. 기대 0 아주 큰편차 위해 fees 큰 sim
    big = _sim(qty=100.0, fill_price=100.1, fees=200.0)
    r = eng.validate(_exp(big, expected_fee=5.005), big, _NOW)
    f = next(c for c in r.checks if c["name"] == "fee")
    assert f["status"] == FAILED and r.status == FAILED


# ── 6. slippage deviation detection ──
def test_slippage_deviation_detection():
    eng = ExecutionReconciliationEngine(ValidationThresholds(price_tolerance_bps=10.0, fail_multiplier=3.0))
    # 가정 slippage 10bps 인데 실현 slippage 5.0(=500bps of ref 100) → 큰 편차 → FAILED
    sim = _sim(slip_bps=10.0, slippage=5.0)
    r = eng.validate(perfect_expectation(sim, _NOW), sim, _NOW)
    s = next(c for c in r.checks if c["name"] == "slippage")
    assert s["status"] == FAILED


def test_slippage_match_pass():
    eng = ExecutionReconciliationEngine()
    # 가정 10bps, 실현 slippage 0.1 / ref 100 = 10bps → 일치 PASS
    sim = _sim(slip_bps=10.0, slippage=0.1, ref=100.0)
    r = eng.validate(perfect_expectation(sim, _NOW), sim, _NOW)
    s = next(c for c in r.checks if c["name"] == "slippage")
    assert s["status"] == PASS


# ── 7. timing violation ──
def test_timing_violation():
    eng = ExecutionReconciliationEngine(ValidationThresholds(timing_seconds=60.0, fail_multiplier=3.0))
    # 의도 00:00:00, 체결 00:10:00 → 600초 > 180 배수 → FAILED
    sim = _sim(ts="2026-07-22T00:10:00Z")
    r = eng.validate(_exp(sim), sim, _NOW)
    t = next(c for c in r.checks if c["name"] == "timing")
    assert t["status"] == FAILED and t["deviation"] == 600.0


# ── 8. missing simulation blocked ──
def test_missing_simulation_blocked():
    eng = ExecutionReconciliationEngine()
    exp = ExecutionExpectation("EI:x", "A", "BUY", 100.0, 100.0, 5.0, _NOW)
    r_none = eng.validate(exp, None, _NOW)
    assert r_none.status == FAILED
    assert r_none.checks[0]["name"] == "simulation_present"
    r_rej = eng.validate(exp, _sim(status="REJECTED"), _NOW)
    assert r_rej.status == FAILED


# ── 9. deterministic hash ──
def test_deterministic_hash():
    eng = ExecutionReconciliationEngine()
    sim = _sim()
    r1 = eng.validate(perfect_expectation(sim, _NOW), sim, _NOW)
    r2 = eng.validate(perfect_expectation(sim, _NOW), sim, _NOW)
    assert r1.hash == r2.hash and r1.to_dict() == r2.to_dict()
    r3 = eng.validate(_exp(sim, expected_quantity=999.0), sim, _NOW)
    assert r3.hash != r1.hash


def test_input_hash_present():
    eng = ExecutionReconciliationEngine()
    sim = _sim()
    r = eng.validate(perfect_expectation(sim, _NOW), sim, _NOW)
    assert r.input_hash.startswith("sha256:") and r.input_hash != r.hash


# ── 10. replay consistency ──
def test_replay_consistency(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.execution_reconciliation.ledger.state_path",
                        lambda name: os.path.join(tmp_path, name))
    eng = ExecutionReconciliationEngine()
    sim = _sim()
    committed = eng.validate(perfect_expectation(sim, _NOW), sim, _NOW, commit=True)
    replay = eng.validate(perfect_expectation(sim, _NOW), sim, _NOW, commit=False)
    assert replay.hash == committed.hash and replay.to_dict() == committed.to_dict()


# ── 11. append-only integrity ──
def test_append_only_integrity(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.execution_reconciliation.ledger.state_path",
                        lambda name: os.path.join(tmp_path, name))
    from jarvis.execution_reconciliation.ledger import read_events, read_reports
    eng = ExecutionReconciliationEngine()
    s1, s2 = _sim(), _sim()
    s2["simulation_id"] = "SIM:2"
    s2["order"]["intent_id"] = "EI:2"
    eng.validate(perfect_expectation(s1, _NOW), s1, _NOW, commit=True)
    eng.validate(perfect_expectation(s2, _NOW), s2, _NOW, commit=True)
    # 동일 validation_id 재커밋은 중복 방지(append-only, 재작성 없음)
    eng.validate(perfect_expectation(s1, _NOW), s1, _NOW, commit=True)
    assert len(read_reports()) == 2
    assert len(read_events()) == 2


# ── 12. no gateway import / no broker call ──
def test_no_execution_import():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.execution_reconciliation.{m}"))
        stripped = (src.replace("jarvis.execution_reconciliation", "")
                       .replace("jarvis.execution_control", "")
                       .replace("jarvis.execution_simulation", ""))
        assert "jarvis.execution" not in stripped   # 집행 게이트웨이/ARM 미import
        assert "gateway" not in src
        assert "place_order" not in src and "submit_order" not in src
        assert "create_order" not in src


def test_no_broker_call():
    import importlib
    import inspect
    src = inspect.getsource(importlib.import_module("jarvis.execution_reconciliation.engine"))
    for banned in ("broker", ".buy(", ".sell(", "cancel_order", "order_client"):
        assert banned not in src
    assert "jarvis.risk" not in src and "jarvis.registry" not in src
    assert "jarvis.paper_execution" not in src


# ── 13. no position mutation (paper + simulation ledgers immutable) ──
def test_no_position_mutation(tmp_path, monkeypatch):
    import hashlib

    def sp(name):
        return os.path.join(tmp_path, name)
    # 페이퍼 원장 시드
    import jarvis.paper_execution.ledger as pel
    monkeypatch.setattr(pel, "state_path", sp)
    from jarvis.paper_execution.engine import PaperExecutionEngine
    PaperExecutionEngine(capital=10000).execute_proposal(
        {"proposal_id": "PP:1", "strategy": "A", "allocation": {"A": 0.5}, "created_at": "t"},
        True, {"decision": "ALLOW"}, lambda s, ts: 100.0, "t", commit=True)
    pos_path = sp("paper_positions.jsonl")
    pos_before = hashlib.sha256(open(pos_path, "rb").read()).hexdigest()
    # 시뮬 원장 시드
    monkeypatch.setattr("jarvis.execution_simulation.ledger.state_path", sp)
    from jarvis.execution_control.models import ExecutionIntent
    from jarvis.execution_simulation.engine import SimulationEngine

    class _D:
        status = "READY"
    intent = ExecutionIntent("EI:1", "A", "A", "BUY", 100.0, 0.4, "PP:1", _NOW, "")
    SimulationEngine().simulate(intent, _D(), lambda s, n: 100.0, _NOW, commit=True)
    sim_path = sp("simulation_reports.jsonl")
    sim_before = hashlib.sha256(open(sim_path, "rb").read()).hexdigest()
    # 검증 실행(격리 원장)
    monkeypatch.setattr("jarvis.execution_reconciliation.ledger.state_path", sp)
    eng = ExecutionReconciliationEngine()
    sim = _sim()
    eng.validate(perfect_expectation(sim, _NOW), sim, _NOW, commit=True)
    assert hashlib.sha256(open(pos_path, "rb").read()).hexdigest() == pos_before   # 페이퍼 불변
    assert hashlib.sha256(open(sim_path, "rb").read()).hexdigest() == sim_before   # 시뮬 불변


# ── 14. no permission escalation ──
def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    # P7.6 전용 신규 권한 액션이 추가되지 않았는지(자가확장 없음)
    assert not any("execution_validation" in a for a in ACTION_PERMISSIONS)
    assert not any("execution_reconciliation" in a for a in ACTION_PERMISSIONS)
    assert not any("fill_validation" in a for a in ACTION_PERMISSIONS)
    # 기존 검증 프레임워크 액션은 불변(P7.6이 건드리지 않음)
    assert "change_validation_threshold" in ACTION_PERMISSIONS


# ── 15. report is validation-only (no order/execution fields) ──
def test_report_is_validation_only():
    eng = ExecutionReconciliationEngine()
    sim = _sim()
    r = eng.validate(perfect_expectation(sim, _NOW), sim, _NOW)
    keys = set(r.to_dict())
    assert keys == {"validation_id", "intent_id", "status", "checks", "deviations",
                    "timestamp", "input_hash", "hash"}
    for f in ("order_id", "broker", "venue", "gateway", "filled", "executed"):
        assert f not in keys
