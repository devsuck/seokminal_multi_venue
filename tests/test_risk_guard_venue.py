"""RiskConfig.from_env(venue=...) — 통화/거래소별 한도 분리. venue 접미사 우선,
없으면 기존 통화무관 변수로 폴백(하위호환)."""
from __future__ import annotations

from live_engine.risk_guard import RiskConfig


def test_venue_specific_overrides_generic(monkeypatch):
    monkeypatch.setenv("MAX_ORDER_NOTIONAL", "1000000")
    monkeypatch.setenv("MAX_ORDER_NOTIONAL_KR", "500000")
    cfg = RiskConfig.from_env(venue="KR")
    assert cfg.max_order_notional == 500000.0


def test_falls_back_to_generic_when_venue_var_absent(monkeypatch):
    monkeypatch.delenv("MAX_ORDER_QTY_HL", raising=False)
    monkeypatch.setenv("MAX_ORDER_QTY", "777")
    cfg = RiskConfig.from_env(venue="HL")
    assert cfg.max_order_qty == 777


def test_no_venue_keeps_legacy_behavior(monkeypatch):
    monkeypatch.setenv("MAX_ORDER_QTY", "42")
    monkeypatch.delenv("MAX_ORDER_QTY_KR", raising=False)
    cfg = RiskConfig.from_env()
    assert cfg.max_order_qty == 42


def test_kr_and_hl_isolated(monkeypatch):
    monkeypatch.setenv("DAILY_LOSS_LIMIT_KR", "150000")
    monkeypatch.setenv("DAILY_LOSS_LIMIT_HL", "80")
    assert RiskConfig.from_env(venue="KR").daily_loss_limit == 150000.0
    assert RiskConfig.from_env(venue="HL").daily_loss_limit == 80.0
