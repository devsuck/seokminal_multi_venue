import datetime as dt
import json
from unittest.mock import patch

import research.run_gex_snapshot_collect as runner


def _snapshot(currency="BTC", spot=95000.0, levels=None):
    return {
        "currency": currency, "spot": spot, "updated_at": 100.0,
        "levels": levels if levels is not None else [{"strike": 100000.0, "call_gex": 1.0, "put_gex": 0.5, "net_gex": 0.5}],
    }


def test_append_snapshot_writes_jsonl_to_currency_dated_file(tmp_path):
    with patch.object(runner, "_DATA_DIR", tmp_path):
        runner.append_snapshot("BTC", _snapshot())
        path = tmp_path / f"BTC_{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
        lines = path.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["spot"] == 95000.0


def test_append_snapshot_skips_write_when_no_levels(tmp_path):
    with patch.object(runner, "_DATA_DIR", tmp_path):
        runner.append_snapshot("BTC", _snapshot(levels=[]))
    assert list(tmp_path.iterdir()) == []


async def test_run_forever_polls_all_currencies_and_appends():
    calls = []

    async def fake_fetch(currency):
        calls.append(currency)
        return _snapshot(currency=currency)

    appended = []
    with patch("asyncio.sleep") as mock_sleep:
        await runner.run_forever(
            currencies=["BTC", "ETH"], fetch_fn=fake_fetch,
            append_fn=lambda c, s: appended.append((c, s)), max_cycles=1,
        )
    assert calls == ["BTC", "ETH"]
    assert {c for c, _ in appended} == {"BTC", "ETH"}
    mock_sleep.assert_called_once_with(runner.GEX_POLL_INTERVAL_SEC)


async def test_run_forever_continues_after_fetch_failure():
    async def failing_fetch(currency):
        if currency == "BTC":
            raise ConnectionError("boom")
        return _snapshot(currency=currency)

    appended = []
    with patch("asyncio.sleep"):
        await runner.run_forever(
            currencies=["BTC", "ETH"], fetch_fn=failing_fetch,
            append_fn=lambda c, s: appended.append((c, s)), max_cycles=1,
        )
    assert {c for c, _ in appended} == {"ETH"}
