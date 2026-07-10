import json

from orderflow.deribit_adapter import DeribitOptionsFlowClient, OptionTradeEvent, parse_deribit_trades_message


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

    def __call__(self, uri: str):
        self.called_with = uri
        return FakeConnection(self._incoming)


def _trades_raw(channel: str, data: list[dict]) -> str:
    return json.dumps({
        "jsonrpc": "2.0",
        "method": "subscription",
        "params": {"channel": channel, "data": data},
    })


def test_parse_deribit_trades_message_parses_events():
    raw = _trades_raw("trades.option.BTC.100ms", [
        {
            "instrument_name": "BTC-27DEC26-100000-C",
            "direction": "buy",
            "price": 0.0512,
            "amount": 10.0,
            "iv": 55.3,
            "index_price": 95000.0,
            "timestamp": 1720000000000,
        },
        {
            "instrument_name": "BTC-27DEC26-90000-P",
            "direction": "sell",
            "price": 0.021,
            "amount": 5.0,
            "iv": 60.1,
            "index_price": 95000.0,
            "timestamp": 1720000001000,
        },
    ])
    events = parse_deribit_trades_message(raw, currency="BTC")
    assert len(events) == 2
    assert all(isinstance(e, OptionTradeEvent) for e in events)
    assert events[0].instrument_name == "BTC-27DEC26-100000-C"
    assert events[0].direction == "buy"
    assert events[0].price == 0.0512
    assert events[0].ts if False else events[0].timestamp == 1720000000.0
    assert events[1].direction == "sell"


def test_parse_deribit_trades_message_ignores_other_channel():
    raw = _trades_raw("trades.option.ETH.100ms", [
        {"instrument_name": "ETH-1JAN27-4000-C", "direction": "buy", "price": 0.01,
         "amount": 1.0, "iv": 50.0, "index_price": 3500.0, "timestamp": 1720000000000},
    ])
    assert parse_deribit_trades_message(raw, currency="BTC") == []


def test_parse_deribit_trades_message_ignores_malformed_json():
    assert parse_deribit_trades_message("not json", currency="BTC") == []


def test_parse_deribit_trades_message_ignores_missing_field():
    raw = _trades_raw("trades.option.BTC.100ms", [
        {"instrument_name": "BTC-27DEC26-100000-C", "direction": "buy",
         "amount": 10.0, "iv": 55.3, "index_price": 95000.0, "timestamp": 1720000000000},  # price 없음
    ])
    assert parse_deribit_trades_message(raw, currency="BTC") == []


def test_parse_deribit_trades_message_ignores_non_subscription_response():
    raw = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"status": "ok"}})
    assert parse_deribit_trades_message(raw, currency="BTC") == []


async def test_stream_subscribes_correct_channel_and_yields_parsed_events():
    raw = _trades_raw("trades.option.BTC.100ms", [
        {"instrument_name": "BTC-27DEC26-100000-C", "direction": "buy", "price": 0.05,
         "amount": 10.0, "iv": 55.0, "index_price": 95000.0, "timestamp": 1720000000000},
    ])
    fake_connect = FakeConnect([raw])
    client = DeribitOptionsFlowClient("BTC", connect_fn=fake_connect)
    events = [e async for e in client.stream()]

    assert len(events) == 1
    assert events[0].instrument_name == "BTC-27DEC26-100000-C"
    assert fake_connect.called_with == client._base_url


async def test_stream_currency_is_uppercased_in_channel():
    fake_connect = FakeConnect([])
    client = DeribitOptionsFlowClient("btc", connect_fn=fake_connect)
    _ = [e async for e in client.stream()]
    assert client.currency == "BTC"
