"""P8.1 Live Execution Adapter 테스트. **첫 라이브 집행 경계 — 사람 게이트 전용.**

READY+ARM→mock 제출 · ARM 없음/READY BLOCKED/수량/스테일 → 차단 · 중복 방지 ·
결정적 request/response 해시 · 어댑터 격리 · 자리표시자 비활성 · 자율 트리거 없음 ·
append-only · 하위 레이어 불변.
"""
from __future__ import annotations

import os

from jarvis.execution_control.models import ExecutionIntent
from jarvis.execution_readiness.models import ExecutionReadinessCertificate
from jarvis.live_execution.adapters import (
    IBExecutionAdapter,
    KISExecutionAdapter,
    MockExecutionAdapter,
)
from jarvis.live_execution.engine import LiveExecutionEngine, build_request
from jarvis.live_execution.models import ACCEPTED, REJECTED

_NOW = "2026-07-22T00:00:00Z"


def _intent(qty=10.0, symbol="A", iid="EI:1"):
    return ExecutionIntent(iid, "A", symbol, "BUY", qty, 0.4, "PP:1", _NOW, "")


def _cert(status="READY", iid="EI:1"):
    return ExecutionReadinessCertificate(certificate_id="CERT:1", status=status,
                                         intent_id=iid, created_at=_NOW)


def _req(intent=None, arm_id="ARM:1", broker="mock"):
    return build_request(intent or _intent(), arm_id, broker, _NOW)


# ── 1. READY + ARM allows mock submission ──
def test_ready_arm_allows_mock_submission():
    eng = LiveExecutionEngine()
    resp = eng.submit(_req(), _cert(), MockExecutionAdapter(), _NOW,
                      arm_present=True, market_fresh=True)
    assert resp.status == ACCEPTED
    assert resp.broker_order_id.startswith("MOCK:")
    assert resp.response_hash.startswith("sha256:")


# ── 2. missing ARM blocks ──
def test_missing_arm_blocks():
    eng = LiveExecutionEngine()
    resp = eng.submit(_req(), _cert(), MockExecutionAdapter(), _NOW,
                      arm_present=False, market_fresh=True)
    assert resp.status == REJECTED and "no_human_arm" in resp.reason
    assert resp.broker_order_id == ""


# ── 3. readiness BLOCKED blocks ──
def test_readiness_blocked_blocks():
    eng = LiveExecutionEngine()
    resp = eng.submit(_req(), _cert(status="BLOCKED"), MockExecutionAdapter(), _NOW,
                      arm_present=True, market_fresh=True)
    assert resp.status == REJECTED and "readiness_not_ready" in resp.reason


# ── 4. invalid quantity blocks ──
def test_invalid_quantity_blocks():
    eng = LiveExecutionEngine()
    resp = eng.submit(_req(_intent(qty=0.0)), _cert(), MockExecutionAdapter(), _NOW,
                      arm_present=True, market_fresh=True)
    assert resp.status == REJECTED and "invalid_quantity" in resp.reason


# ── 5. stale market blocks ──
def test_stale_market_blocks():
    eng = LiveExecutionEngine()
    resp = eng.submit(_req(), _cert(), MockExecutionAdapter(), _NOW,
                      arm_present=True, market_fresh=False)
    assert resp.status == REJECTED and "stale_market_data" in resp.reason


def test_certificate_intent_mismatch_blocks():
    eng = LiveExecutionEngine()
    # 요청 의도 EI:1, 인증서 의도 EI:other → 불일치 차단
    resp = eng.submit(_req(), _cert(iid="EI:other"), MockExecutionAdapter(), _NOW,
                      arm_present=True, market_fresh=True)
    assert resp.status == REJECTED and "certificate_intent_mismatch" in resp.reason


def test_gates_never_call_broker_on_failure():
    # 게이트 실패 시 어댑터.submit_order 호출 안 됨(브로커 미접촉)
    calls = {"n": 0}

    class _Spy(MockExecutionAdapter):
        def submit_order(self, request):
            calls["n"] += 1
            return super().submit_order(request)
    eng = LiveExecutionEngine()
    eng.submit(_req(), _cert(status="BLOCKED"), _Spy(), _NOW, arm_present=False, market_fresh=False)
    assert calls["n"] == 0


# ── 6. duplicate request prevented ──
def test_duplicate_request_prevented(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.live_execution.ledger.state_path",
                        lambda name: os.path.join(tmp_path, name))
    eng = LiveExecutionEngine()
    first = eng.submit(_req(), _cert(), MockExecutionAdapter(), _NOW,
                       arm_present=True, market_fresh=True, commit=True)
    second = eng.submit(_req(), _cert(), MockExecutionAdapter(), _NOW,
                        arm_present=True, market_fresh=True, commit=True)
    assert first is not None and second is None
    from jarvis.live_execution.ledger import read_requests
    assert len(read_requests()) == 1


# ── 7. deterministic request hash ──
def test_deterministic_request_hash():
    from jarvis.live_execution.models import request_hash
    r1 = _req()
    r2 = _req()
    assert r1.request_id == r2.request_id
    assert request_hash(r1.to_dict()) == request_hash(r2.to_dict())


