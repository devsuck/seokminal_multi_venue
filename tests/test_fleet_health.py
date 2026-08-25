"""수집기 함대 헬스 판정 유닛테스트."""
import time

from api_server.fleet_health import classify, classify_disk, count_restarts_by_key, fleet_summary, stale_after


def test_classify_fresh():
    r = classify("hl_orderflow_tick", {"running": True, "session_exists": True,
                                       "last_write": "2026-07-22T00:00:00Z", "age_sec": 30})
    assert r["verdict"] == "fresh" and r["stale_after_s"] == 300


def test_classify_stale_over_threshold():
    r = classify("hl_orderflow_tick", {"running": True, "session_exists": True,
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
    assert stale_after("options_uoa") == 3600


def test_convergence_legs_not_stale_between_cycles():
    """convergence_legs(6h 폴링)는 사이클 대기 중에 stale로 찍히면 안 된다(2026-08-15 발견).
    임계는 실제 사이클 상수보다 커야 함."""
    from research.run_convergence_signal_collect import POLL_INTERVAL_SEC

    assert stale_after("convergence_legs") > POLL_INTERVAL_SEC
    r = classify("convergence_legs", {"running": True, "age_sec": int(POLL_INTERVAL_SEC) - 1})
    assert r["verdict"] == "fresh"


def test_heartbeat_keeps_event_driven_collector_fresh(tmp_path):
    """이벤트 0건이어도 하트비트가 있으면 폴링 생존으로 판정돼야 한다."""
    from research.collector_heartbeat import touch_heartbeat

    hb = touch_heartbeat(tmp_path / "options_uoa")
    assert hb.exists() and hb.suffix != ".jsonl"   # 이벤트 glob(*.jsonl)에 섞이면 안 됨
    age = int(time.time() - hb.stat().st_mtime)
    assert classify("options_uoa", {"running": True, "age_sec": age})["verdict"] == "fresh"


def test_fleet_summary_worst_and_counts():
    rows = [
        classify("hl_orderflow_tick", {"running": True, "age_sec": 30}),         # fresh
        classify("options_uoa", {"running": True, "age_sec": 5000}),             # stale (>3600)
        classify("cross_venue_skew_tick", {"running": False, "age_sec": 1}),     # dead
    ]
    s = fleet_summary(rows)
    assert s["ok"] is False
    assert s["worst_verdict"] == "dead"
    assert s["counts"] == {"fresh": 1, "stale": 1, "dead": 1, "stuck": 0}
    assert s["collectors"][0]["verdict"] == "dead"       # 나쁜 것 먼저 정렬


def test_fleet_summary_all_fresh_ok():
    rows = [classify("hl_orderflow_tick", {"running": True, "age_sec": 10})]
    s = fleet_summary(rows)
    assert s["ok"] is True and s["worst_verdict"] == "fresh"


def test_classify_stuck_far_past_threshold():
    # hl_orderflow_tick 임계 300s, STUCK_MULTIPLIER=4 → 1200s 넘으면 stuck
    r = classify("hl_orderflow_tick", {"running": True, "age_sec": 1300})
    assert r["verdict"] == "stuck"


def test_classify_stale_not_yet_stuck():
    r = classify("hl_orderflow_tick", {"running": True, "age_sec": 1199})
    assert r["verdict"] == "stale"


def test_stuck_ranks_worse_than_stale_but_better_than_dead():
    rows = [
        classify("hl_orderflow_tick", {"running": True, "age_sec": 1300}),   # stuck
        classify("options_uoa", {"running": True, "age_sec": 5000}),         # stale
        classify("cross_venue_skew_tick", {"running": False, "age_sec": 1}), # dead
    ]
    s = fleet_summary(rows)
    assert s["worst_verdict"] == "dead"
    assert [c["verdict"] for c in s["collectors"]] == ["dead", "stuck", "stale"]
    assert s["ok"] is False


def test_classify_flapping_flag_from_restart_count():
    fresh_not_flapping = classify("hl_orderflow_tick", {"running": True, "age_sec": 10}, restart_count_24h=2)
    fresh_flapping = classify("hl_orderflow_tick", {"running": True, "age_sec": 10}, restart_count_24h=3)
    assert fresh_not_flapping["flapping"] is False
    assert fresh_flapping["flapping"] is True
    assert fresh_flapping["restart_count_24h"] == 3


def test_fleet_summary_not_ok_when_flapping_even_if_fresh():
    rows = [classify("hl_orderflow_tick", {"running": True, "age_sec": 10}, restart_count_24h=5)]
    s = fleet_summary(rows)
    assert s["ok"] is False
    assert s["worst_verdict"] == "fresh"       # verdict 자체는 그대로


def test_count_restarts_by_key_windows_and_groups():
    now = 1_000_000.0
    events = [
        {"key": "hl_orderflow_tick", "ts": now - 100},
        {"key": "hl_orderflow_tick", "ts": now - 200},
        {"key": "hl_orderflow_tick", "ts": now - 90_000},   # 24h 밖(>86400s)
        {"key": "cross_venue_skew_tick", "ts": now - 300},
    ]
    counts = count_restarts_by_key(events, now)
    assert counts == {"hl_orderflow_tick": 2, "cross_venue_skew_tick": 1}


def test_classify_disk_tiers():
    assert classify_disk(free_gb=50.0, total_gb=228.0)["verdict"] == "ok"
    assert classify_disk(free_gb=15.0, total_gb=228.0)["verdict"] == "warn"
    assert classify_disk(free_gb=5.0, total_gb=228.0)["verdict"] == "critical"
