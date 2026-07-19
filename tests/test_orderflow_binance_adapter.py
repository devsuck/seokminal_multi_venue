import json

from orderflow.binance_adapter import (
    BinanceOrderflowClient,
    parse_binance_depth_message,
    parse_binance_liquidation_message,
    parse_binance_message,
)
from orderflow.models import LiquidationEvent, OrderBookSnapshot, TradeEvent


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


def _force_order_raw(side: str, ap: str | None = "9910", p: str = "9900") -> str:
    o = {"s": "BTCUSDT", "S": side, "q": "0.014", "p": p, "T": 1568014460893}
    if ap is not None:
        o["ap"] = ap
    return json.dumps({"e": "forceOrder", "o": o})


def test_parse_binance_liquidation_message_sell_is_long_liquidation():
    event = parse_binance_liquidation_message(_force_order_raw("SELL"), coin="BTC")
    assert isinstance(event, LiquidationEvent)
    assert event.symbol == "BTC.HL"
    assert event.ts == 1568014460.893
    assert event.price == 9910.0
    assert event.size == 0.014
    assert event.side == "long"  # 강제매도 = 롱 청산


def test_parse_binance_liquidation_message_buy_is_short_liquidation():
    event = parse_binance_liquidation_message(_force_order_raw("BUY"), coin="BTC")
    assert event.side == "short"


def test_parse_binance_liquidation_message_falls_back_to_p_when_ap_missing():
    event = parse_binance_liquidation_message(_force_order_raw("SELL", ap=None, p="9900"), coin="BTC")
    assert event.price == 9900.0


def test_parse_binance_liquidation_message_ignores_other_event_types():
    raw = json.dumps({"e": "aggTrade", "o": {}})
    assert parse_binance_liquidation_message(raw, coin="BTC") is None


def test_parse_binance_liquidation_message_ignores_malformed_json():
    assert parse_binance_liquidation_message("not json", coin="BTC") is None


def test_parse_binance_liquidation_message_ignores_missing_field():
    raw = json.dumps({"e": "forceOrder", "o": {"s": "BTCUSDT", "S": "SELL", "q": "0.014", "T": 1568014460893}})  # p/ap 없음
    assert parse_binance_liquidation_message(raw, coin="BTC") is None


async def test_stream_liquidations_connects_to_force_order_url_and_yields_parsed_events():
    fake_connect = FakeConnect([_force_order_raw("SELL")])
    client = BinanceOrderflowClient(connect_fn=fake_connect)
    events = [e async for e in client.stream_liquidations("BTC")]
    assert len(events) == 1
    assert events[0].side == "long"
    assert fake_connect.called_with == "wss://fstream.binance.com/ws/btcusdt@forceOrder"


async def test_stream_liquidations_yields_nothing_for_unmapped_coin():
    fake_connect = FakeConnect([])
    client = BinanceOrderflowClient(connect_fn=fake_connect)
    events = [e async for e in client.stream_liquidations("DOGE")]
    assert events == []
    assert fake_connect.called_with is None
