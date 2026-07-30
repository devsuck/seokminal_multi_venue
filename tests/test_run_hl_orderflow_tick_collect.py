import datetime as dt
import json
from unittest.mock import patch

import research.run_hl_orderflow_tick_collect as runner
from orderflow.models import OrderBookSnapshot, TradeEvent


def _trade(price=100.0, size=1.0, side="buy", ts=1.0, symbol="BTC.HL"):
    return TradeEvent(symbol=symbol, ts=ts, price=price, size=size, side=side)


def _book(symbol="BTC.HL", ts=1.0, bids=None, asks=None):
    return OrderBookSnapshot(symbol=symbol, ts=ts, bids=bids or [], asks=asks or [])


class FakeClient:
    """coin별 stream() 호출을 리스트로 미리 정의 — 매 재연결 사이클마다 다음 behavior 소비."""

    def __init__(self, behaviors: list):
        self._behaviors = behaviors
        self.calls: list[str] = []

    async def stream(self, coin):
        self.calls.append(coin)
        behavior = self._behaviors[len(self.calls) - 1]
        if isinstance(behavior, Exception):
            raise behavior
        for event in behavior:
            yield event


def test_append_trades_writes_jsonl_to_coin_dated_file(tmp_path):
    with patch.object(runner, "_DATA_DIR", tmp_path):
        runner.append_trades("BTC", [_trade().model_dump(), _trade(price=101.0).model_dump()])
        path = tmp_path / f"BTC_{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
        lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["price"] == 100.0


def test_append_trades_skips_write_when_empty(tmp_path):
    with patch.object(runner, "_DATA_DIR", tmp_path):
        runner.append_trades("BTC", [])
    assert list(tmp_path.iterdir()) == []


async def test_run_coin_forever_appends_only_trade_events_not_book_snapshots():
    client = FakeClient([[_book(), _trade(), _book(), _trade(price=102.0)]])
    appended = []
    await runner.run_coin_forever(
        "BTC", client=client, append_fn=lambda coin, trades: appended.extend(trades), max_cycles=1,
    )
    assert len(appended) == 2
    assert appended[0]["price"] == 100.0
    assert appended[1]["price"] == 102.0


async def test_run_coin_forever_converts_book_snapshots_to_heatmap_deltas():
    from orderflow.models import OrderBookLevel

    book = _book(bids=[OrderBookLevel(price=90.0, size=1.5)], asks=[OrderBookLevel(price=110.0, size=2.0)])
    client = FakeClient([[book]])
    depth_appended = []
    await runner.run_coin_forever(
        "BTC", client=client,
        append_fn=lambda coin, trades: None,
        depth_append_fn=lambda coin, deltas: depth_appended.extend(deltas),
        max_cycles=1,
    )
    assert len(depth_appended) == 2
    assert {d["price"] for d in depth_appended} == {90.0, 110.0}
    assert all(d["type"] == "heatmap_delta" for d in depth_appended)


def test_append_depth_writes_jsonl_to_coin_dated_file(tmp_path):
    with patch.object(runner, "_DEPTH_DATA_DIR", tmp_path):
        runner.append_depth("BTC", [{"type": "heatmap_delta", "ts": 0.0, "price": 100.0, "size": 1.0}])
        path = tmp_path / f"BTC_{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
        lines = path.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["price"] == 100.0


def test_append_depth_skips_write_when_empty(tmp_path):
    with patch.object(runner, "_DEPTH_DATA_DIR", tmp_path):
        runner.append_depth("BTC", [])
    assert list(tmp_path.iterdir()) == []


def test_append_snapshot_writes_jsonl_to_coin_dated_file(tmp_path):
    with patch.object(runner, "_SNAPSHOT_DATA_DIR", tmp_path):
        runner.append_snapshot("BTC", [{"ts": 1.0, "bids": [[100.0, 1.0]], "asks": [[101.0, 2.0]]}])
        path = tmp_path / f"BTC_{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
        lines = path.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["bids"] == [[100.0, 1.0]]


