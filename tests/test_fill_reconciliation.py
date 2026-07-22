"""P8.3 Broker Fill Reconciliation 테스트.

정확일치·수량/가격/수수료/타이밍 불일치·부분체결 집계·가중평균·누락·예상밖·중복방지·
결정적 해시·append-only·리플레이·변조탐지·브로커 write 없음·집행 미import·포지션 불변·
권한 무변경.
"""
from __future__ import annotations

import os

from jarvis.fill_reconciliation.engine import FillReconciliationEngine
from jarvis.fill_reconciliation.matcher import aggregate, match
from jarvis.fill_reconciliation.models import (
    FAILED,
    MATCHED,
    WARNING,
    BrokerFill,
    FillThresholds,
    InternalExecutionRecord,
)

_SUB = "2026-07-22T00:00:00Z"


def _rec(oid="LXR:1", qty=100.0, price=100.0, side="BUY", req="LXR:1"):
    return InternalExecutionRecord(order_id=oid, request_id=req, expected_quantity=qty,
                                   expected_price=price, expected_side=side, submitted_at=_SUB)


def _fill(fid="F:1", boid="LXR:1", qty=100.0, price=100.0, fee=0.0, ts=_SUB, side="BUY"):
    return BrokerFill(fill_id=fid, broker_order_id=boid, symbol="A", side=side, quantity=qty,
                      fill_price=price, fee=fee, timestamp=ts, source="mock")


def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.fill_reconciliation.ledger.state_path",
                        lambda name: os.path.join(tmp_path, name))


# ── 1. exact fill match ──
def test_exact_fill_match():
    eng = FillReconciliationEngine()
    r = eng.reconcile(_rec(), [_fill()], _SUB)
    assert r.status == MATCHED
    assert r.checks["quantity_difference"] == 0.0
    assert r.checks["price_difference_bps"] == 0.0
    assert r.aggregate["total_quantity"] == 100.0
    assert r.report_hash.startswith("sha256:")


# ── 2. quantity mismatch ──
def test_quantity_mismatch():
    eng = FillReconciliationEngine(FillThresholds(quantity_tolerance=1.0, fail_multiplier=3.0))
    r = eng.reconcile(_rec(qty=100.0), [_fill(qty=90.0)], _SUB)   # dev 10 > 3 → FAILED
    assert r.status == FAILED and r.checks["quantity_difference"] == 10.0


# ── 3. price mismatch ──
def test_price_mismatch():
    eng = FillReconciliationEngine(FillThresholds(price_tolerance_bps=10.0, fail_multiplier=3.0))
    r = eng.reconcile(_rec(price=100.0), [_fill(price=101.0)], _SUB)   # 100bps > 30 → FAILED
    assert r.status == FAILED and r.checks["price_difference_bps"] == 100.0


# ── 4. fee mismatch ──
def test_fee_mismatch():
    eng = FillReconciliationEngine(FillThresholds(fee_tolerance=0.01, fail_multiplier=3.0))
    r = eng.reconcile(_rec(), [_fill(fee=5.0)], _SUB, expected_fee=0.0)   # dev 5 > 0.03 → FAILED
    assert r.status == FAILED and r.checks["fee_difference"] == 5.0


def test_fee_match_when_expected():
    eng = FillReconciliationEngine()
    r = eng.reconcile(_rec(), [_fill(fee=5.0)], _SUB, expected_fee=5.0)
    assert r.checks["fee_difference"] == 0.0


# ── 5. timing mismatch ──
def test_timing_mismatch():
    eng = FillReconciliationEngine(FillThresholds(timing_seconds=60.0, fail_multiplier=3.0))
    r = eng.reconcile(_rec(), [_fill(ts="2026-07-22T00:10:00Z")], _SUB)   # 600s > 180 → FAILED
    assert r.status == FAILED and r.checks["timing_difference_seconds"] == 600.0


