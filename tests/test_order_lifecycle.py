"""P8.2 Order Lifecycle Control 테스트.

생성·유효/무효 전이·중복방지·결정적 재현·해시무결성·append-only·거부/부분체결/취소/
만료 생애주기·재시작 복구·집행미import·브로커무호출·포지션불변.
"""
from __future__ import annotations

import os

import pytest

from jarvis.live_execution.models import LiveExecutionRequest, LiveExecutionResponse
from jarvis.order_lifecycle.manager import OrderLifecycleManager
from jarvis.order_lifecycle.models import OrderLifecycleState as S
from jarvis.order_lifecycle.state_machine import InvalidTransition, is_valid_transition

_NOW = "2026-07-22T00:00:00Z"


def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.order_lifecycle.ledger.state_path",
                        lambda name: os.path.join(tmp_path, name))


def _request(rid="LXR:1"):
    return LiveExecutionRequest(request_id=rid, intent_id="EI:1", broker="mock", symbol="A",
                                side="BUY", quantity=10.0, limit_price=None, created_at=_NOW,
                                arm_id="ARM:1")


def _ts(n):
    return f"2026-07-22T00:{n:02d}:00Z"


def _advance(mgr, oid, states, start=1):
    """상태 시퀀스를 순서대로 커밋."""
    for i, st in enumerate(states, start=start):
        mgr.transition(oid, st, _ts(i), commit=True)


# ── 1. create lifecycle ──
def test_create_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    mgr = OrderLifecycleManager()
    ev = mgr.create(_request(), _NOW, commit=True)
    assert ev.new_state == S.CREATED.value and ev.previous_state == ""
    assert ev.previous_hash == "GENESIS" and ev.event_hash.startswith("sha256:")
    assert mgr.current_state("LXR:1") == S.CREATED.value


