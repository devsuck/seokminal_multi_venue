"""P8.7 Post-Trade Analytics & TCA 테스트. **ANALYTICS-ONLY.**

PASS/WARNING/FAILED·누락(벤치마크/체결/집행)·VWAP·TWAP·Arrival·IS·Market Impact·Spread·
포트폴리오집계·해시체인·리플레이·결정성·변조탐지·중복방지·CLI·금지import없음·집행능력없음·
상태변경없음.
"""
from __future__ import annotations

import os

from jarvis.post_trade_analytics import benchmarks as B
from jarvis.post_trade_analytics.engine import PostTradeAnalyticsEngine
from jarvis.post_trade_analytics.models import ExecutionData, FAILED, PASS, WARNING

_NOW = "2026-07-22T00:01:00Z"


def _fills():
    return [{"fill_id": "F:1", "quantity": 40.0, "fill_price": 100.0, "fee": 0.0,
             "timestamp": "2026-07-22T00:00:01Z"},
            {"fill_id": "F:2", "quantity": 60.0, "fill_price": 100.5, "fee": 0.0,
             "timestamp": "2026-07-22T00:00:03Z"}]


def _exec(**over):
    base = dict(request_id="LXR:1", symbol="A", side="BUY", order_quantity=100.0,
                fills=_fills(), arrival_price=100.0, decision_price=99.9, close_price=100.6,
                mid_price=100.1, start_time="2026-07-22T00:00:00Z",
                end_time="2026-07-22T00:00:05Z", broker="mock", strategy="S1")
    base.update(over)
    return ExecutionData(**base)


def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.post_trade_analytics.ledger.state_path",
                        lambda name: os.path.join(tmp_path, name))


# ── benchmark pure functions ──
def test_vwap():
    # 40@100 + 60@100.5 = (4000+6030)/100 = 100.3
    assert B.vwap(_fills()) == 100.3


def test_twap():
    # 단순평균 (100+100.5)/2 = 100.25
    assert B.twap(_fills()) == 100.25


def test_vwap_dedup():
    f = _fills() + [_fills()[0]]   # 중복 fill_id
    assert B.total_quantity(f) == 100.0


def test_arrival_slippage():
    # BUY, arrival 100, exec 100.3 → (100.3-100)/100*1e4 = 30bps 불리
    assert B.slippage_bps("BUY", 100.0, 100.3) == 30.0
    # SELL 유리(비싸게) → 음수
    assert B.slippage_bps("SELL", 100.0, 100.3) == -30.0


def test_implementation_shortfall():
    assert B.implementation_shortfall_bps("BUY", 99.9, 100.3) is not None
    assert B.implementation_shortfall_bps("BUY", None, 100.3) is None   # decision 없음


def test_market_impact():
    assert B.market_impact_bps("BUY", 100.0, 100.3) == 30.0


def test_effective_spread():
    # exec 100.3, mid 100.1 → 2*|0.2|/100.1*1e4
    assert B.effective_spread_bps(100.3, 100.1) == round(2 * 0.2 / 100.1 * 10000, 8)


def test_realized_spread_and_opportunity():
    assert B.realized_spread_bps("BUY", 100.3, None) is None
    assert B.opportunity_cost("BUY", 0.0, 99.9, 100.6) == 0.0
    assert B.opportunity_cost("BUY", 10.0, 100.0, 101.0) == 10.0   # 1*10


# ── 1. PASS path ──
def test_pass_path():
    r = PostTradeAnalyticsEngine().analyze("LXR:1", _exec(), _NOW)
    assert r.overall_status == PASS and r.errors == [] and r.warnings == []
    assert r.benchmarks["execution_price"] == 100.3
    assert r.benchmarks["market_impact_bps"] == 30.0
    assert r.report_hash.startswith("sha256:")


def test_metrics_present():
    r = PostTradeAnalyticsEngine().analyze("LXR:1", _exec(), _NOW)
    for k in ("execution_price", "average_fill_size", "fill_efficiency", "partial_fill_ratio",
              "execution_duration_seconds", "price_improvement_bps", "liquidity_score",
              "execution_score", "execution_alpha_bps", "execution_beta", "cost_breakdown"):
        assert k in r.metrics
    assert r.metrics["fill_efficiency"] == 1.0
    assert r.metrics["average_fill_size"] == 50.0
    assert r.metrics["execution_duration_seconds"] == 5.0


