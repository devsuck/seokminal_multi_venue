"""수집기 함대 헬스 판정 유닛테스트."""
from api_server.fleet_health import classify, classify_disk, count_restarts_by_key, fleet_summary, stale_after


def test_classify_fresh():
    r = classify("polymarket_tick", {"running": True, "session_exists": True,
                                     "last_write": "2026-07-22T00:00:00Z", "age_sec": 30})
    assert r["verdict"] == "fresh" and r["stale_after_s"] == 300


def test_classify_stale_over_threshold():
    r = classify("polymarket_tick", {"running": True, "session_exists": True,
                                     "last_write": "x", "age_sec": 400})
    assert r["verdict"] == "stale"          # 400 > 300 임계


def test_classify_dead_no_process():
    r = classify("hl_orderflow_tick", {"running": False, "session_exists": True,
                                       "last_write": "x", "age_sec": 10})
    assert r["verdict"] == "dead" and "python" in r["reason"]


def test_classify_dead_no_data():
    r = classify("cross_venue_skew_tick", {"running": True, "session_exists": True,
                                           "last_write": None, "age_sec": None})
    assert r["verdict"] == "dead" and "파일" in r["reason"]


def test_default_threshold_for_unknown_key():
    assert stale_after("something_new") == 900
    assert stale_after("polymarket_arb") == 1800


def test_fleet_summary_worst_and_counts():
    rows = [
        classify("polymarket_tick", {"running": True, "age_sec": 30}),           # fresh
        classify("polymarket_arb", {"running": True, "age_sec": 5000}),          # stale (>1800)
        classify("hl_orderflow_tick", {"running": False, "age_sec": 1}),         # dead
    ]
    s = fleet_summary(rows)
    assert s["ok"] is False
    assert s["worst_verdict"] == "dead"
    assert s["counts"] == {"fresh": 1, "stale": 1, "dead": 1, "stuck": 0}
    assert s["collectors"][0]["verdict"] == "dead"       # 나쁜 것 먼저 정렬


def test_fleet_summary_all_fresh_ok():
    rows = [classify("polymarket_tick", {"running": True, "age_sec": 10})]
    s = fleet_summary(rows)
    assert s["ok"] is True and s["worst_verdict"] == "fresh"


def test_classify_stuck_far_past_threshold():
    # polymarket_tick 임계 300s, STUCK_MULTIPLIER=4 → 1200s 넘으면 stuck
    r = classify("polymarket_tick", {"running": True, "age_sec": 1300})
    assert r["verdict"] == "stuck"


def test_classify_stale_not_yet_stuck():
    r = classify("polymarket_tick", {"running": True, "age_sec": 1199})
    assert r["verdict"] == "stale"


def test_stuck_ranks_worse_than_stale_but_better_than_dead():
    rows = [
        classify("polymarket_tick", {"running": True, "age_sec": 1300}),   # stuck
        classify("polymarket_arb", {"running": True, "age_sec": 5000}),    # stale
        classify("hl_orderflow_tick", {"running": False, "age_sec": 1}),   # dead
    ]
    s = fleet_summary(rows)
    assert s["worst_verdict"] == "dead"
    assert [c["verdict"] for c in s["collectors"]] == ["dead", "stuck", "stale"]
    assert s["ok"] is False


def test_classify_flapping_flag_from_restart_count():
    fresh_not_flapping = classify("polymarket_tick", {"running": True, "age_sec": 10}, restart_count_24h=2)
    fresh_flapping = classify("polymarket_tick", {"running": True, "age_sec": 10}, restart_count_24h=3)
    assert fresh_not_flapping["flapping"] is False
    assert fresh_flapping["flapping"] is True
    assert fresh_flapping["restart_count_24h"] == 3


def test_fleet_summary_not_ok_when_flapping_even_if_fresh():
    rows = [classify("polymarket_arb", {"running": True, "age_sec": 10}, restart_count_24h=5)]
    s = fleet_summary(rows)
    assert s["ok"] is False
    assert s["worst_verdict"] == "fresh"       # verdict 자체는 그대로


def test_count_restarts_by_key_windows_and_groups():
    now = 1_000_000.0
    events = [
        {"key": "polymarket_arb", "ts": now - 100},
        {"key": "polymarket_arb", "ts": now - 200},
        {"key": "polymarket_arb", "ts": now - 90_000},   # 24h 밖(>86400s)
        {"key": "polymarket_updown_arb", "ts": now - 300},
    ]
    counts = count_restarts_by_key(events, now)
    assert counts == {"polymarket_arb": 2, "polymarket_updown_arb": 1}


def test_classify_disk_tiers():
    assert classify_disk(free_gb=50.0, total_gb=228.0)["verdict"] == "ok"
    assert classify_disk(free_gb=15.0, total_gb=228.0)["verdict"] == "warn"
    assert classify_disk(free_gb=5.0, total_gb=228.0)["verdict"] == "critical"
