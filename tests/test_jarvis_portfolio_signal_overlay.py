"""Signal Overlay 테스트 — 전략비중×종목신호 합성, 무수정 원칙, 퓨전 상충 플래그."""
from __future__ import annotations

import os

import pytest

from tests.jarvis_state_isolation import isolate_jarvis_state

from jarvis.fusion.types import FusionSignal, StrategySignal
from jarvis.portfolio.signal_overlay import compute_overlay


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    isolate_jarvis_state(monkeypatch, tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def _fake_registry():
    from jarvis.fusion.providers import PROVIDER_REGISTRY
    saved = dict(PROVIDER_REGISTRY)
    PROVIDER_REGISTRY.clear()
    yield PROVIDER_REGISTRY
    PROVIDER_REGISTRY.clear()
    PROVIDER_REGISTRY.update(saved)


def _provider(sigs):
    return lambda as_of="": list(sigs)


def test_no_adapter_skips_strategy_honestly(_fake_registry):
    rows = compute_overlay({"no_adapter_strategy": 0.5}, "2026-07-29")
    assert rows == []


def test_single_instrument_full_weight(_fake_registry):
    _fake_registry["s1"] = _provider([StrategySignal("s1", "AAPL", 1, 0.8)])
    rows = compute_overlay({"s1": 0.4}, "2026-07-29")
    assert len(rows) == 1
    r = rows[0]
    assert r["instrument"] == "AAPL"
    assert r["direction"] == 1
    assert r["intra_strategy_weight"] == 1.0
    assert r["instrument_target_weight"] == pytest.approx(0.4)
    assert r["fusion_direction"] is None
    assert r["conflict"] is False


def test_multi_instrument_split_proportional(_fake_registry):
    _fake_registry["s2"] = _provider([
        StrategySignal("s2", "AAPL", 1, 0.6),
        StrategySignal("s2", "MSFT", -1, 0.2),
    ])
    rows = compute_overlay({"s2": 1.0}, "2026-07-29")
    by_ins = {r["instrument"]: r for r in rows}
    assert by_ins["AAPL"]["intra_strategy_weight"] == pytest.approx(0.75)
    assert by_ins["MSFT"]["intra_strategy_weight"] == pytest.approx(0.25)
    assert by_ins["MSFT"]["direction"] == -1
    assert by_ins["MSFT"]["instrument_target_weight"] == pytest.approx(-0.25)


def test_conflict_flagged_against_fusion_ledger(_fake_registry):
    from jarvis.fusion.ledger import write_signals
    _fake_registry["s3"] = _provider([StrategySignal("s3", "TSLA", 1, 1.0)])
    fused = [FusionSignal(instrument="TSLA", direction=-1, confidence=0.7, score=-0.5,
                          scheme="v1_risk_adjusted", as_of="2026-07-29", n_strategies=3)]
    write_signals(fused, "v1_risk_adjusted")
    rows = compute_overlay({"s3": 0.3}, "2026-07-29")
    assert rows[0]["fusion_direction"] == -1
    assert rows[0]["fusion_confidence"] == 0.7
    assert rows[0]["conflict"] is True


def test_original_weights_untouched(_fake_registry):
    """오버레이는 입력 strategy_weights dict를 변형하지 않음(제안 전용 원칙)."""
    _fake_registry["s1"] = _provider([StrategySignal("s1", "AAPL", 1, 1.0)])
    weights = {"s1": 0.5}
    snapshot = dict(weights)
    compute_overlay(weights, "2026-07-29")
    assert weights == snapshot
