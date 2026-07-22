"""수집기 워치독 재기동 판정(순수) 유닛테스트."""
from ops.collector_watchdog import to_restart


def _fleet(*verdicts):
    return {"collectors": [{"key": f"c{i}", "verdict": v} for i, v in enumerate(verdicts)]}


def test_restarts_dead_only_by_default():
    assert to_restart(_fleet("fresh", "dead", "stale", "dead")) == ["c1", "c3"]


def test_restarts_stale_when_enabled():
    assert to_restart(_fleet("fresh", "stale", "dead"), restart_stale=True) == ["c1", "c2"]


def test_all_fresh_no_restart():
    assert to_restart(_fleet("fresh", "fresh")) == []


def test_empty_fleet():
    assert to_restart({}) == []