def test_benchmarks_present():
    r = PostTradeAnalyticsEngine().analyze("LXR:1", _exec(), _NOW)
    for k in ("arrival_price", "decision_price", "vwap", "twap", "close_price",
              "implementation_shortfall_bps", "effective_spread_bps", "market_impact_bps",
              "opportunity_cost", "slippage_attribution", "cost_attribution",
              "benchmark_difference_bps"):
        assert k in r.benchmarks


# ── 2. WARNING path (optional benchmark missing) ──
def test_warning_missing_optional_benchmark():
    r = PostTradeAnalyticsEngine().analyze("LXR:1", _exec(decision_price=None), _NOW)
    assert r.overall_status == WARNING
    assert any("decision_price" in w for w in r.warnings)


def test_warning_missing_close():
    r = PostTradeAnalyticsEngine().analyze("LXR:1", _exec(close_price=None), _NOW)
    assert r.overall_status == WARNING and any("close_price" in w for w in r.warnings)


# ── 3. FAILED path (required benchmark missing) ──
def test_failed_missing_arrival():
    r = PostTradeAnalyticsEngine().analyze("LXR:1", _exec(arrival_price=None), _NOW)
    assert r.overall_status == FAILED
    assert any("arrival" in e for e in r.errors)


# ── 4. missing fills ──
def test_failed_missing_fills():
    r = PostTradeAnalyticsEngine().analyze("LXR:1", _exec(fills=[]), _NOW)
    assert r.overall_status == FAILED and "missing_fills" in r.errors


# ── 5. missing execution ──
def test_failed_missing_execution():
    r = PostTradeAnalyticsEngine().analyze("", {}, _NOW)
    assert r.overall_status == FAILED and "missing_execution" in r.errors


# ── 6. portfolio aggregation ──
def test_portfolio_aggregation():
    trades = [{"request_id": "A", "cost_bps": 10.0, "slippage_bps": 5.0, "fill_quality": 0.9,
               "success": True, "broker": "mock", "symbol": "A", "strategy": "S1"},
              {"request_id": "B", "cost_bps": 30.0, "slippage_bps": 20.0, "fill_quality": 0.5,
               "success": False, "broker": "ib", "symbol": "B", "strategy": "S2"},
              {"request_id": "C", "cost_bps": 20.0, "slippage_bps": 10.0, "fill_quality": 0.7,
               "success": True, "broker": "mock", "symbol": "A", "strategy": "S1"}]
    s = PostTradeAnalyticsEngine().portfolio_summary(trades, "daily", _NOW)
    assert s.n_trades == 3
    assert s.average_cost_bps == 20.0 and s.median_cost_bps == 20.0
    assert s.worst_trade["request_id"] == "B" and s.best_trade["request_id"] == "A"
    assert s.execution_success_rate == round(2 / 3, 8)
    assert s.cost_by_broker == {"ib": 30.0, "mock": 15.0}   # mock=(10+20)/2
    assert s.cost_by_symbol["A"] == 15.0 and s.cost_by_strategy["S1"] == 15.0


def test_portfolio_periods():
    eng = PostTradeAnalyticsEngine()
    trades = [{"request_id": "A", "cost_bps": 10.0, "success": True}]
    for period in ("daily", "weekly", "monthly"):
        s = eng.portfolio_summary(trades, period, _NOW)
        assert s.period == period and s.n_trades == 1


# ── 7. hash chain (append-only) ──
def test_append_only_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.post_trade_analytics.ledger import read_reports
    from jarvis.post_trade_analytics.verify import verify_chain
    eng = PostTradeAnalyticsEngine()
    eng.analyze("LXR:a", _exec(request_id="LXR:a"), _NOW, commit=True)
    eng.analyze("LXR:b", _exec(request_id="LXR:b"), _NOW, commit=True)
    reps = read_reports()
    assert len(reps) == 2
    assert reps[0]["previous_hash"] == "GENESIS"
    assert reps[1]["previous_hash"] == reps[0]["report_hash"]
    assert verify_chain()["ok"]


