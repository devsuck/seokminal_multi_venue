import json

from orderflow.binance_adapter import (
    BinanceOrderflowClient,
    apply_binance_diff,
    parse_binance_diff_message,
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


def test_apply_binance_diff_updates_and_removes_zero_size():
    book = {65000.0: 0.5, 64999.0: 1.2}
    apply_binance_diff(book, [["64999.0", "0"], ["64998.0", "2.0"]])
    assert book == {65000.0: 0.5, 64998.0: 2.0}


def test_parse_binance_diff_message_maps_fields():
    raw = json.dumps({"e": "depthUpdate", "U": 101, "u": 105, "b": [["65000.0", "0.5"]], "a": [["65001.0", "0.3"]]})
    diff = parse_binance_diff_message(raw)
    assert diff == {"U": 101, "u": 105, "b": [["65000.0", "0.5"]], "a": [["65001.0", "0.3"]]}


def test_parse_binance_diff_message_ignores_other_event_types():
    raw = json.dumps({"e": "aggTrade"})
    assert parse_binance_diff_message(raw) is None


def test_parse_binance_diff_message_ignores_malformed_json():
    assert parse_binance_diff_message("not json") is None


def test_parse_binance_diff_message_ignores_missing_field():
    raw = json.dumps({"e": "depthUpdate", "U": 101, "b": [], "a": []})  # u 없음
    assert parse_binance_diff_message(raw) is None


async def test_stream_depth_fetches_snapshot_then_merges_diff_and_yields_snapshot():
    diff_raw = json.dumps({"e": "depthUpdate", "U": 101, "u": 101, "b": [["64998.0", "2.0"]], "a": []})
    fake_connect = FakeConnect([diff_raw])

    async def fake_fetch_snapshot(pair: str) -> dict:
        assert pair == "btcusdt"
        return {"lastUpdateId": 100, "bids": [["65000.0", "0.5"]], "asks": [["65001.0", "0.3"]]}

    client = BinanceOrderflowClient(connect_fn=fake_connect, fetch_snapshot_fn=fake_fetch_snapshot)
    events = [e async for e in client.stream_depth("BTC")]
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, OrderBookSnapshot)
    assert [lvl.price for lvl in event.bids] == [65000.0, 64998.0]
    assert event.asks[0].price == 65001.0
    assert fake_connect.called_with == "wss://stream.binance.com:9443/ws/btcusdt@depth@100ms"


async def test_stream_depth_discards_diffs_not_newer_than_snapshot():
    old_diff = json.dumps({"e": "depthUpdate", "U": 90, "u": 100, "b": [["64000.0", "1.0"]], "a": []})
    new_diff = json.dumps({"e": "depthUpdate", "U": 101, "u": 101, "b": [["64998.0", "2.0"]], "a": []})
    fake_connect = FakeConnect([old_diff, new_diff])

    async def fake_fetch_snapshot(pair: str) -> dict:
        return {"lastUpdateId": 100, "bids": [["65000.0", "0.5"]], "asks": [["65001.0", "0.3"]]}

    client = BinanceOrderflowClient(connect_fn=fake_connect, fetch_snapshot_fn=fake_fetch_snapshot)
    events = [e async for e in client.stream_depth("BTC")]
    assert len(events) == 1  # old_diff(u=100<=lastUpdateId=100)는 폐기, new_diff만 반영
    bid_prices = [lvl.price for lvl in events[0].bids]
    assert 64000.0 not in bid_prices
    assert 64998.0 in bid_prices


async def test_stream_depth_hard_resyncs_on_mid_stream_gap():
    # 1) synced 상태 진입, 2) U가 prev_u+1을 건너뛰는 갭 diff(폐기+리싱크 트리거),
    # 3) 리싱크 후 새 스냅샷 기준으로 이어지는 diff — 유령 레벨 없이 새 스냅샷 상태만 반영돼야 함.
    diff1 = json.dumps({"e": "depthUpdate", "U": 101, "u": 101, "b": [["64998.0", "2.0"]], "a": []})
    gap_diff = json.dumps({"e": "depthUpdate", "U": 105, "u": 106, "b": [["64000.0", "9.0"]], "a": []})
    diff_after_resync = json.dumps({"e": "depthUpdate", "U": 201, "u": 201, "b": [["70000.0", "3.0"]], "a": []})
    fake_connect = FakeConnect([diff1, gap_diff, diff_after_resync])

    snapshots = [
        {"lastUpdateId": 100, "bids": [["65000.0", "0.5"]], "asks": [["65001.0", "0.3"]]},
        {"lastUpdateId": 200, "bids": [["70001.0", "1.0"]], "asks": [["70002.0", "0.2"]]},
    ]
    calls = {"n": 0}

    async def fake_fetch_snapshot(pair: str) -> dict:
        snap = snapshots[calls["n"]]
        calls["n"] += 1
        return snap

    client = BinanceOrderflowClient(connect_fn=fake_connect, fetch_snapshot_fn=fake_fetch_snapshot)
    # throttle_sec=0: 이 테스트는 유효 diff마다 매번 yield되는지 검증하는 게 목적이라
    # 실시간 스로틀(기본 0.2초)을 끔 — 안 끄면 테스트가 순식간에 돌아서 두 번째 emit이
    # 스로틀에 걸려 사라짐.
    events = [e async for e in client.stream_depth("BTC", throttle_sec=0.0)]

    assert calls["n"] == 2  # 최초 스냅샷 + 갭으로 인한 리싱크 1회
    assert len(events) == 2  # gap_diff는 리싱크 트리거로 폐기, 나머지 2개만 yield
    final_bids = [lvl.price for lvl in events[-1].bids]
    assert 64000.0 not in final_bids  # 갭 diff 내용은 반영되지 않음
    assert 65000.0 not in final_bids  # 리싱크 전 스냅샷의 유령 레벨도 제거됨
    assert 70001.0 in final_bids and 70000.0 in final_bids  # 새 스냅샷 + 리싱크 후 diff


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
