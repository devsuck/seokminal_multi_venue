"""Backtest Auto-Ingestion Adapter(P54) 테스트 — 매핑·자동수집·멱등·엔드투엔드·안전.

핵심 요구(문서 §Tests):
  · 가짜 백테스트 → 원장 갱신
  · 실패 백테스트 → failure intelligence 자동 생성
  · 성공 백테스트 → success memory 자동 생성
  · 두 번 수집 → 중복 없음
  · recall 이 찾아낸다(agent→backtest→stored→memory→recall)

모든 관련 원장(ring_/expt_/rmi_/research_assistant)을 같은 tmp _state 로 격리(P53 패턴 재사용).
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

from jarvis.research_ingestion import ledger
from jarvis.research_ingestion import models as M
from jarvis.research_ingestion.backtest_adapter import (
    adapt,
    ingest_backtest,
    ingest_backtests,
)
from jarvis.research_ingestion.engine import ResearchIngestionEngine

NOW = "2026-01-01T00:00:00Z"
SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """수집·실험·메모리·어시스턴트 원장을 모두 같은 tmp _state 로 격리."""
    state = tmp_path / "_state"
    state.mkdir()
    sp = lambda name: str(state / name)  # noqa: E731
    from jarvis.experiment_tracking import ledger as el
    from jarvis.research_memory_intelligence import ledger as ml
    from jarvis.research_assistant import ledger as al
    monkeypatch.setattr(ledger, "state_path", sp)
    monkeypatch.setattr(el, "state_path", sp)
    monkeypatch.setattr(ml, "state_path", sp)
    monkeypatch.setattr(al, "state_path", sp)
    return ResearchIngestionEngine()


# ── 완료-시점 백테스트 출력(실제 backtest_runner 형태) ──
def _flat_bt(**over):
    """run_backtest / run_simple_backtest 반환 형태(평면)."""
    bt = {
        "instrument_id": "AAPL.NASDAQ", "bar_count": 500,
        "sharpe_ratio": 0.9, "max_drawdown": -0.18, "total_pnl": 1234.5,
        "total_pnl_pct": 0.12, "win_rate": 0.55, "profit_loss_ratio": 1.4,
        "avg_win": 30.0, "avg_loss": -20.0, "volatility": 0.14,
        "sortino_ratio": 1.1, "num_trades": 42, "trades": [],
        "source": "backtest_runner",
    }
    bt.update(over)
    return bt


def _agent_bt(**over):
    """jarvis.agents.backtest.run 반환 형태(중첩 metrics + provenance)."""
    bt = {
        "strategy_id": "momentum_v3",
        "metrics": {"net": 0.11, "ann_return": 0.11, "sharpe": 0.8,
                    "wf_first": 0.7, "wf_second": 0.6, "random_percentile": 0.2,
                    "powered": True},
        "provenance": {"data_version": "eod_2024", "code_version": "v3",
                       "config_hash": "abc123", "random_seed": 42,
                       "timestamp": NOW},
        "immutable": True,
    }
    bt.update(over)
    return bt


# 검증 하네스(research/validation)가 산출하는 나머지 검증지표 보강
_VALIDATION = {"walk_forward": 0.8, "out_of_sample": 0.7, "cost_impact": 0.1,
               "parameter_stability": 0.8, "random_baseline": 0.2}


def _ctx(**over):
    ctx = {
        "strategy_name": "momentum", "strategy_version": "v1",
        "hypothesis": "momentum works in stable regimes",
        "universe": "KOSPI200", "period": {"start": "2020-01", "end": "2023-12"},
        "features": ["ret_12m", "vol_20d"], "entry_rules": "top decile",
        "exit_rules": "monthly rebalance", "risk_rules": "10% per name",
        "metrics": dict(_VALIDATION), "source": "backtest_runner",
    }
    ctx.update(over)
    return ctx


# ── 매핑(adapt) — 순수 변환 ──
def test_adapt_flat_maps_core_metrics():
    s = adapt(_flat_bt(), context=_ctx())
    assert s["strategy_name"] == "momentum"
    assert s["metrics"]["sharpe"] == 0.9           # sharpe_ratio → sharpe
    assert s["metrics"]["return"] == 0.12          # total_pnl_pct → return
    assert s["metrics"]["max_drawdown"] == -0.18
    assert s["metrics"]["volatility"] == 0.14


def test_adapt_context_fills_validation_metrics():
    s = adapt(_flat_bt(), context=_ctx())
    for k in ("walk_forward", "out_of_sample", "cost_impact",
              "parameter_stability", "random_baseline"):
        assert s["metrics"][k] == _VALIDATION[k]


def test_adapt_original_metric_not_overwritten_by_context():
    # 원본 백테스트 sharpe=0.9 는 context.metrics 로 덮이지 않는다
    s = adapt(_flat_bt(), context=_ctx(metrics={**_VALIDATION, "sharpe": 0.1}))
    assert s["metrics"]["sharpe"] == 0.9


def test_adapt_nested_agent_shape():
    s = adapt(_agent_bt(), context={"universe": "KR", "metrics": _VALIDATION})
    assert s["strategy_name"] == "momentum_v3"     # strategy_id fallback
    assert s["strategy_version"] == "v3"           # provenance.code_version
    assert s["metrics"]["sharpe"] == 0.8
    assert s["metrics"]["return"] == 0.11          # ann_return → return
    assert s["metrics"]["walk_forward"] == 0.7     # wf_first → walk_forward
    assert s["metrics"]["out_of_sample"] == 0.6    # wf_second → out_of_sample
    assert s["provenance"]["config_hash"] == "abc123"


def test_adapt_no_context_defaults():
    s = adapt(_flat_bt())
    assert s["strategy_name"] == "AAPL.NASDAQ"     # instrument_id fallback
    assert s["source"] == "backtest_runner"
    assert s["metrics"]["sharpe"] == 0.9


def test_adapt_pure_no_side_effects(env):
    adapt(_flat_bt(), context=_ctx())
    assert ledger.read_ingestions() == []          # 매핑만 — 기록 없음


# ── 자동수집 훅 — 가짜 백테스트 → 원장 갱신 ──
def test_ingest_backtest_updates_ledger(env):
    r = ingest_backtest(_flat_bt(), context=_ctx(), engine=env, now=NOW, commit=True)
    assert r.experiment_id
    assert len(ledger.read_ingestions()) == 1
    from jarvis.experiment_tracking import ledger as el
    assert len(el.read_experiments()) == 1
    assert len(el.read_runs()) == 1


# ── 성공 백테스트 → success memory 자동 생성 ──
def test_success_backtest_creates_success_memory(env):
    r = ingest_backtest(_flat_bt(), context=_ctx(), engine=env, now=NOW, commit=True)
    assert r.outcome == M.OUT_SUCCESS
    assert r.memory_written == "success"
    from jarvis.research_memory_intelligence import ledger as ml
    assert len(ml.read_successes()) == 1


# ── 실패 백테스트 → failure intelligence 자동 생성 ──
def test_failed_backtest_creates_failure_intel(env):
    bad = _flat_bt(sharpe_ratio=-0.2, max_drawdown=-0.4)
    ctx = _ctx(metrics={**_VALIDATION, "sharpe": None, "out_of_sample": -0.5,
                        "cost_impact": 0.4})
    r = ingest_backtest(bad, context=ctx, engine=env, now=NOW, commit=True)
    assert r.outcome == M.OUT_FAILURE
    assert r.failure_category == "COST_SENSITIVITY"
    assert r.memory_written == "failure"
    from jarvis.research_memory_intelligence import ledger as ml
    assert len(ml.read_failures()) == 1
    assert len(ml.read_lessons()) == 1
    # failure intelligence 가 실제로 채워진다
    from jarvis.research_assistant.engine import ResearchAssistantEngine
    fi = ResearchAssistantEngine().failure_intelligence()
    assert fi.total_failures >= 1


# ── 두 번 수집 → 중복 없음(멱등) ──
def test_ingest_twice_no_duplicate(env):
    a = ingest_backtest(_flat_bt(), context=_ctx(), engine=env, now=NOW, commit=True)
    b = ingest_backtest(_flat_bt(), context=_ctx(), engine=env, now=NOW, commit=True)
    assert a.deduplicated is False
    assert b.deduplicated is True
    assert len(ledger.read_ingestions()) == 1
    from jarvis.experiment_tracking import ledger as el
    assert len(el.read_experiments()) == 1


# ── recall 이 찾아낸다(agent→backtest→stored→memory→recall) ──
def test_recall_finds_ingested_backtest(env):
    ingest_backtest(_agent_bt(), context=_ctx(strategy_name="momentum"),
                    engine=env, now=NOW, commit=True)
    from jarvis.research_assistant.engine import ResearchAssistantEngine
    r = ResearchAssistantEngine().recall("momentum")
    assert r.tried_before is True


# ── 검증 미보강 시 INCOMPLETE(누락을 숨기지 않음) ──
def test_missing_validation_yields_incomplete(env):
    # context.metrics 없음 → 필수 검증지표 5개 누락
    r = ingest_backtest(_flat_bt(), context={"strategy_name": "raw_only"},
                        engine=env, now=NOW, commit=True)
    assert r.validation_complete is False
    assert r.outcome == M.OUT_INCOMPLETE
    assert set(r.missing_validations) >= {"walk_forward", "cost_impact"}


# ── 드라이런(commit=False) — 판정만, 기록 없음 ──
def test_ingest_backtest_dry_run(env):
    r = ingest_backtest(_flat_bt(), context=_ctx(), engine=env, now=NOW, commit=False)
    assert r.outcome == M.OUT_SUCCESS
    assert r.experiment_id == ""
    assert ledger.read_ingestions() == []


# ── 일괄 백필 ──
def test_ingest_backtests_batch(env):
    outs = [_flat_bt(instrument_id="A"), _flat_bt(instrument_id="B")]
    ctxs = [_ctx(strategy_name="a"), _ctx(strategy_name="b")]
    rs = ingest_backtests(outs, contexts=ctxs, engine=env, now=NOW, commit=True)
    assert len(rs) == 2
    assert len(ledger.read_ingestions()) == 2


def test_ingest_backtest_default_engine_dry_run(env):
    # engine 미주입 시 내부 생성 — 격리된 원장 사용(드라이런이라 기록 없음)
    r = ingest_backtest(_flat_bt(), context=_ctx(), now=NOW, commit=False)
    assert r.outcome == M.OUT_SUCCESS


# ── 자문 전용(결정·집행 아님) ──
def test_result_is_advisory(env):
    r = ingest_backtest(_flat_bt(), context=_ctx(), engine=env, now=NOW, commit=True)
    assert r.is_advisory is True
    assert r.is_decision is False


# ── 안전 스캔 ──
def test_no_forbidden_imports():
    path = str(SRC / "backtest_adapter.py")
    tree = ast.parse(open(path).read())
    bad = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
           "jarvis.live_trading", "jarvis.portfolio_execution")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(b) for b in bad), node.module


def test_no_dangerous_defs():
    path = str(SRC / "backtest_adapter.py")
    tree = ast.parse(open(path).read())
    bad = ("execute", "trade", "deploy", "allocate", "approve", "place_order")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


def test_no_model_id_leak():
    assert MODEL_LEAK_TOKEN not in open(SRC / "backtest_adapter.py").read().lower()


# ── CLI: ingest-backtest ──
def test_cli_ingest_backtest(tmp_path, monkeypatch, capsys):
    state = tmp_path / "_state"
    state.mkdir()
    sp = lambda name: str(state / name)  # noqa: E731
    from jarvis.experiment_tracking import ledger as el
    from jarvis.research_memory_intelligence import ledger as ml
    monkeypatch.setattr(ledger, "state_path", sp)
    monkeypatch.setattr(el, "state_path", sp)
    monkeypatch.setattr(ml, "state_path", sp)
    rawf = tmp_path / "raw.json"
    rawf.write_text(json.dumps(_flat_bt()), encoding="utf-8")
    ctxf = tmp_path / "ctx.json"
    ctxf.write_text(json.dumps(_ctx()), encoding="utf-8")
    from jarvis.research_ingestion import __main__ as cli
    rc = cli.main(["ingest-backtest", "--file", str(rawf),
                   "--context", str(ctxf), "--commit"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "mapped_schema" in out
    assert "SUCCESS" in out
    assert len(ledger.read_ingestions()) == 1


def test_cli_ingest_backtest_dry_run_no_context(tmp_path, monkeypatch, capsys):
    state = tmp_path / "_state"
    state.mkdir()
    sp = lambda name: str(state / name)  # noqa: E731
    from jarvis.experiment_tracking import ledger as el
    from jarvis.research_memory_intelligence import ledger as ml
    monkeypatch.setattr(ledger, "state_path", sp)
    monkeypatch.setattr(el, "state_path", sp)
    monkeypatch.setattr(ml, "state_path", sp)
    rawf = tmp_path / "raw.json"
    rawf.write_text(json.dumps(_flat_bt()), encoding="utf-8")
    from jarvis.research_ingestion import __main__ as cli
    rc = cli.main(["ingest-backtest", "--file", str(rawf)])
    assert rc == 0
    assert ledger.read_ingestions() == []          # 드라이런 — 기록 없음
