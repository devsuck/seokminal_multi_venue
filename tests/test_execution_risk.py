"""P8.5 Execution Risk Enforcement 테스트.

전 규칙 PASS/WARNING/FAILED·ALLOW/BLOCK·kill switch·브로커 불가·스테일 시장·노출/레버리지/
드로다운 위반·긴급정지·결정적 리플레이·중복방지·append-only·체인무결성·금지import 없음·
집행경로 없음·브로커통신 없음·상태변경 없음·권한무결성.
"""
from __future__ import annotations

import os

from jarvis.execution_risk.engine import ExecutionRiskEngine
from jarvis.execution_risk.models import ALLOW, BLOCK, FAILED, PASS, WARNING
from jarvis.execution_risk.policy import ExecutionRiskPolicy, RiskContext

_NOW = "2026-07-22T00:00:00Z"
_REQ = {"request_id": "XRR:1", "symbol": "A", "side": "BUY", "quantity": 10.0, "limit_price": 100.0}


def _safe_ctx(**over):
    """모든 검사 PASS인 안전 컨텍스트."""
    base = dict(position_size=10.0, notional=1000.0, concentration=0.1,
                daily_realized_loss=0.0, drawdown=0.0, leverage=0.5, turnover=1.0,
                consecutive_failures=0, broker_healthy=True, market_fresh=True,
                trading_halted=False, kill_switch=False, emergency_stop=False)
    base.update(over)
    return RiskContext(**base)


def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.execution_risk.ledger.state_path",
                        lambda name: os.path.join(tmp_path, name))


def _check(report, name):
    return next(c for c in report.individual_checks if c["name"] == name)


# ── 1. all safe → ALLOW ──
def test_all_safe_allow():
    r = ExecutionRiskEngine().evaluate(_REQ, _safe_ctx(), now=_NOW)
    assert r.overall_status == ALLOW and r.failures == [] and r.warnings == []
    assert len(r.individual_checks) == 13
    assert all(c["status"] == PASS for c in r.individual_checks)


def test_thirteen_checks_present():
    r = ExecutionRiskEngine().evaluate(_REQ, _safe_ctx(), now=_NOW)
    names = {c["name"] for c in r.individual_checks}
    assert names == {"max_position_size", "max_notional_exposure", "portfolio_concentration",
                     "daily_realized_loss", "daily_drawdown", "max_leverage", "max_turnover",
                     "consecutive_failures", "broker_health", "market_data_freshness",
                     "trading_halt", "kill_switch", "emergency_stop"}


# ── 2. max position size FAILED ──
def test_max_position_size_breach():
    pol = ExecutionRiskPolicy(max_position_size=100.0)
    r = ExecutionRiskEngine().evaluate(_REQ, _safe_ctx(position_size=200.0), pol, now=_NOW)
    assert _check(r, "max_position_size")["status"] == FAILED and r.overall_status == BLOCK


# ── 3. max notional exposure breach ──
def test_max_notional_breach():
    pol = ExecutionRiskPolicy(max_notional=1000.0)
    r = ExecutionRiskEngine().evaluate(_REQ, _safe_ctx(notional=5000.0), pol, now=_NOW)
    assert _check(r, "max_notional_exposure")["status"] == FAILED and r.overall_status == BLOCK


# ── 4. concentration breach ──
def test_concentration_breach():
    pol = ExecutionRiskPolicy(max_concentration=0.35)
    r = ExecutionRiskEngine().evaluate(_REQ, _safe_ctx(concentration=0.9), pol, now=_NOW)
    assert _check(r, "portfolio_concentration")["status"] == FAILED and r.overall_status == BLOCK


# ── 5. daily realized loss breach ──
def test_daily_loss_breach():
    pol = ExecutionRiskPolicy(daily_loss_limit=1000.0)
    r = ExecutionRiskEngine().evaluate(_REQ, _safe_ctx(daily_realized_loss=5000.0), pol, now=_NOW)
    assert _check(r, "daily_realized_loss")["status"] == FAILED and r.overall_status == BLOCK


