"""Auto-Research 엔진 — latest_bh_survivor 리더 + classify 통합."""
from __future__ import annotations

import json

from research.autoresearch import engine


def test_latest_bh_survivor_reads_leaderboard(tmp_path, monkeypatch):
    status = tmp_path / "status.json"
    status.write_text(json.dumps({
        "leaderboard": [
            {"cid": "ev_buyback", "bh_survivor": True},
            {"cid": "ev_spinoff", "bh_survivor": False},
        ]
    }), encoding="utf-8")
    monkeypatch.setattr(engine, "STATUS", str(status))
    assert engine.latest_bh_survivor("buyback") is True
    assert engine.latest_bh_survivor("spinoff") is False


def test_latest_bh_survivor_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "STATUS", str(tmp_path / "nope.json"))
    assert engine.latest_bh_survivor("buyback") is None


def test_latest_bh_survivor_family_absent_returns_none(tmp_path, monkeypatch):
    status = tmp_path / "status.json"
    status.write_text(json.dumps({"leaderboard": [{"cid": "ev_other", "bh_survivor": True}]}),
                      encoding="utf-8")
    monkeypatch.setattr(engine, "STATUS", str(status))
    assert engine.latest_bh_survivor("buyback") is None
