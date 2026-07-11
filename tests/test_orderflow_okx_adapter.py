import json

from orderflow.models import TradeEvent
from orderflow.okx_adapter import OkxOrderflowClient, parse_okx_message


class FakeConnection:
    def __init__(self, incoming: list[str]):
        self._incoming = incoming
        self.sent: list[str] = []

    async def send(self, message: str) -> None:
        self.sent.append(message)

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
        self.connection: FakeConnection | None = None

    def __call__(self, uri: str):
        self.called_with = uri
        self.connection = FakeConnection(self._incoming)
        return self.connection


def test_parse_okx_message_trades():
    raw = json.dumps({
        "arg": {"channel": "trades", "instId": "BTC-USDT"},
        "data": [
            {"instId": "BTC-USDT", "px": "65000.0", "sz": "0.1", "side": "buy", "ts": "1720000001000"},
            {"instId": "BTC-USDT", "px": "64990.0", "sz": "0.2", "side": "sell", "ts": "1720000002000"},
        ],
    })
    events = parse_okx_message(raw, coin="BTC")
    assert len(events) == 2
    assert all(isinstance(e, TradeEvent) for e in events)
    assert events[0].symbol == "BTC.HL"
    assert events[0].ts == 1720000001.0
    assert events[0].side == "buy"
    assert events[1].side == "sell"


def test_parse_okx_message_ignores_missing_data():
    raw = json.dumps({"event": "subscribe", "arg": {"channel": "trades", "instId": "BTC-USDT"}})
    assert parse_okx_message(raw, coin="BTC") == []


def test_parse_okx_message_ignores_malformed_json():
    assert parse_okx_message("not json", coin="BTC") == []


def test_parse_okx_message_skips_invalid_side():
    raw = json.dumps({"data": [{"px": "65000.0", "sz": "0.1", "side": "unknown", "ts": "1720000001000"}]})
    assert parse_okx_message(raw, coin="BTC") == []


def test_parse_okx_message_skips_missing_field():
    raw = json.dumps({"data": [{"sz": "0.1", "side": "buy", "ts": "1720000001000"}]})  # px 없음
    assert parse_okx_message(raw, coin="BTC") == []


async def test_stream_subscribes_trades_channel_and_yields_parsed_events():
    raw = json.dumps({"data": [{"px": "65000.0", "sz": "0.1", "side": "buy", "ts": "1720000001000"}]})
    fake_connect = FakeConnect([raw])
    client = OkxOrderflowClient(connect_fn=fake_connect)
    events = [e async for e in client.stream("BTC")]
    assert len(events) == 1
    assert events[0].side == "buy"
    assert fake_connect.called_with == "wss://ws.okx.com:8443/ws/v5/public"


async def test_stream_sends_subscribe_message_with_inst_id():
    fake_connect = FakeConnect([])
    client = OkxOrderflowClient(connect_fn=fake_connect)
    _ = [e async for e in client.stream("BTC")]
    sent = json.loads(fake_connect.connection.sent[0])
    assert sent == {"op": "subscribe", "args": [{"channel": "trades", "instId": "BTC-USDT"}]}


async def test_stream_yields_nothing_for_unmapped_coin():
    fake_connect = FakeConnect([])
    client = OkxOrderflowClient(connect_fn=fake_connect)
    events = [e async for e in client.stream("DOGE")]
    assert events == []
    assert fake_connect.called_with is None
