import json

from orderflow.binance_adapter import (
    BinanceOrderflowClient,
    parse_binance_depth_message,
    parse_binance_message,
)
from orderflow.models import OrderBookSnapshot, TradeEvent


class FakeConnection:
    def __init__(self, incoming: list[str]):
        self._incoming = incoming

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for msg in self._incoming:
            yield msg

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeConnect:
    def __init__(self, incoming: list[str]):
        self._incoming = incoming
        self.called_with = None

    def __call__(self, uri: str):
        self.called_with = uri
        return FakeConnection(self._incoming)


def test_parse_binance_message_maps_maker_flag_to_side():
    raw = json.dumps({"e": "aggTrade", "T": 1720000001000, "p": "65000.0", "q": "0.1", "m": True})
    event = parse_binance_message(raw, coin="BTC")
    assert isinstance(event, TradeEvent)
    assert event.symbol == "BTC.HL"
    assert event.ts == 1720000001.0
    assert event.price == 65000.0
    assert event.size == 0.1
    assert event.side == "sell"  # m=True → 매수자가 메이커 → 테이커(공격 방향)는 매도


def test_parse_binance_message_maker_false_is_buy():
    raw = json.dumps({"e": "aggTrade", "T": 1720000001000, "p": "65000.0", "q": "0.1", "m": False})
    event = parse_binance_message(raw, coin="BTC")
    assert event.side == "buy"


def test_parse_binance_message_ignores_other_event_types():
    raw = json.dumps({"e": "depthUpdate", "T": 1720000001000})
    assert parse_binance_message(raw, coin="BTC") is None


def test_parse_binance_message_ignores_malformed_json():
    assert parse_binance_message("not json", coin="BTC") is None


def test_parse_binance_message_ignores_missing_field():
    raw = json.dumps({"e": "aggTrade", "T": 1720000001000, "q": "0.1", "m": False})  # p 없음
    assert parse_binance_message(raw, coin="BTC") is None


async def test_stream_connects_to_aggtrade_url_and_yields_parsed_events():
    raw = json.dumps({"e": "aggTrade", "T": 1720000001000, "p": "65000.0", "q": "0.1", "m": False})
    fake_connect = FakeConnect([raw])
    client = BinanceOrderflowClient(connect_fn=fake_connect)
    events = [e async for e in client.stream("BTC")]
    assert len(events) == 1
    assert events[0].side == "buy"
    assert fake_connect.called_with == "wss://stream.binance.com:9443/ws/btcusdt@aggTrade"


async def test_stream_yields_nothing_for_unmapped_coin():
    fake_connect = FakeConnect([])
    client = BinanceOrderflowClient(connect_fn=fake_connect)
    events = [e async for e in client.stream("DOGE")]
    assert events == []
    assert fake_connect.called_with is None


def test_parse_binance_depth_message_maps_levels():
    raw = json.dumps({
        "lastUpdateId": 1,
        "bids": [["65000.0", "0.5"], ["64999.0", "1.2"]],
        "asks": [["65001.0", "0.3"]],
    })
    event = parse_binance_depth_message(raw, coin="BTC", now_fn=lambda: 1720000001.0)
    assert isinstance(event, OrderBookSnapshot)
    assert event.symbol == "BTC.HL"
    assert event.ts == 1720000001.0
    assert [lvl.price for lvl in event.bids] == [65000.0, 64999.0]
    assert event.asks[0].size == 0.3


def test_parse_binance_depth_message_ignores_malformed_json():
    assert parse_binance_depth_message("not json", coin="BTC") is None


def test_parse_binance_depth_message_ignores_missing_field():
    raw = json.dumps({"lastUpdateId": 1, "bids": [["65000.0", "0.5"]]})  # asks 없음
    assert parse_binance_depth_message(raw, coin="BTC") is None


async def test_stream_depth_connects_to_depth_url_and_yields_parsed_snapshot():
    raw = json.dumps({"lastUpdateId": 1, "bids": [["65000.0", "0.5"]], "asks": [["65001.0", "0.3"]]})
    fake_connect = FakeConnect([raw])
    client = BinanceOrderflowClient(connect_fn=fake_connect)
    events = [e async for e in client.stream_depth("BTC")]
    assert len(events) == 1
    assert isinstance(events[0], OrderBookSnapshot)
    assert fake_connect.called_with == "wss://stream.binance.com:9443/ws/btcusdt@depth20@100ms"


async def test_stream_depth_yields_nothing_for_unmapped_coin():
    fake_connect = FakeConnect([])
    client = BinanceOrderflowClient(connect_fn=fake_connect)
    events = [e async for e in client.stream_depth("DOGE")]
    assert events == []
    assert fake_connect.called_with is None
