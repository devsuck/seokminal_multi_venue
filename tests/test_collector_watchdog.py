"""수집기 워치독 재기동 판정(순수) 유닛테스트."""
import ops.collector_watchdog as watchdog
from ops.collector_watchdog import to_restart


def _fleet(*verdicts):
    return {"collectors": [{"key": f"c{i}", "verdict": v} for i, v in enumerate(verdicts)]}


def test_restarts_dead_only_by_default():
    assert to_restart(_fleet("fresh", "dead", "stale", "dead")) == ["c1", "c3"]


def test_restarts_stale_when_enabled():
    assert to_restart(_fleet("fresh", "stale", "dead"), restart_stale=True) == ["c1", "c2"]


def test_stuck_not_restarted_by_default():
    assert to_restart(_fleet("fresh", "stuck", "dead")) == ["c2"]


def test_stuck_restarted_when_stale_enabled():
    assert to_restart(_fleet("fresh", "stuck", "stale"), restart_stale=True) == ["c1", "c2"]


def test_all_fresh_no_restart():
    assert to_restart(_fleet("fresh", "fresh")) == []


def test_empty_fleet():
    assert to_restart({}) == []


def test_notify_dedups_same_condition_then_refires_after_clear(monkeypatch):
    calls = []
    monkeypatch.setattr(watchdog.subprocess, "run", lambda *a, **k: calls.append(a))
    watchdog._NOTIFIED.clear()
    watchdog._notify("c0:dead", "c0 dead")
    watchdog._notify("c0:dead", "c0 dead again")
    assert len(calls) == 1
    watchdog._NOTIFIED.discard("c0:dead")
    watchdog._notify("c0:dead", "c0 dead once more")
    assert len(calls) == 2
