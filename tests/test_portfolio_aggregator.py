"""PortfolioAggregator 단위 테스트 — HL/KIS 프로바이더를 monkeypatch로 대체."""
from __future__ import annotations

import pytest

from jarvis.broker_readonly import aggregator
from jarvis.broker_readonly.models import AccountSnapshot, BrokerHealth, BrokerPosition


class _FakeHL:
    def __init__(self, paper=False):
        self.paper = paper

    def account_snapshot(self):
        return AccountSnapshot(cash=100.0, equity=5000.0, buying_power=5000.0, timestamp="t")

    def positions(self):
        return [BrokerPosition(symbol="BTC", quantity=0.1, avg_price=60000.0, market_value=6000.0)]

    def health_check(self):
        return BrokerHealth(connected=True, stale=False, error=None, timestamp="t")

    def orders_history(self):
        return [{"ts": "t2", "venue": "HL", "status": "submitted", "symbol": "BTC",
                  "side": "BUY", "quantity": 0.1}]


class _FakeKISBroken:
    def __init__(self, paper=False):
        self.paper = paper

    def account_snapshot(self):
        raise RuntimeError("KIS unreachable")

    def positions(self):
        raise RuntimeError("KIS unreachable")

    def health_check(self):
        return BrokerHealth(connected=False, stale=False, error="KIS unreachable", timestamp="t")

    def orders_history(self):
        return []


@pytest.fixture(autouse=True)
def _patch_providers(monkeypatch):
    monkeypatch.setattr(aggregator, "HLReadOnlyProvider", _FakeHL)
    monkeypatch.setattr(aggregator, "KISReadOnlyProvider", _FakeKISBroken)
    monkeypatch.setattr(aggregator, "_usdkrw_rate", lambda: 1350.0)


async def test_summary_reports_partial_failure_not_500():
    result = await aggregator.PortfolioAggregator("live").summary()
    accounts = {a["account"]: a for a in result["accounts"]}
    assert accounts["hl"]["connected"] is True
    assert accounts["kis"]["connected"] is False
    assert accounts["kis"]["equity_usd"] == 0.0
    assert accounts["kis"]["positions"] == []


async def test_summary_totals_and_holdings():
    result = await aggregator.PortfolioAggregator("live").summary()
    assert result["total_equity_usd"] == 5000.0
    assert result["holdings"] == [{"account": "hl", "symbol": "BTC", "value_usd": 6000.0}]


def test_trades_merges_and_sorts_by_ts_desc():
    trades = aggregator.PortfolioAggregator("live").trades()
    assert trades == [{"ts": "t2", "venue": "HL", "status": "submitted", "symbol": "BTC",
                        "side": "BUY", "quantity": 0.1}]


def test_trades_filters_by_account():
    assert aggregator.PortfolioAggregator("live").trades(account="kis") == []