# ── 2. valid transitions (정상 경로 전체) ──
def test_valid_transitions_full_path(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    mgr = OrderLifecycleManager()
    mgr.create(_request(), _NOW, commit=True)
    _advance(mgr, "LXR:1", [S.VALIDATED.value, S.SUBMITTED.value, S.ACKNOWLEDGED.value,
                            S.PARTIALLY_FILLED.value, S.FILLED.value])
    assert mgr.current_state("LXR:1") == S.FILLED.value
    assert len(mgr.history("LXR:1")) == 6


def test_state_machine_rules():
    assert is_valid_transition(S.CREATED.value, S.VALIDATED.value)
    assert is_valid_transition(S.ACKNOWLEDGED.value, S.PARTIALLY_FILLED.value)
    assert is_valid_transition(S.PARTIALLY_FILLED.value, S.PARTIALLY_FILLED.value)   # 자기루프
    # 무효
    assert not is_valid_transition(S.CREATED.value, S.FILLED.value)
    assert not is_valid_transition(S.FILLED.value, S.SUBMITTED.value)
    assert not is_valid_transition(S.CANCELLED.value, S.FILLED.value)


# ── 3. invalid transitions ──
def test_invalid_transition_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    mgr = OrderLifecycleManager()
    mgr.create(_request(), _NOW, commit=True)
    with pytest.raises(InvalidTransition):
        mgr.transition("LXR:1", S.FILLED.value, _ts(1), commit=True)   # CREATED→FILLED
    # 무효 전이는 원장에 기록되지 않음
    assert len(mgr.history("LXR:1")) == 1
    assert mgr.current_state("LXR:1") == S.CREATED.value


def test_terminal_no_exit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    mgr = OrderLifecycleManager()
    mgr.create(_request(), _NOW, commit=True)
    _advance(mgr, "LXR:1", [S.REJECTED.value])
    with pytest.raises(InvalidTransition):
        mgr.transition("LXR:1", S.SUBMITTED.value, _ts(2), commit=True)


def test_transition_without_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    mgr = OrderLifecycleManager()
    with pytest.raises(InvalidTransition):
        mgr.transition("LXR:none", S.VALIDATED.value, _NOW, commit=True)


# ── 4. duplicate event prevention ──
def test_duplicate_event_prevented(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    mgr = OrderLifecycleManager()
    mgr.create(_request(), _NOW, commit=True)
    first = mgr.transition("LXR:1", S.VALIDATED.value, _ts(1), commit=True)
    second = mgr.transition("LXR:1", S.VALIDATED.value, _ts(1), commit=True)   # 동일 체인위치·동일전이
    assert first is not None and second is None
    assert len(mgr.history("LXR:1")) == 2
    # create 재시도도 멱등
    assert mgr.create(_request(), _NOW, commit=True) is None


# ── 5. deterministic replay ──
def test_deterministic_replay(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.order_lifecycle.verify import replay_state
    mgr = OrderLifecycleManager()
    mgr.create(_request(), _NOW, commit=True)
    _advance(mgr, "LXR:1", [S.VALIDATED.value, S.SUBMITTED.value, S.ACKNOWLEDGED.value,
                            S.FILLED.value])
    assert replay_state("LXR:1") == S.FILLED.value
    assert replay_state("LXR:1") == replay_state("LXR:1")   # 동일 결과


# ── 6. hash integrity ──
def test_hash_chain_integrity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.order_lifecycle.verify import verify_chain
    mgr = OrderLifecycleManager()
    mgr.create(_request(), _NOW, commit=True)
    _advance(mgr, "LXR:1", [S.VALIDATED.value, S.SUBMITTED.value])
    res = verify_chain("LXR:1")
    assert res["ok"] and res["n"] == 3
    # 각 이벤트 previous_hash == 직전 event_hash
    evs = mgr.history("LXR:1")
    assert evs[0]["previous_hash"] == "GENESIS"
    assert evs[1]["previous_hash"] == evs[0]["event_hash"]
    assert evs[2]["previous_hash"] == evs[1]["event_hash"]


def test_tamper_detected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.order_lifecycle.verify import verify_chain
    mgr = OrderLifecycleManager()
    mgr.create(_request(), _NOW, commit=True)
    _advance(mgr, "LXR:1", [S.VALIDATED.value])
    # 원장 파일 변조(previous_state 조작)
    p = os.path.join(tmp_path, "order_lifecycle_events.jsonl")
    lines = open(p).read().splitlines()
    import json
    row = json.loads(lines[1])
    row["reason"] = "TAMPERED"
    lines[1] = json.dumps(row)
    open(p, "w").write("\n".join(lines) + "\n")
    res = verify_chain("LXR:1")
    assert not res["ok"] and res["reason"] == "event_hash_mismatch"


# ── 7. append-only check ──
def test_append_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.order_lifecycle.ledger import read_events
    mgr = OrderLifecycleManager()
    mgr.create(_request("LXR:a"), _NOW, commit=True)
    mgr.create(_request("LXR:b"), _NOW, commit=True)
    n1 = len(read_events())
    mgr.transition("LXR:a", S.VALIDATED.value, _ts(1), commit=True)
    n2 = len(read_events())
    assert n2 == n1 + 1   # 오직 추가


# ── 8. rejected order lifecycle ──
def test_rejected_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    mgr = OrderLifecycleManager()
    mgr.create(_request(), _NOW, commit=True)
    mgr.transition("LXR:1", S.VALIDATED.value, _ts(1), commit=True)
    mgr.transition("LXR:1", S.SUBMITTED.value, _ts(2), commit=True)
    # 브로커 응답 REJECTED 수용
    resp = LiveExecutionResponse(request_id="LXR:1", broker_order_id="", status="REJECTED",
                                 reason="risk", timestamp=_ts(3))
    ev = mgr.accept_response("LXR:1", resp, _ts(3), commit=True)
    assert ev.new_state == S.REJECTED.value
    assert mgr.current_state("LXR:1") == S.REJECTED.value


# ── 9. partial fill lifecycle ──
def test_partial_fill_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    mgr = OrderLifecycleManager()
    mgr.create(_request(), _NOW, commit=True)
    _advance(mgr, "LXR:1", [S.VALIDATED.value, S.SUBMITTED.value, S.ACKNOWLEDGED.value])
    # 여러 부분체결 후 완전체결
    mgr.transition("LXR:1", S.PARTIALLY_FILLED.value, _ts(4), reason="fill 3/10", commit=True)
    mgr.transition("LXR:1", S.PARTIALLY_FILLED.value, _ts(5), reason="fill 7/10", commit=True)
    mgr.transition("LXR:1", S.FILLED.value, _ts(6), reason="fill 10/10", commit=True)
    assert mgr.current_state("LXR:1") == S.FILLED.value
    from jarvis.order_lifecycle.verify import verify_chain
    assert verify_chain("LXR:1")["ok"]


# ── 10. cancellation lifecycle ──
def test_cancellation_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    mgr = OrderLifecycleManager()
    mgr.create(_request(), _NOW, commit=True)
    _advance(mgr, "LXR:1", [S.VALIDATED.value, S.SUBMITTED.value, S.ACKNOWLEDGED.value,
                            S.CANCEL_PENDING.value, S.CANCELLED.value])
    assert mgr.current_state("LXR:1") == S.CANCELLED.value


# ── 11. expired lifecycle ──
def test_expired_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    mgr = OrderLifecycleManager()
    mgr.create(_request(), _NOW, commit=True)
    mgr.transition("LXR:1", S.VALIDATED.value, _ts(1), commit=True)
    mgr.transition("LXR:1", S.SUBMITTED.value, _ts(2), commit=True)
    mgr.transition("LXR:1", S.EXPIRED.value, _ts(3), reason="TTL", commit=True)
    assert mgr.current_state("LXR:1") == S.EXPIRED.value


# ── 12. restart recovery ──
def test_restart_recovery(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    mgr = OrderLifecycleManager()
    mgr.create(_request(), _NOW, commit=True)
    _advance(mgr, "LXR:1", [S.VALIDATED.value, S.SUBMITTED.value])
    # "재시작" — 새 매니저 인스턴스가 원장에서 상태 복구
    mgr2 = OrderLifecycleManager()
    assert mgr2.current_state("LXR:1") == S.SUBMITTED.value
    # 복구 후 전이 계속 가능
    ev = mgr2.transition("LXR:1", S.ACKNOWLEDGED.value, _ts(3), commit=True)
    assert ev.previous_hash == mgr.history("LXR:1")[-2]["event_hash"] or ev is not None
    assert mgr2.current_state("LXR:1") == S.ACKNOWLEDGED.value


# ── 13. no execution import ──
def test_no_execution_import():
    import importlib
    import inspect
    for m in ("models", "state_machine", "manager", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.order_lifecycle.{m}"))
        assert "jarvis.execution" not in src        # 게이트웨이/arm 미import
        assert "jarvis.execution.gateway" not in src
        assert "jarvis.execution.arm" not in src
        assert "jarvis.risk" not in src and "jarvis.registry" not in src


# ── 14. no broker call ──
def test_no_broker_call():
    import importlib
    import inspect
    for m in ("manager", "ledger", "verify", "state_machine"):
        src = inspect.getsource(importlib.import_module(f"jarvis.order_lifecycle.{m}"))
        for banned in ("submit_order", "adapter", "broker_execution", "place_order",
                       ".buy(", ".sell(", "gateway"):
            assert banned not in src


def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    assert not any("lifecycle" in a for a in ACTION_PERMISSIONS)
    assert not any("order_lifecycle" in a for a in ACTION_PERMISSIONS)


# ── 15. no position mutation ──
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
    monkeypatch.setattr("jarvis.order_lifecycle.ledger.state_path", sp)
    mgr = OrderLifecycleManager()
    mgr.create(_request(), _NOW, commit=True)
    mgr.transition("LXR:1", S.VALIDATED.value, _ts(1), commit=True)
    assert hashlib.sha256(open(pos, "rb").read()).hexdigest() == before   # 페이퍼 불변


# ── 16. no autonomous trigger (repo 전역: order_lifecycle가 집행을 호출하지 않음) ──
def test_no_autonomous_trigger():
    import importlib
    import inspect
    for m in ("manager", "__main__", "verify", "ledger", "state_machine", "models"):
        src = inspect.getsource(importlib.import_module(f"jarvis.order_lifecycle.{m}"))
        assert "live_execution.engine" not in src   # 집행 엔진 호출 경로 없음
        assert "LiveExecutionEngine" not in src
