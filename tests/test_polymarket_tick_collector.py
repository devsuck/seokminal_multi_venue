# tests/test_polymarket_tick_collector.py
import json

from research.polymarket_tick.ws_collector import PolymarketTickWSClient, parse_tick_message

META = {
    "y1": {"condition_id": "c1", "question": "q1", "family": "sports", "outcome": "yes"},
    "n1": {"condition_id": "c1", "question": "q1", "family": "sports", "outcome": "no"},
}


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


async def test_stream_ticks_sends_subscribe_message_and_yields_raw_messages():
    fake_connect = FakeConnect(["msg1", "msg2"])
    client = PolymarketTickWSClient(connect_fn=fake_connect)
    received = [msg async for msg in client.stream_ticks(["y1", "n1"])]
    assert received == ["msg1", "msg2"]
    assert fake_connect.called_with == client._base_url


def test_subscribe_message_has_expected_shape():
    client = PolymarketTickWSClient(connect_fn=FakeConnect([]))
    assert client._subscribe_message(["y1", "n1"]) == {"assets_ids": ["y1", "n1"], "type": "market"}


def test_parse_tick_message_book_event_computes_best_bid_ask():
    raw = json.dumps({
        "event_type": "book", "asset_id": "y1",
        "bids": [{"price": "0.40", "size": "100"}, {"price": "0.45", "size": "50"}],
        "asks": [{"price": "0.55", "size": "80"}, {"price": "0.50", "size": "60"}],
    })
    rows = parse_tick_message(raw, META)
    assert len(rows) == 1
    row = rows[0]
    assert row["token_id"] == "y1"
    assert row["outcome"] == "yes"
    assert row["condition_id"] == "c1"
    assert row["event_type"] == "book"
    assert row["best_bid"] == 0.45
    assert row["best_ask"] == 0.50
    assert row["price"] is None
    assert row["size"] is None
    assert row["side"] is None


def test_parse_tick_message_price_change_event_expands_array():
    raw = json.dumps({
        "event_type": "price_change", "market": "0xabc",
        "price_changes": [
            {"asset_id": "y1", "price": "0.52", "size": "10", "side": "BUY", "best_bid": "0.51", "best_ask": "0.53"},
            {"asset_id": "n1", "price": "0.48", "size": "10", "side": "SELL", "best_bid": "0.47", "best_ask": "0.49"},
        ],
    })
    rows = parse_tick_message(raw, META)
    assert len(rows) == 2
    assert rows[0]["token_id"] == "y1"
    assert rows[0]["outcome"] == "yes"
    assert rows[0]["price"] == 0.52
    assert rows[0]["side"] == "BUY"
    assert rows[1]["token_id"] == "n1"
    assert rows[1]["outcome"] == "no"


def test_parse_tick_message_unknown_token_id_dropped():
    raw = json.dumps({"event_type": "book", "asset_id": "unknown", "bids": [], "asks": []})
    assert parse_tick_message(raw, META) == []


def test_parse_tick_message_unknown_event_type_ignored():
    raw = json.dumps({"event_type": "tick_size_change", "asset_id": "y1"})
    assert parse_tick_message(raw, META) == []


def test_parse_tick_message_invalid_json_returns_empty_list():
    assert parse_tick_message("not json", META) == []
