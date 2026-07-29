import datetime as dt
import json
from unittest.mock import patch

import research.run_cross_venue_skew_collect as runner
from orderflow.models import OrderBookLevel, OrderBookSnapshot, TradeEvent


def _book(symbol="BTC.HL", ts=1.0, price=100.0):
    return OrderBookSnapshot(
        symbol=symbol, ts=ts,
        bids=[OrderBookLevel(price=price - 1, size=1.0)],
        asks=[OrderBookLevel(price=price + 1, size=1.0)],
    )


def _trade(price=100.0, size=1.0, side="buy", ts=1.0, symbol="BTC.HL"):
    return TradeEvent(symbol=symbol, ts=ts, price=price, size=size, side=side)


class FakeClient:
    """venue별 stream()/stream_depth() 호출을 리스트로 미리 정의 —
    매 재연결 사이클마다 다음 behavior 소비. 두 메서드 다 같은 behavior 큐를 씀."""

    def __init__(self, behaviors: list):
        self._behaviors = behaviors
        self.calls: list[str] = []

    async def _consume(self, coin):
        self.calls.append(coin)
        behavior = self._behaviors[len(self.calls) - 1]
        if isinstance(behavior, Exception):
            raise behavior
        for event in behavior:
            yield event

    async def stream(self, coin):
        async for event in self._consume(coin):
            yield event

    async def stream_depth(self, coin):
        async for event in self._consume(coin):
            yield event


def test_append_snapshots_writes_jsonl_to_venue_coin_dated_file(tmp_path):
    with patch.object(runner, "_DATA_DIR", tmp_path):
        runner.append_snapshots("binance", "BTC", [_book(), _book(price=101.0)])
        path = tmp_path / f"binance_BTC_{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
        lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["bids"][0]["price"] == 99.0


def test_append_snapshots_skips_write_when_empty(tmp_path):
    with patch.object(runner, "_DATA_DIR", tmp_path):
        runner.append_snapshots("binance", "BTC", [])
    assert list(tmp_path.iterdir()) == []


async def test_run_venue_coin_forever_appends_only_book_snapshots_not_trades():
    client = FakeClient([[_book(), _trade(), _book(price=102.0)]])
    appended = []
    await runner.run_venue_coin_forever(
        "hl", "BTC", client=client,
        append_fn=lambda venue, coin, snaps: appended.extend(snaps), max_cycles=1,
    )
    assert len(appended) == 2
    assert appended[0].bids[0].price == 99.0
    assert appended[1].bids[0].price == 101.0


async def test_run_venue_coin_forever_uses_stream_depth_for_non_hl_venues():
    client = FakeClient([[_book()]])
    appended = []
    await runner.run_venue_coin_forever(
        "binance", "BTC", client=client,
        append_fn=lambda venue, coin, snaps: appended.extend(snaps), max_cycles=1,
    )
    assert len(appended) == 1


async def test_run_venue_coin_forever_backs_off_and_doubles_delay_on_repeated_failure():
    client = FakeClient([ConnectionError("boom"), ConnectionError("boom")])
    with patch("asyncio.sleep") as mock_sleep:
        await runner.run_venue_coin_forever(
            "hl", "BTC", client=client,
            append_fn=lambda venue, coin, snaps: None, max_cycles=2,
        )
    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [runner.RECONNECT_BASE_DELAY, runner.RECONNECT_BASE_DELAY * 2]


async def test_run_venue_coin_forever_resets_delay_after_success():
    client = FakeClient([ConnectionError("boom"), [_book()]])
    with patch("asyncio.sleep") as mock_sleep:
        await runner.run_venue_coin_forever(
            "hl", "BTC", client=client,
            append_fn=lambda venue, coin, snaps: None, max_cycles=2,
        )
    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [runner.RECONNECT_BASE_DELAY]


async def test_run_forever_runs_all_venue_coin_combinations_concurrently():
    made_for = []

    def factory(venue):
        made_for.append(venue)
        return FakeClient([[_book()]])

    appended = []
    await runner.run_forever(
        venues=["hl", "binance", "okx"], coins=["BTC", "ETH"],
        client_factory=factory,
        append_fn=lambda venue, coin, snaps: appended.append((venue, coin)),
        max_cycles=1,
    )
    assert len(made_for) == 6
    assert len(appended) == 6