# ── 6. drawdown breach ──
def test_drawdown_breach():
    pol = ExecutionRiskPolicy(max_drawdown=0.2)
    r = ExecutionRiskEngine().evaluate(_REQ, _safe_ctx(drawdown=0.5), pol, now=_NOW)
    assert _check(r, "daily_drawdown")["status"] == FAILED and r.overall_status == BLOCK


# ── 7. leverage breach ──
def test_leverage_breach():
    pol = ExecutionRiskPolicy(max_leverage=1.0)
    r = ExecutionRiskEngine().evaluate(_REQ, _safe_ctx(leverage=3.0), pol, now=_NOW)
    assert _check(r, "max_leverage")["status"] == FAILED and r.overall_status == BLOCK


# ── 8. turnover breach ──
def test_turnover_breach():
    pol = ExecutionRiskPolicy(max_turnover=5.0)
    r = ExecutionRiskEngine().evaluate(_REQ, _safe_ctx(turnover=20.0), pol, now=_NOW)
    assert _check(r, "max_turnover")["status"] == FAILED and r.overall_status == BLOCK


# ── 9. consecutive failures breach ──
def test_consecutive_failures_breach():
    pol = ExecutionRiskPolicy(max_consecutive_failures=3)
    r = ExecutionRiskEngine().evaluate(_REQ, _safe_ctx(consecutive_failures=10), pol, now=_NOW)
    assert _check(r, "consecutive_failures")["status"] == FAILED and r.overall_status == BLOCK


# ── 10. broker unavailable ──
def test_broker_unavailable():
    r = ExecutionRiskEngine().evaluate(_REQ, _safe_ctx(broker_healthy=False), now=_NOW)
    assert _check(r, "broker_health")["status"] == FAILED and r.overall_status == BLOCK


# ── 11. stale market ──
def test_stale_market():
    r = ExecutionRiskEngine().evaluate(_REQ, _safe_ctx(market_fresh=False), now=_NOW)
    assert _check(r, "market_data_freshness")["status"] == FAILED and r.overall_status == BLOCK


# ── 12. trading halt ──
def test_trading_halt():
    r = ExecutionRiskEngine().evaluate(_REQ, _safe_ctx(trading_halted=True), now=_NOW)
    assert _check(r, "trading_halt")["status"] == FAILED and r.overall_status == BLOCK


# ── 13. kill switch ──
def test_kill_switch():
    r = ExecutionRiskEngine().evaluate(_REQ, _safe_ctx(kill_switch=True), now=_NOW)
    assert _check(r, "kill_switch")["status"] == FAILED and r.overall_status == BLOCK


# ── 14. emergency stop ──
def test_emergency_stop():
    r = ExecutionRiskEngine().evaluate(_REQ, _safe_ctx(emergency_stop=True), now=_NOW)
    assert _check(r, "emergency_stop")["status"] == FAILED and r.overall_status == BLOCK


# ── 15. WARNING band does not block ──
def test_warning_band_allows():
    pol = ExecutionRiskPolicy(max_leverage=1.0, warn_ratio=0.8)
    r = ExecutionRiskEngine().evaluate(_REQ, _safe_ctx(leverage=0.9), pol, now=_NOW)  # >0.8, <=1.0
    assert _check(r, "max_leverage")["status"] == WARNING
    assert r.overall_status == ALLOW and "max_leverage" in r.warnings


# ── 16. one FAILED always blocks (even amid passes) ──
def test_one_failed_blocks():
    r = ExecutionRiskEngine().evaluate(_REQ, _safe_ctx(kill_switch=True), now=_NOW)
    passes = [c for c in r.individual_checks if c["status"] == PASS]
    assert len(passes) == 12 and r.overall_status == BLOCK
    assert r.blocker_reason == "kill_switch"


# ── 17. deterministic hash ──
def test_deterministic_hash():
    eng = ExecutionRiskEngine()
    r1 = eng.evaluate(_REQ, _safe_ctx(), now=_NOW)
    r2 = eng.evaluate(_REQ, _safe_ctx(), now=_NOW)
    assert r1.report_hash == r2.report_hash and r1.to_dict() == r2.to_dict()
    r3 = eng.evaluate(_REQ, _safe_ctx(kill_switch=True), now=_NOW)
    assert r3.report_hash != r1.report_hash