# ── 8. replay ──
def test_replay(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.post_trade_analytics.verify import replay
    eng = PostTradeAnalyticsEngine()
    committed = eng.analyze("LXR:1", _exec(), _NOW, commit=True)
    res = replay(eng, "LXR:1", _exec(), _NOW)
    assert res["deterministic"] and res["report_hash"] == committed.report_hash


# ── 9. determinism ──
def test_determinism():
    eng = PostTradeAnalyticsEngine()
    r1 = eng.analyze("LXR:1", _exec(), _NOW)
    r2 = eng.analyze("LXR:1", _exec(), _NOW)
    assert r1.report_hash == r2.report_hash and r1.to_dict() == r2.to_dict()
    r3 = eng.analyze("LXR:1", _exec(arrival_price=99.0), _NOW)
    assert r3.report_hash != r1.report_hash


def test_input_hash_present():
    r = PostTradeAnalyticsEngine().analyze("LXR:1", _exec(), _NOW)
    assert r.input_hash.startswith("sha256:") and r.input_hash != r.report_hash


# ── 10. tampering detection ──
def test_tampering_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.post_trade_analytics.verify import verify_chain
    eng = PostTradeAnalyticsEngine()
    eng.analyze("LXR:a", _exec(request_id="LXR:a"), _NOW, commit=True)
    eng.analyze("LXR:b", _exec(request_id="LXR:b"), _NOW, commit=True)
    import json
    p = os.path.join(tmp_path, "post_trade_reports.jsonl")
    lines = open(p).read().splitlines()
    row = json.loads(lines[1]); row["previous_hash"] = "sha256:tampered"
    lines[1] = json.dumps(row)
    open(p, "w").write("\n".join(lines) + "\n")
    res = verify_chain()
    assert not res["ok"] and res["reason"] == "previous_hash_broken"


# ── 11. duplicate prevention ──
def test_duplicate_prevention(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.post_trade_analytics.ledger import read_reports
    eng = PostTradeAnalyticsEngine()
    eng.analyze("LXR:1", _exec(), _NOW, commit=True)
    eng.analyze("LXR:1", _exec(), _NOW, commit=True)   # 동일 → 재추가 안 됨
    assert len(read_reports()) == 1


# ── 12. CLI ──
def test_cli_analyze_and_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.post_trade_analytics.__main__ import main
    assert main(["analyze"]) == 0
    assert main(["verify"]) == 0
    out = capsys.readouterr().out
    assert '"ok": true' in out


def test_cli_summary(capsys):
    from jarvis.post_trade_analytics.__main__ import main
    assert main(["summary"]) == 0
    assert "average_cost_bps" in capsys.readouterr().out


# ── 13. no forbidden imports ──
def test_no_forbidden_imports():
    import importlib
    import inspect
    forbidden = ("jarvis.execution.gateway", "jarvis.execution.arm", "jarvis.live_execution",
                 "jarvis.paper_execution", "jarvis.risk.governor")
    for m in ("models", "benchmarks", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.post_trade_analytics.{m}"))
        for f in forbidden:
            assert f not in src, f"{m} imports {f}"


# ── 14. no execution capability ──
def test_no_execution_capability():
    import importlib
    import inspect
    for m in ("models", "benchmarks", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.post_trade_analytics.{m}"))
        for banned in ("submit_order", "place_order", "cancel_order", "route_order",
                       ".buy(", ".sell(", "gateway", "adapter.submit", "broker_execution",
                       "LiveExecutionEngine"):
            assert banned not in src


# ── 15. no permission escalation ──
def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    assert not any("post_trade" in a for a in ACTION_PERMISSIONS)
    assert not any("tca" in a.lower() for a in ACTION_PERMISSIONS)


# ── 16. no mutation ──
def test_no_mutation(tmp_path, monkeypatch):
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
    monkeypatch.setattr("jarvis.post_trade_analytics.ledger.state_path", sp)
    PostTradeAnalyticsEngine().analyze("LXR:1", _exec(), _NOW, commit=True)
    assert hashlib.sha256(open(pos, "rb").read()).hexdigest() == before   # 페이퍼 불변


# ── 17. report is analytics-only (no trade authorization fields) ──
def test_report_is_analytics_only():
    r = PostTradeAnalyticsEngine().analyze("LXR:1", _exec(), _NOW)
    keys = set(r.to_dict())
    assert keys == {"report_id", "request_id", "timestamp", "report_type", "overall_status",
                    "overall_score", "benchmarks", "metrics", "warnings", "errors",
                    "input_hash", "report_hash", "previous_hash"}
    for f in ("authorized", "submit", "execute", "route", "order_id"):
        assert f not in keys
