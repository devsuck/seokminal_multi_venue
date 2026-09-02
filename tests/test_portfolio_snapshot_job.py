"""portfolio_snapshots.jsonl append + 실패 삼킴 테스트."""
from __future__ import annotations

import json

from jarvis.broker_readonly import snapshot_job


def test_append_snapshot_writes_jsonl_line(tmp_path):
    path = tmp_path / "snap.jsonl"
    snapshot_job._append_snapshot("live", 1234.5, path=path)
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["mode"] == "live" and row["total_equity_usd"] == 1234.5 and "ts" in row


async def test_snapshot_once_swallows_aggregator_errors(monkeypatch):
    class _Boom:
        def __init__(self, mode):
            pass

        async def summary(self):
            raise RuntimeError("kis timeout")

    monkeypatch.setattr(snapshot_job, "PortfolioAggregator", _Boom)
    await snapshot_job._snapshot_once()  # 예외 안 남으면 통과


async def test_snapshot_once_writes_both_modes(monkeypatch, tmp_path):
    monkeypatch.setattr(snapshot_job, "_SNAPSHOT_PATH", tmp_path / "snap.jsonl")

    class _Fake:
        def __init__(self, mode):
            self.mode = mode

        async def summary(self):
            return {"total_equity_usd": 100.0 if self.mode == "live" else 50.0}

    monkeypatch.setattr(snapshot_job, "PortfolioAggregator", _Fake)
    await snapshot_job._snapshot_once()
    lines = (tmp_path / "snap.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2
    modes = {json.loads(line)["mode"] for line in lines}
    assert modes == {"live", "paper"}
