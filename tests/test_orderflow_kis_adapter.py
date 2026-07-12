import json

from orderflow.kis_adapter import (
    DEPTH_TR_ID,
    TRADE_TR_ID,
    KISFuturesOrderflowClient,
    parse_kis_futures_depth_message,
    parse_kis_futures_trade_message,
)
from orderflow.models import OrderBookSnapshot, TradeEvent

TRADE_FIELDS = [""] * 25
TRADE_FIELDS[10] = "18500.25"  # last_price
TRADE_FIELDS[11] = "2"  # last_qntt
TRADE_RAW = "0|" + TRADE_TR_ID + "|001|" + "^".join(TRADE_FIELDS)

DEPTH_FIELDS = ["0"] * 35
DEPTH_FIELDS[0:4] = ["NQ", "20260712", "090000", "18490.00"]
DEPTH_FIELDS[4:10] = ["3", "1", "18499.75", "2", "1", "18500.00"]  # level 1
DEPTH_FIELDS[10:16] = ["5", "2", "18499.50", "4", "2", "18500.25"]  # level 2
DEPTH_RAW = "0|" + DEPTH_TR_ID + "|001|" + "^".join(DEPTH_FIELDS)


class FakeConnection:
    def __init__(self, incoming: list[str]):
        self._incoming = incoming
        self.sent: list[str] = []

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for msg in self._incoming:
            yield msg

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeConnect:
    def __init__(self, incoming: list[str]):
        self._incoming = incoming
        self.connection: FakeConnection | None = None
        self.called_with = None

    def __call__(self, uri: str):
        self.called_with = uri
        self.connection = FakeConnection(self._incoming)
        return self.connection


def test_parse_kis_futures_trade_message_uses_bid_ask_to_classify_side():
    event = parse_kis_futures_trade_message(
        TRADE_RAW, symbol="NQ", bid=18500.00, ask=18500.50, now_fn=lambda: 1720000000.0
    )
    assert isinstance(event, TradeEvent)
    assert event.symbol == "NQ"
    assert event.price == 18500.25
    assert event.size == 2.0
    assert event.side == "buy"  # mid=18500.25, price>=mid → buy
    assert event.ts == 1720000000.0


def test_parse_kis_futures_trade_message_wrong_tr_id_returns_none():
    raw = "0|SOMETHING_ELSE|001|" + "^".join(TRADE_FIELDS)
    assert parse_kis_futures_trade_message(raw, symbol="NQ", bid=1.0, ask=2.0) is None


def test_parse_kis_futures_trade_message_short_field_block_returns_none():
    raw = "0|" + TRADE_TR_ID + "|001|too^short"
    assert parse_kis_futures_trade_message(raw, symbol="NQ", bid=1.0, ask=2.0) is None


def test_parse_kis_futures_depth_message_maps_five_levels():
    snapshot = parse_kis_futures_depth_message(DEPTH_RAW, symbol="NQ", now_fn=lambda: 1720000000.0)
    assert isinstance(snapshot, OrderBookSnapshot)
    assert snapshot.symbol == "NQ"
    assert snapshot.ts == 1720000000.0
    assert snapshot.bids[0].price == 18499.75
    assert snapshot.bids[0].size == 3.0
    assert snapshot.asks[0].price == 18500.00
    assert snapshot.asks[0].size == 2.0
    assert snapshot.bids[1].price == 18499.50
    assert snapshot.asks[1].price == 18500.25


def test_parse_kis_futures_depth_message_skips_zero_price_levels():
    fields = list(DEPTH_FIELDS)
    fields[16:22] = ["0", "0", "0", "0", "0", "0"]  # level 3 empty
    raw = "0|" + DEPTH_TR_ID + "|001|" + "^".join(fields)
    snapshot = parse_kis_futures_depth_message(raw, symbol="NQ")
    assert len(snapshot.bids) == 2
    assert len(snapshot.asks) == 2


def test_parse_kis_futures_depth_message_wrong_tr_id_returns_none():
    raw = "0|SOMETHING_ELSE|001|" + "^".join(DEPTH_FIELDS)
    assert parse_kis_futures_depth_message(raw, symbol="NQ") is None


async def test_stream_subscribes_both_trs_and_yields_depth_then_trade():
    fake_connect = FakeConnect([DEPTH_RAW, TRADE_RAW])
    client = KISFuturesOrderflowClient(approval_key="fake-key", connect_fn=fake_connect)
    events = [e async for e in client.stream("NQ")]

    assert fake_connect.called_with == "ws://ops.koreainvestment.com:21000"
    sent = [json.loads(m) for m in fake_connect.connection.sent]
    assert sent[0]["body"]["input"]["tr_id"] == TRADE_TR_ID
    assert sent[1]["body"]["input"]["tr_id"] == DEPTH_TR_ID
    assert sent[0]["body"]["input"]["tr_key"] == "NQ"
    assert sent[0]["header"]["approval_key"] == "fake-key"

    assert isinstance(events[0], OrderBookSnapshot)
    assert isinstance(events[1], TradeEvent)


async def test_stream_skips_trade_before_first_depth_snapshot():
    fake_connect = FakeConnect([TRADE_RAW])
    client = KISFuturesOrderflowClient(approval_key="fake-key", connect_fn=fake_connect)
    events = [e async for e in client.stream("NQ")]
    assert events == []


async def test_stream_echoes_pingpong_control_frame():
    pingpong = json.dumps({"header": {"tr_id": "PINGPONG"}})
    fake_connect = FakeConnect([pingpong])
    client = KISFuturesOrderflowClient(approval_key="fake-key", connect_fn=fake_connect)
    events = [e async for e in client.stream("NQ")]
    assert events == []
    assert pingpong in fake_connect.connection.sent


def test_client_raises_without_credentials_or_approval_key(monkeypatch):
    monkeypatch.delenv("KIS_APP_KEY", raising=False)
    monkeypatch.delenv("KIS_APP_SECRET", raising=False)
    client = KISFuturesOrderflowClient(connect_fn=FakeConnect([]))
    try:
        client._resolve_approval_key()
        assert False, "expected ValueError"
    except ValueError:
        pass
