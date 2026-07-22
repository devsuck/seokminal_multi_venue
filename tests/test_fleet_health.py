"""수집기 함대 헬스 판정 유닛테스트."""
from api_server.fleet_health import classify, fleet_summary, stale_after


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
    assert s["counts"] == {"fresh": 1, "stale": 1, "dead": 1}
    assert s["collectors"][0]["verdict"] == "dead"       # 나쁜 것 먼저 정렬


def test_fleet_summary_all_fresh_ok():
    rows = [classify("polymarket_tick", {"running": True, "age_sec": 10})]
    s = fleet_summary(rows)
    assert s["ok"] is True and s["worst_verdict"] == "fresh"
