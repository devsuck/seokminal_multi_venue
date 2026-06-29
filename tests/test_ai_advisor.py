import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from ai_strategy.advisor import recommend_strategy
from api_server.main import app

client = TestClient(app)


def _fake_bars(n=50):
    bar = MagicMock()
    bar.close = 100.0
    bar.ts_event = 1_704_067_200_000_000_000  # 2024-01-01 UTC in nanoseconds
    return [bar] * n


def _mock_anthropic_response(strategy="macd", params=None, reasoning="Test reasoning."):
    if params is None:
        params = {"fast": 12, "slow": 26, "signal_period": 9}
    import json
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_content = MagicMock()
    mock_content.text = json.dumps({"strategy": strategy, "params": params, "reasoning": reasoning})
    mock_message.content = [mock_content]
    mock_client.messages.create.return_value = mock_message
    return mock_client


def test_recommend_strategy_returns_required_keys():
    bars = _fake_bars(50)
    with patch("ai_strategy.advisor.anthropic.Anthropic", return_value=_mock_anthropic_response()):
        result = recommend_strategy(bars, "AAPL.NASDAQ")
    assert "strategy" in result
    assert "params" in result
    assert "reasoning" in result
    assert result["strategy"] in {"ema_cross", "macd", "rsi"}


def test_recommend_strategy_raises_on_empty_bars():
    with pytest.raises(ValueError, match="no bars"):
        recommend_strategy([], "AAPL.NASDAQ")


def test_ai_recommend_endpoint_returns_200():
    with (
        patch("api_server.main.ParquetDataCatalog") as mock_cat,
        patch("api_server.main.bar_type_for") as mock_bt,
        patch("api_server.main.InstrumentId") as mock_iid,
        patch("api_server.main.recommend_strategy") as mock_rec,
    ):
        mock_cat.return_value.bars.return_value = _fake_bars(50)
        mock_bt.return_value = MagicMock(__str__=lambda s: "bar_type")
        mock_iid.from_str.return_value = MagicMock()
        mock_rec.return_value = {
            "strategy": "macd",
            "params": {"fast": 12, "slow": 26, "signal_period": 9},
            "reasoning": "MACD suits this trending instrument.",
        }

        r = client.get(
            "/ai/strategy-recommend"
            "?instrument_id=AAPL.NASDAQ&start=2024-01-01&end=2024-12-31"
        )

    assert r.status_code == 200
    data = r.json()
    assert data["strategy"] == "macd"
    assert "fast" in data["params"]
    assert data["instrument_id"] == "AAPL.NASDAQ"
    assert len(data["reasoning"]) > 0


def test_ai_recommend_endpoint_returns_400_for_missing_bars():
    with (
        patch("api_server.main.ParquetDataCatalog") as mock_cat,
        patch("api_server.main.bar_type_for") as mock_bt,
        patch("api_server.main.InstrumentId") as mock_iid,
    ):
        mock_cat.return_value.bars.return_value = []
        mock_bt.return_value = MagicMock(__str__=lambda s: "bar_type")
        mock_iid.from_str.return_value = MagicMock()

        r = client.get(
            "/ai/strategy-recommend"
            "?instrument_id=UNKNOWN.XX&start=2024-01-01&end=2024-12-31"
        )

    assert r.status_code == 400