def test_append_snapshot_skips_write_when_empty(tmp_path):
    with patch.object(runner, "_SNAPSHOT_DATA_DIR", tmp_path):
        runner.append_snapshot("BTC", [])
    assert list(tmp_path.iterdir()) == []


async def test_run_coin_forever_persists_snapshot_sorted_and_capped_to_top_n():
    from orderflow.models import OrderBookLevel

    bids = [OrderBookLevel(price=p, size=1.0) for p in [90.0, 92.0, 88.0]]
    asks = [OrderBookLevel(price=p, size=1.0) for p in [111.0, 109.0, 113.0]]
    book = _book(ts=100.0, bids=bids, asks=asks)
    client = FakeClient([[book]])
    snapshots = []
    with patch.object(runner, "SNAPSHOT_LEVELS", 2):
        await runner.run_coin_forever(
            "BTC", client=client,
            append_fn=lambda coin, trades: None,
            depth_append_fn=lambda coin, deltas: None,
            snapshot_append_fn=lambda coin, snaps: snapshots.extend(snaps),
            max_cycles=1,
        )
    assert len(snapshots) == 1
    assert snapshots[0]["ts"] == 100.0
    assert snapshots[0]["bids"] == [[92.0, 1.0], [90.0, 1.0]]  # 내림차순 top-2
    assert snapshots[0]["asks"] == [[109.0, 1.0], [111.0, 1.0]]  # 오름차순 top-2


async def test_run_coin_forever_throttles_snapshot_persistence_by_event_ts():
    base_ts = 1_000_000.0  # last_snapshot_ts는 0.0에서 시작하므로 첫 스냅샷은 항상 저장됨
    first_book = _book(ts=base_ts)
    within_throttle_book = _book(ts=base_ts + runner.SNAPSHOT_THROTTLE_SEC - 0.1)
    past_throttle_book = _book(ts=base_ts + runner.SNAPSHOT_THROTTLE_SEC)
    client = FakeClient([[first_book, within_throttle_book, past_throttle_book]])
    snapshots = []
    await runner.run_coin_forever(
        "BTC", client=client,
        append_fn=lambda coin, trades: None,
        depth_append_fn=lambda coin, deltas: None,
        snapshot_append_fn=lambda coin, snaps: snapshots.extend(snaps),
        max_cycles=1,
    )
    assert [s["ts"] for s in snapshots] == [base_ts, base_ts + runner.SNAPSHOT_THROTTLE_SEC]


async def test_run_coin_forever_backs_off_and_doubles_delay_on_repeated_failure():
    client = FakeClient([ConnectionError("boom"), ConnectionError("boom")])
    with patch("asyncio.sleep") as mock_sleep:
        await runner.run_coin_forever(
            "BTC", client=client, append_fn=lambda coin, trades: None, max_cycles=2,
        )
    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [runner.RECONNECT_BASE_DELAY, runner.RECONNECT_BASE_DELAY * 2]


async def test_run_coin_forever_resets_delay_after_success():
    client = FakeClient([ConnectionError("boom"), [_trade()]])
    with patch("asyncio.sleep") as mock_sleep:
        await runner.run_coin_forever(
            "BTC", client=client, append_fn=lambda coin, trades: None, max_cycles=2,
        )
    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [runner.RECONNECT_BASE_DELAY]


async def test_run_coin_forever_backs_off_on_clean_close_without_trades():
    client = FakeClient([[], []])
    with patch("asyncio.sleep") as mock_sleep:
        await runner.run_coin_forever(
            "BTC", client=client, append_fn=lambda coin, trades: None, max_cycles=2,
        )
    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [runner.RECONNECT_BASE_DELAY, runner.RECONNECT_BASE_DELAY * 2]


async def test_run_forever_runs_all_coins_concurrently():
    clients = {"BTC": FakeClient([[_trade()]]), "ETH": FakeClient([[_trade(symbol="ETH.HL")]])}
    appended = []
    await runner.run_forever(
        coins=["BTC", "ETH"],
        client_factory=lambda coin: clients[coin],
        append_fn=lambda coin, trades: appended.append((coin, trades)),
        max_cycles=1,
    )
    assert {c for c, _ in appended} == {"BTC", "ETH"}
