import datetime as dt
import json
from unittest.mock import patch

import research.run_polymarket_tick_collect as runner


def _market(condition_id="c1", end_date="2026-07-10", clob_token_ids=("y1", "n1")):
    return {
        "condition_id": condition_id, "question": f"q-{condition_id}", "event_id": "e1",
        "event_title": "", "end_date": end_date, "volume": 1000.0, "liquidity": 10000.0,
        "yes_price": 0.5, "no_price": 0.5, "active": True, "closed": False,
        "accepting_orders": True, "clob_token_ids": clob_token_ids,
        "sports_market_type": None, "game_start_time": None,
    }


class FakeClient:
    def __init__(self, behaviors: list):
        self._behaviors = behaviors
        self.calls: list[list[str]] = []

    async def stream_ticks(self, asset_ids):
        self.calls.append(asset_ids)
        behavior = self._behaviors[len(self.calls) - 1]
        if isinstance(behavior, Exception):
            raise behavior
        for msg in behavior:
            yield msg


def test_append_ticks_writes_jsonl_to_dated_file(tmp_path):
    with patch.object(runner, "_DATA_DIR", tmp_path):
        runner.append_ticks([{"token_id": "y1"}, {"token_id": "n1"}])
        path = tmp_path / f"{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
        lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["token_id"] == "y1"


def test_append_ticks_skips_write_when_empty(tmp_path):
    with patch.object(runner, "_DATA_DIR", tmp_path):
        runner.append_ticks([])
    assert list(tmp_path.iterdir()) == []


async def test_run_forever_skips_cycle_when_no_target_markets():
    with patch("asyncio.sleep") as mock_sleep:
        await runner.run_forever(
            get_markets_fn=lambda: [],
            client=FakeClient([]),
            append_fn=lambda ticks: None,
            max_cycles=1,
        )
    mock_sleep.assert_called_once_with(runner.RESELECT_INTERVAL_SEC)


async def test_run_forever_parses_and_appends_ticks_from_stream():
    raw_book = json.dumps({"event_type": "book", "asset_id": "y1", "bids": [{"price": "0.4", "size": "10"}], "asks": []})
    client = FakeClient([[raw_book]])
    appended = []
    await runner.run_forever(
        get_markets_fn=lambda: [_market()],
        client=client,
        append_fn=appended.append,
        max_cycles=1,
    )
    assert client.calls == [["y1", "n1"]]
    assert len(appended) == 1
    assert appended[0][0]["token_id"] == "y1"


async def test_run_forever_backs_off_and_doubles_delay_on_repeated_failure():
    client = FakeClient([ConnectionError("boom"), ConnectionError("boom")])
    with patch("asyncio.sleep") as mock_sleep:
        await runner.run_forever(
            get_markets_fn=lambda: [_market()],
            client=client,
            append_fn=lambda ticks: None,
            max_cycles=2,
        )
    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [runner.RECONNECT_BASE_DELAY, runner.RECONNECT_BASE_DELAY * 2]


async def test_run_forever_resets_delay_after_success():
    raw_book = json.dumps({"event_type": "book", "asset_id": "y1", "bids": [{"price": "0.4", "size": "10"}], "asks": []})
    client = FakeClient([ConnectionError("boom"), [raw_book]])
    with patch("asyncio.sleep") as mock_sleep:
        await runner.run_forever(
            get_markets_fn=lambda: [_market()],
            client=client,
            append_fn=lambda ticks: None,
            max_cycles=2,
        )
    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [runner.RECONNECT_BASE_DELAY]


async def test_run_forever_backs_off_on_clean_close_without_ticks():
    # stream_ticks()가 예외 없이 즉시 끝나며 틱을 하나도 내보내지 않은 경우(서버의 클린 클로즈 등) —
    # 백오프 없이 즉시 재연결하면 핫루프가 되므로 예외 케이스와 동일하게 지연을 적용해야 한다.
    client = FakeClient([[], []])
    with patch("asyncio.sleep") as mock_sleep:
        await runner.run_forever(
            get_markets_fn=lambda: [_market()],
            client=client,
            append_fn=lambda ticks: None,
            max_cycles=2,
        )
    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [runner.RECONNECT_BASE_DELAY, runner.RECONNECT_BASE_DELAY * 2]


async def test_run_forever_reuses_last_markets_when_reselect_fails():
    def flaky_get_markets():
        flaky_get_markets.calls += 1
        if flaky_get_markets.calls == 1:
            return [_market()]
        raise RuntimeError("gamma down")
    flaky_get_markets.calls = 0

    client = FakeClient([[], []])
    appended = []
    with patch("asyncio.sleep"):
        await runner.run_forever(
            get_markets_fn=flaky_get_markets,
            client=client,
            append_fn=appended.append,
            max_cycles=2,
        )
    assert client.calls == [["y1", "n1"], ["y1", "n1"]]
