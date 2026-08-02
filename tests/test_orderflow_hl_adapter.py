import asyncio
import json

import pytest

from orderflow.hl_adapter import HyperliquidOrderflowClient, parse_hl_message
from orderflow.models import OrderBookSnapshot, TradeEvent


class FakeConnection:
    def __init__(self, incoming: list[str], hang: bool = False):
        self._incoming = incoming
        self._hang = hang
        self.sent: list[str] = []

    async def send(self, message: str) -> None:
        self.sent.append(message)

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        if self._hang:
            await asyncio.sleep(3600)  # idle_timeout 가드가 이걸 끊어줘야 함
            return
        for msg in self._incoming:
            yield msg

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class HangingConnect:
    """connect_fn 자체가 응답 없이 멈추는 상황(getaddrinfo OS 레벨 정지) 시뮬레이션."""

    def __call__(self, uri: str):
        return self

    async def __aenter__(self):
        await asyncio.sleep(3600)

    async def __aexit__(self, *exc):
        return False


class FakeConnect:
    def __init__(self, incoming: list[str]):
        self._incoming = incoming
        self.called_with = None

    def __call__(self, uri: str):
        self.called_with = uri
        return FakeConnection(self._incoming)


def test_parse_hl_message_l2book():
    raw = json.dumps({
        "channel": "l2Book",
        "data": {
            "coin": "BTC", "time": 1720000000000,
            "levels": [
                [{"px": "65000.0", "sz": "1.5", "n": 2}],
                [{"px": "65010.0", "sz": "2.0", "n": 1}],
            ],
        },
    })
    events = parse_hl_message(raw, coin="BTC")
    assert len(events) == 1
    snap = events[0]
    assert isinstance(snap, OrderBookSnapshot)
    assert snap.symbol == "BTC.HL"
    assert snap.ts == 1720000000.0
    assert snap.bids[0].price == 65000.0
    assert snap.asks[0].size == 2.0


def test_parse_hl_message_trades_maps_side():
    raw = json.dumps({
        "channel": "trades",
        "data": [
            {"coin": "BTC", "side": "B", "px": "65000.0", "sz": "0.1", "time": 1720000001000},
            {"coin": "BTC", "side": "A", "px": "64990.0", "sz": "0.2", "time": 1720000002000},
        ],
    })
    events = parse_hl_message(raw, coin="BTC")
    assert len(events) == 2
    assert all(isinstance(e, TradeEvent) for e in events)
    assert events[0].side == "buy"
    assert events[1].side == "sell"
    assert events[0].symbol == "BTC.HL"


def test_parse_hl_message_ignores_unknown_channel():
    raw = json.dumps({"channel": "subscriptionResponse", "data": {}})
    assert parse_hl_message(raw, coin="BTC") == []


def test_parse_hl_message_ignores_malformed_json():
    assert parse_hl_message("not json", coin="BTC") == []


def test_parse_hl_message_ignores_l2book_missing_field():
    raw = json.dumps({
        "channel": "l2Book",
        "data": {
            "coin": "BTC", "time": 1720000000000,
            "levels": [
                [{"sz": "1.5", "n": 2}],  # px 없음
                [{"px": "65010.0", "sz": "2.0", "n": 1}],
            ],
        },
    })
    assert parse_hl_message(raw, coin="BTC") == []


def test_parse_hl_message_ignores_trades_missing_field():
    raw = json.dumps({
        "channel": "trades",
        "data": [
            {"coin": "BTC", "side": "B", "sz": "0.1", "time": 1720000001000},  # px 없음
        ],
    })
    assert parse_hl_message(raw, coin="BTC") == []


async def test_stream_subscribes_l2book_and_trades_then_yields_parsed_events():
    raw_book = json.dumps({
        "channel": "l2Book",
        "data": {"coin": "BTC", "time": 1720000000000, "levels": [[], []]},
    })
    fake_connect = FakeConnect([raw_book])
    client = HyperliquidOrderflowClient(connect_fn=fake_connect)
    events = [e async for e in client.stream("BTC")]
    assert len(events) == 1
    assert isinstance(events[0], OrderBookSnapshot)
    assert fake_connect.called_with == client._base_url


async def test_stream_raises_timeout_when_idle_too_long():
    client = HyperliquidOrderflowClient(connect_fn=lambda uri: FakeConnection([], hang=True))
    with pytest.raises(asyncio.TimeoutError):
        async for _ in client.stream("BTC", idle_timeout=0.02):
            pass


async def test_stream_raises_timeout_when_connect_hangs():
    client = HyperliquidOrderflowClient(connect_fn=HangingConnect())
    with pytest.raises(asyncio.TimeoutError):
        async for _ in client.stream("BTC", connect_timeout=0.02):
            pass