# ── 6. partial fill aggregation ──
def test_partial_fill_aggregation():
    eng = FillReconciliationEngine()
    fills = [_fill("F:1", qty=30.0, ts="2026-07-22T00:00:01Z"),
             _fill("F:2", qty=70.0, ts="2026-07-22T00:00:02Z")]
    r = eng.reconcile(_rec(qty=100.0), fills, _SUB)
    assert r.aggregate["total_quantity"] == 100.0 and r.aggregate["n_fills"] == 2
    assert r.status == MATCHED


# ── 7. multiple fills weighted average ──
def test_multiple_fills_weighted_average():
    # 40@100 + 60@110 → wap = (4000+6600)/100 = 106.0
    fills = [_fill("F:1", qty=40.0, price=100.0), _fill("F:2", qty=60.0, price=110.0)]
    agg = aggregate(fills)
    assert agg["total_quantity"] == 100.0
    assert agg["weighted_average_price"] == 106.0


# ── 8. missing fill ──
def test_missing_fill():
    eng = FillReconciliationEngine()
    r = eng.reconcile(_rec(), [], _SUB)
    assert r.status == FAILED and r.reason == "missing_fill"
    assert r.aggregate["n_fills"] == 0


# ── 9. unexpected broker fill ──
def test_unexpected_broker_fill():
    eng = FillReconciliationEngine()
    # 내부 기록 없음 + 브로커가 알 수 없는 주문 체결 보고
    reports = eng.reconcile_batch([_rec("LXR:1")], [_fill(boid="UNKNOWN:99")], _SUB)
    unexpected = [r for r in reports if r.reason == "unexpected_fill"]
    missing = [r for r in reports if r.reason == "missing_fill"]
    assert len(unexpected) == 1 and unexpected[0].status == FAILED
    assert len(missing) == 1   # LXR:1은 체결 못 받음


# ── 10. duplicate fill prevention ──
def test_duplicate_fill_prevention():
    eng = FillReconciliationEngine()
    # 동일 fill_id 두 번 → 한 번만 집계
    r = eng.reconcile(_rec(qty=100.0), [_fill("F:1", qty=100.0), _fill("F:1", qty=100.0)], _SUB)
    assert r.aggregate["total_quantity"] == 100.0 and r.aggregate["n_fills"] == 1
    assert r.status == MATCHED


# ── 11. deterministic report hash ──
def test_deterministic_report_hash():
    eng = FillReconciliationEngine()
    r1 = eng.reconcile(_rec(), [_fill()], _SUB)
    r2 = eng.reconcile(_rec(), [_fill()], _SUB)
    assert r1.report_hash == r2.report_hash and r1.to_dict() == r2.to_dict()
    r3 = eng.reconcile(_rec(), [_fill(qty=50.0)], _SUB)
    assert r3.report_hash != r1.report_hash


def test_input_hash_present():
    eng = FillReconciliationEngine()
    r = eng.reconcile(_rec(), [_fill()], _SUB)
    assert r.input_hash.startswith("sha256:") and r.input_hash != r.report_hash


