import datetime as dt
import json

import research.run_ib_orderflow_tick_collect as runner
from orderflow.models import OrderBookLevel, OrderBookSnapshot, TradeEvent


def _trade(price=100.0, size=1.0, side="buy", ts=1000.0, symbol="NQ"):
    return TradeEvent(symbol=symbol, ts=ts, price=price, size=size, side=side)


def _book(symbol="NQ", ts=1000.0):
    return OrderBookSnapshot(
        symbol=symbol, ts=ts,
        bids=[OrderBookLevel(price=99.75, size=5.0)],
        asks=[OrderBookLevel(price=100.25, size=3.0)],
    )


class FakeClient:
    """symbol별 stream() 호출을 리스트로 미리 정의 — 매 재연결 사이클마다 다음 behavior 소비."""

    def __init__(self, behaviors: list):
        self._behaviors = behaviors
        self.calls: list[str] = []

    async def stream(self, symbol, connect_timeout=15.0):
        self.calls.append(symbol)
        behavior = self._behaviors[len(self.calls) - 1]
        if isinstance(behavior, Exception):
            raise behavior
        for event in behavior:
            yield event


def test_append_deltas_writes_jsonl_to_symbol_dated_file(tmp_path):
    from unittest.mock import patch
    with patch.object(runner, "_DATA_DIR", tmp_path):
        runner.append_deltas("NQ", [{"type": "footprint_delta", "bucket_ts": 960.0}])
        path = tmp_path / f"NQ_{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
        lines = path.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["type"] == "footprint_delta"


def test_append_deltas_skips_write_when_empty(tmp_path):
    from unittest.mock import patch
    with patch.object(runner, "_DATA_DIR", tmp_path):
        runner.append_deltas("NQ", [])
    assert list(tmp_path.iterdir()) == []


async def test_run_symbol_forever_converts_trade_and_book_events_to_deltas():
    client = FakeClient([[_trade(), _book()]])
    appended = []
    await runner.run_symbol_forever(
        "NQ", client=client, append_fn=lambda symbol, deltas: appended.extend(deltas), max_cycles=1,
    )
    types = {d["type"] for d in appended}
    assert types == {"footprint_delta", "heatmap_delta"}


async def test_run_symbol_forever_uses_symbol_specific_client_id_when_no_client_passed():
    # client_factory 기본값이 CLIENT_IDS 매핑을 쓰는지는 run_forever 레벨에서 검증
    assert runner.CLIENT_IDS == {"NQ": 20, "MNQ": 21}


async def test_run_symbol_forever_backs_off_and_doubles_delay_on_repeated_failure():
    from unittest.mock import patch
    client = FakeClient([ConnectionError("boom"), ConnectionError("boom")])
    with patch("asyncio.sleep") as mock_sleep:
        await runner.run_symbol_forever(
            "NQ", client=client, append_fn=lambda symbol, deltas: None, max_cycles=2,
        )
    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [runner.RECONNECT_BASE_DELAY, runner.RECONNECT_BASE_DELAY * 2]


async def test_run_symbol_forever_resets_delay_after_success():
    from unittest.mock import patch
    client = FakeClient([ConnectionError("boom"), [_trade()]])
    with patch("asyncio.sleep") as mock_sleep:
        await runner.run_symbol_forever(
            "NQ", client=client, append_fn=lambda symbol, deltas: None, max_cycles=2,
        )
    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [runner.RECONNECT_BASE_DELAY]


async def test_run_symbol_forever_backs_off_on_clean_close_without_events():
    from unittest.mock import patch
    client = FakeClient([[], []])
    with patch("asyncio.sleep") as mock_sleep:
        await runner.run_symbol_forever(
            "NQ", client=client, append_fn=lambda symbol, deltas: None, max_cycles=2,
        )
    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [runner.RECONNECT_BASE_DELAY, runner.RECONNECT_BASE_DELAY * 2]


async def test_run_forever_runs_all_symbols_concurrently_with_distinct_client_ids():
    clients = {"NQ": FakeClient([[_trade()]]), "MNQ": FakeClient([[_trade(symbol="MNQ")]])}
    seen_ids = []

    def factory(symbol):
        seen_ids.append(symbol)
        return clients[symbol]

    appended = []
    await runner.run_forever(
        symbols=["NQ", "MNQ"],
        client_factory=factory,
        append_fn=lambda symbol, deltas: appended.append((symbol, deltas)),
        max_cycles=1,
    )
    assert {s for s, _ in appended} == {"NQ", "MNQ"}