# ── 8. deterministic response hash ──
def test_deterministic_response_hash():
    eng = LiveExecutionEngine()
    a = eng.submit(_req(), _cert(), MockExecutionAdapter(), _NOW, arm_present=True, market_fresh=True)
    b = eng.submit(_req(), _cert(), MockExecutionAdapter(), _NOW, arm_present=True, market_fresh=True)
    assert a.response_hash == b.response_hash and a.to_dict() == b.to_dict()
    # 상태가 바뀌면 해시도 바뀜
    c = eng.submit(_req(), _cert(), MockExecutionAdapter(), _NOW, arm_present=False, market_fresh=True)
    assert c.response_hash != a.response_hash


# ── 9. adapter isolation ──
def test_adapter_isolation():
    # 어댑터는 게이트 판단을 하지 않음 — 엔진 게이트만 담당. mock은 늘 수락(자본 없음).
    mock = MockExecutionAdapter()
    r = mock.submit_order({"request_id": "LXR:x"})
    assert r["accepted"] is True and r["broker_order_id"].startswith("MOCK:")
    # ABC는 직접 인스턴스화 불가
    from jarvis.live_execution.adapters import BrokerExecutionAdapter
    import pytest
    with pytest.raises(TypeError):
        BrokerExecutionAdapter()


# ── 10. broker placeholder disabled ──
def test_broker_placeholder_disabled():
    for A in (IBExecutionAdapter, KISExecutionAdapter):
        a = A()
        h = a.health_check()
        assert h["enabled"] is False and h["connected"] is False
        r = a.submit_order({"request_id": "LXR:x"})
        assert r["accepted"] is False and "adapter_disabled" in r["reason"]


def test_live_adapter_rejected_even_with_ready_arm():
    # READY+ARM+신선해도 실브로커 어댑터는 비활성 → REJECTED(honest CLOSED)
    eng = LiveExecutionEngine()
    resp = eng.submit(_req(broker="ib"), _cert(), IBExecutionAdapter(), _NOW,
                      arm_present=True, market_fresh=True)
    assert resp.status == REJECTED and "adapter_disabled" in resp.reason


# ── 11. no autonomous trigger (repo-wide: nothing outside live_execution imports it) ──
def test_no_autonomous_trigger():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "jarvis"
    offenders = []
    for py in root.rglob("*.py"):
        rel = py.relative_to(root.parent).as_posix()
        if rel.startswith("jarvis/live_execution/"):
            continue
        txt = py.read_text(encoding="utf-8", errors="ignore")
        if "jarvis.live_execution" in txt or "import live_execution" in txt:
            offenders.append(rel)
    # 스케줄러/플래너/포트폴리오/전략 어느 것도 집행을 호출하지 않음
    assert offenders == [], f"live_execution imported by: {offenders}"


def test_scheduler_planner_portfolio_cannot_call_execution():
    import importlib
    import inspect
    for mod in ("jarvis.planner.planner", "jarvis.portfolio.orchestrator",
                "jarvis.paper_execution.runner"):
        src = inspect.getsource(importlib.import_module(mod))
        assert "live_execution" not in src


# ── 12. append-only integrity ──
def test_append_only_integrity(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.live_execution.ledger.state_path",
                        lambda name: os.path.join(tmp_path, name))
    from jarvis.live_execution.ledger import read_events, read_requests, read_responses
    eng = LiveExecutionEngine()
    eng.submit(_req(_intent(iid="EI:a"), arm_id="ARM:a"), _cert(iid="EI:a"),
               MockExecutionAdapter(), _NOW, arm_present=True, market_fresh=True, commit=True)
    eng.submit(_req(_intent(iid="EI:b"), arm_id="ARM:b"), _cert(iid="EI:b"),
               MockExecutionAdapter(), _NOW, arm_present=False, market_fresh=True, commit=True)
    assert len(read_requests()) == 2 and len(read_responses()) == 2 and len(read_events()) == 2
    # request 원장에 request_hash 포함
    assert all("request_hash" in r for r in read_requests())


# ── 13. no permission escalation ──
def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    assert not any("live_execution" in a for a in ACTION_PERMISSIONS)


# ── 14. risk/registry/paper/simulation unchanged (no import → no mutation) ──
def test_no_downstream_mutation_imports():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "adapters"):
        src = inspect.getsource(importlib.import_module(f"jarvis.live_execution.{m}"))
        assert "jarvis.risk" not in src
        assert "jarvis.registry" not in src
        assert "jarvis.paper_execution" not in src
        assert "jarvis.execution_simulation" not in src
        assert "jarvis.execution.gateway" not in src   # 기존 게이트웨이 미import


def test_paper_ledger_immutable(tmp_path, monkeypatch):
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
    monkeypatch.setattr("jarvis.live_execution.ledger.state_path", sp)
    eng = LiveExecutionEngine()
    eng.submit(_req(), _cert(), MockExecutionAdapter(), _NOW,
               arm_present=True, market_fresh=True, commit=True)
    assert hashlib.sha256(open(pos, "rb").read()).hexdigest() == before   # 페이퍼 불변