# ── 12. append-only ledger + hash chain ──
def test_append_only_ledger(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.fill_reconciliation.ledger import read_events
    eng = FillReconciliationEngine()
    eng.reconcile(_rec("LXR:a", req="LXR:a"), [_fill(boid="LXR:a")], _SUB, commit=True)
    eng.reconcile(_rec("LXR:b", req="LXR:b"), [_fill(boid="LXR:b")], _SUB, commit=True)
    evs = read_events()
    assert len(evs) == 2
    assert evs[0]["previous_hash"] == "GENESIS"
    assert evs[1]["previous_hash"] == evs[0]["report_hash"]   # 체인 연결


def test_duplicate_report_not_reappended(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.fill_reconciliation.ledger import read_events
    eng = FillReconciliationEngine()
    eng.reconcile(_rec(), [_fill()], _SUB, commit=True)
    eng.reconcile(_rec(), [_fill()], _SUB, commit=True)   # 동일 → 재추가 안 됨
    assert len(read_events()) == 1


# ── 13. replay recovery ──
def test_replay_recovery(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.fill_reconciliation.verify import replay
    eng = FillReconciliationEngine()
    committed = eng.reconcile(_rec(), [_fill()], _SUB, commit=True)
    res = replay(eng, _rec(), [_fill()], _SUB)
    assert res["deterministic"] and res["report_hash"] == committed.report_hash


# ── 14. corrupted ledger detection ──
def test_corrupted_ledger_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.fill_reconciliation.verify import verify_chain
    eng = FillReconciliationEngine()
    eng.reconcile(_rec("LXR:a", req="LXR:a"), [_fill(boid="LXR:a")], _SUB, commit=True)
    eng.reconcile(_rec("LXR:b", req="LXR:b"), [_fill(boid="LXR:b")], _SUB, commit=True)
    assert verify_chain()["ok"]
    # 원장 변조: 두번째 previous_hash 깨기
    import json
    p = os.path.join(tmp_path, "fill_reconciliation_events.jsonl")
    lines = open(p).read().splitlines()
    row = json.loads(lines[1]); row["previous_hash"] = "sha256:tampered"
    lines[1] = json.dumps(row)
    open(p, "w").write("\n".join(lines) + "\n")
    res = verify_chain()
    assert not res["ok"] and res["reason"] == "previous_hash_broken"


# ── matcher: broker_order_id primary / request_id fallback ──
def test_matcher_link_map_and_fallback():
    rec = _rec("LXR:1", req="REQ:1")
    # link_map 경유(broker_order_id → order_id)
    mr = match([rec], [_fill(boid="BRK:1")], link_map={"BRK:1": "LXR:1"})
    assert "LXR:1" in mr.matched and not mr.unexpected
    # fallback: broker_order_id가 request_id를 참조
    mr2 = match([rec], [_fill(boid="REQ:1")])
    assert "LXR:1" in mr2.matched


# ── 15. no broker write / no execution import ──
def test_no_broker_write_no_execution_import():
    import importlib
    import inspect
    for m in ("models", "matcher", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.fill_reconciliation.{m}"))
        assert "jarvis.execution" not in src        # 게이트웨이/arm 미import
        assert "gateway" not in src
        assert "submit_order" not in src and "place_order" not in src
        assert "adapter.submit" not in src
    eng = inspect.getsource(importlib.import_module("jarvis.fill_reconciliation.engine"))
    assert "jarvis.risk" not in eng and "jarvis.registry" not in eng
    assert "jarvis.paper_execution" not in eng


# ── 16. no autonomous trigger ──
def test_no_autonomous_trigger():
    import importlib
    import inspect
    for m in ("engine", "matcher", "__main__", "verify"):
        src = inspect.getsource(importlib.import_module(f"jarvis.fill_reconciliation.{m}"))
        assert "LiveExecutionEngine" not in src
        assert "live_execution.engine" not in src


# ── 17. no position mutation ──
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
    monkeypatch.setattr("jarvis.fill_reconciliation.ledger.state_path", sp)
    FillReconciliationEngine().reconcile(_rec(), [_fill()], _SUB, commit=True)
    assert hashlib.sha256(open(pos, "rb").read()).hexdigest() == before   # 페이퍼 불변


# ── 18. no permission escalation ──
def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    assert not any("fill_reconciliation" in a for a in ACTION_PERMISSIONS)
    assert not any("broker_fill" in a for a in ACTION_PERMISSIONS)


# ── warning band (등급 경계) ──
def test_warning_band():
    eng = FillReconciliationEngine(FillThresholds(quantity_tolerance=1.0, fail_multiplier=3.0))
    r = eng.reconcile(_rec(qty=100.0), [_fill(qty=98.0)], _SUB)   # dev 2 (>1, ≤3) → WARNING
    assert r.status == WARNING
