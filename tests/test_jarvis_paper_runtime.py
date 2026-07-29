"""P6.5 Paper Trading Runtime Loop 테스트.

deterministic replay · no lookahead · missing data · stale feed · append-only ·
no execution capability · restart recovery.
"""
from __future__ import annotations

import os

import pytest

from jarvis.market_data.adapters import CSVHistoricalProvider
from jarvis.market_data.bridge import paper_valuation_provider
from jarvis.paper_execution.engine import PaperExecutionEngine
from jarvis.paper_execution.runner import PaperTradingRunner, RuntimeConfig, read_runtime_events


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    import jarvis.audit.log as al
    import jarvis.market_data.cache as mc
    import jarvis.paper_execution.ledger as pl
    import jarvis.paper_execution.runner as rn
    import jarvis.paper_execution.valuation as vv
    monkeypatch.setattr(al, "state_path", sp)
    monkeypatch.setattr(mc, "state_path", sp)
    monkeypatch.setattr(pl, "state_path", sp)
    monkeypatch.setattr(rn, "state_path", sp)
    monkeypatch.setattr(vv, "state_path", sp)
    return sp


_ALLOW = {"decision": "ALLOW", "failed_checks": []}


def _seed_position(strategy="AAA", weight=0.5, price=100.0, capital=10000.0, pid="PP:1"):
    PaperExecutionEngine(capital=capital).execute_proposal(
        {"proposal_id": pid, "strategy": strategy, "allocation": {strategy: weight},
         "created_at": "2026-07-22T00:00:00Z"},
        True, _ALLOW, lambda s, ts: price, "2026-07-22T01:00:00Z", commit=True)


def _md_rows():
    return [{"symbol": "AAA", "timestamp": "2026-07-22T00:00:00Z", "price": "120"},
            {"symbol": "AAA", "timestamp": "2026-08-01T00:00:00Z", "price": "999"}]  # 미래


def _provider(positions_capital=10000.0):
    from jarvis.paper_execution.ledger import current_positions
    positions = list(current_positions().values())
    return paper_valuation_provider(CSVHistoricalProvider(rows=_md_rows()), positions)


# ── 1. deterministic replay ──
def test_deterministic_replay():
    _seed_position(capital=10000.0)
    runner = PaperTradingRunner(config=RuntimeConfig(capital=10000.0, frequency="manual"))
    prov = _provider()
    e1 = runner.run_once("2026-07-22T12:00:00Z", provider=prov)
    e2 = runner.run_once("2026-07-22T12:00:00Z", provider=prov)
    assert e1.to_dict() == e2.to_dict()
    assert e1.valuation_status == "OK" and e1.nav is not None


# ── 2. no lookahead ──
def test_no_lookahead():
    _seed_position(capital=10000.0)
    runner = PaperTradingRunner(config=RuntimeConfig(capital=10000.0, frequency="manual"))
    # as-of 07-22 → 미래 999(08-01)를 안 봄 → mark 120 사용
    e = runner.run_once("2026-07-22T12:00:00Z", provider=_provider())
    # 50주 @avg100, mark120 → nav = cash5000 + 50*120 = 11000
    assert abs(e.nav - 11000.0) < 1e-3


# ── 3. missing data handling ──
def test_missing_data_uses_fallback():
    _seed_position(strategy="NODATA", capital=10000.0)
    runner = PaperTradingRunner(config=RuntimeConfig(capital=10000.0))
    prov = _provider()   # CSV엔 AAA만 → NODATA는 flat-mark 폴백
    e = runner.run_once("2026-07-22T12:00:00Z", provider=prov)
    assert e.valuation_status == "OK"
    assert e.data_quality["fallback"] >= 1
    assert any("fallback" in w for w in e.warnings)


# ── 4. stale feed handling ──
def test_stale_feed_flagged():
    _seed_position(strategy="AAA", capital=10000.0)
    stale_rows = [{"symbol": "AAA", "timestamp": "2026-06-01T00:00:00Z", "price": "120"}]
    from jarvis.paper_execution.ledger import current_positions
    positions = list(current_positions().values())
    prov = paper_valuation_provider(CSVHistoricalProvider(rows=stale_rows, stale_hours=24), positions)
    runner = PaperTradingRunner(config=RuntimeConfig(capital=10000.0))
    e = runner.run_once("2026-07-22T12:00:00Z", provider=prov)
    assert e.data_quality["stale"] >= 1 and any("stale" in w for w in e.warnings)