def test_input_hash_present():
    r = ExecutionRiskEngine().evaluate(_REQ, _safe_ctx(), now=_NOW)
    assert r.input_hash.startswith("sha256:") and r.input_hash != r.report_hash


# ── 18. deterministic replay ──
def test_deterministic_replay(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.execution_risk.verify import replay
    eng = ExecutionRiskEngine()
    committed = eng.evaluate(_REQ, _safe_ctx(), now=_NOW, commit=True)
    res = replay(eng, _REQ, _safe_ctx(), None, _NOW)
    assert res["deterministic"] and res["report_hash"] == committed.report_hash


# ── 19. duplicate prevention ──
def test_duplicate_prevention(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.execution_risk.ledger import read_events
    eng = ExecutionRiskEngine()
    eng.evaluate(_REQ, _safe_ctx(), now=_NOW, commit=True)
    eng.evaluate(_REQ, _safe_ctx(), now=_NOW, commit=True)   # 동일 → 재추가 안 됨
    assert len(read_events()) == 1


# ── 20. append-only integrity + hash chain ──
def test_append_only_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.execution_risk.ledger import read_events
    from jarvis.execution_risk.verify import verify_chain
    eng = ExecutionRiskEngine()
    eng.evaluate({"request_id": "XRR:a"}, _safe_ctx(), now=_NOW, commit=True)
    eng.evaluate({"request_id": "XRR:b"}, _safe_ctx(), now=_NOW, commit=True)
    evs = read_events()
    assert len(evs) == 2
    assert evs[0]["previous_hash"] == "GENESIS"
    assert evs[1]["previous_hash"] == evs[0]["report_hash"]
    assert verify_chain()["ok"]


def test_corrupted_ledger_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.execution_risk.verify import verify_chain
    eng = ExecutionRiskEngine()
    eng.evaluate({"request_id": "XRR:a"}, _safe_ctx(), now=_NOW, commit=True)
    eng.evaluate({"request_id": "XRR:b"}, _safe_ctx(), now=_NOW, commit=True)
    import json
    p = os.path.join(tmp_path, "execution_risk_reports.jsonl")
    lines = open(p).read().splitlines()
    row = json.loads(lines[1]); row["previous_hash"] = "sha256:tampered"
    lines[1] = json.dumps(row)
    open(p, "w").write("\n".join(lines) + "\n")
    res = verify_chain()
    assert not res["ok"] and res["reason"] == "previous_hash_broken"


# ── 21. no forbidden imports / no execution path / no broker communication ──
def test_no_forbidden_imports():
    import importlib
    import inspect
    for m in ("models", "policy", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.execution_risk.{m}"))
        assert "jarvis.execution.gateway" not in src
        assert "jarvis.execution.arm" not in src
        assert "gateway" not in src
        assert "submit_order" not in src and "place_order" not in src
        assert "adapter" not in src and "broker_execution" not in src


def test_no_state_mutation_imports():
    import importlib
    import inspect
    for m in ("engine", "policy", "verify"):
        src = inspect.getsource(importlib.import_module(f"jarvis.execution_risk.{m}"))
        assert "jarvis.risk.governor" not in src   # 리스크 거버너 미변경/미호출
        assert "jarvis.registry" not in src
        assert "jarvis.portfolio" not in src
        assert "jarvis.paper_execution" not in src
        assert "jarvis.live_execution" not in src


def test_no_autonomous_trigger():
    import importlib
    import inspect
    for m in ("engine", "__main__", "verify"):
        src = inspect.getsource(importlib.import_module(f"jarvis.execution_risk.{m}"))
        assert "LiveExecutionEngine" not in src and "live_execution.engine" not in src


# ── 22. no position mutation ──
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
    monkeypatch.setattr("jarvis.execution_risk.ledger.state_path", sp)
    ExecutionRiskEngine().evaluate(_REQ, _safe_ctx(), now=_NOW, commit=True)
    assert hashlib.sha256(open(pos, "rb").read()).hexdigest() == before   # 페이퍼 불변


# ── 23. permission integrity ──
def test_permission_integrity():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    assert not any("execution_risk" in a for a in ACTION_PERMISSIONS)
    assert not any("kill_switch" in a for a in ACTION_PERMISSIONS)