# ── 5. append-only integrity ──
def test_append_only_integrity(_isolate):
    _seed_position(capital=10000.0)
    runner = PaperTradingRunner(config=RuntimeConfig(capital=10000.0, frequency="manual"))
    runner.run_once("2026-07-22T12:00:00Z", commit=True, provider=_provider())
    runner.run_once("2026-07-23T12:00:00Z", commit=True, provider=_provider())
    rows = read_runtime_events()
    assert len(rows) == 2 and all(r["capital"] == "paper" for r in rows)


def test_dry_run_no_mutation(_isolate):
    _seed_position(capital=10000.0)
    PaperTradingRunner(config=RuntimeConfig(capital=10000.0)).run_once(
        "2026-07-22T12:00:00Z", commit=False, provider=_provider())
    assert read_runtime_events() == []


# ── 6. no execution capability ──
def test_no_execution_gateway_or_governor(monkeypatch):
    import jarvis.execution.gateway as gw
    import jarvis.risk.governor as rg
    gcalled = {"x": False}
    monkeypatch.setattr(gw.ExecutionGateway, "execute", lambda *a, **k: gcalled.__setitem__("x", True))
    monkeypatch.setattr(rg.RiskGovernor, "check",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("governor called")))
    _seed_position(capital=10000.0)
    PaperTradingRunner(config=RuntimeConfig(capital=10000.0)).run_once(
        "2026-07-22T12:00:00Z", commit=True, provider=_provider())
    assert gcalled["x"] is False


# ── 7. restart recovery (스케줄 판단) ──
def test_restart_recovery_daily_schedule():
    _seed_position(capital=10000.0)
    cfg = RuntimeConfig(capital=10000.0, frequency="daily")
    r1 = PaperTradingRunner(config=cfg)
    r1.run("2026-07-22T00:00:00Z", commit=True, provider=_provider())   # 최초 실행
    # 재시작(새 인스턴스): 같은 날 → SKIPPED
    r2 = PaperTradingRunner(config=cfg)
    same_day = r2.run("2026-07-22T06:00:00Z", commit=False, provider=_provider())
    assert same_day.valuation_status == "SKIPPED" and same_day.reason == "not_due"
    # 다음 날 → 실행
    next_day = r2.run("2026-07-23T06:00:00Z", commit=False, provider=_provider())
    assert next_day.valuation_status == "OK"


# ── 실패 우아처리 ──
def test_corrupted_state_handled(monkeypatch):
    _seed_position(capital=10000.0)
    import jarvis.paper_execution.ledger as pl
    monkeypatch.setattr(pl, "current_positions",
                        lambda: (_ for _ in ()).throw(RuntimeError("corrupt")))
    e = PaperTradingRunner(config=RuntimeConfig(capital=10000.0)).run_once("2026-07-22T12:00:00Z")
    assert e.valuation_status == "FAILED" and "corrupted_state" in e.warnings[0]


def test_empty_state_graceful():
    e = PaperTradingRunner(config=RuntimeConfig(capital=10000.0)).run_once("2026-07-22T12:00:00Z")
    assert e.valuation_status == "OK" and abs(e.nav - 10000.0) < 1e-6
    assert e.data_quality["n_symbols"] == 0


# ── 권한 게이팅 ──
def test_runtime_commit_requires_permission(monkeypatch):
    # _commit이 record_paper_runtime 권한 요구 — PAPER_EXECUTION_AGENT는 통과.
    _seed_position(capital=10000.0)
    runner = PaperTradingRunner(config=RuntimeConfig(capital=10000.0))
    e = runner.run_once("2026-07-22T12:00:00Z", commit=True, provider=_provider())
    assert e.valuation_status == "OK"
    from jarvis.audit.log import read_all
    assert any(a.get("action") == "record_paper_runtime" and a.get("result") == "recorded"
               for a in read_all())
