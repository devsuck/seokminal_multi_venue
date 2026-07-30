"""방치 vitest 프로세스 감시 판정(순수) 유닛테스트."""
from ops.dev_process_watchdog import classify_processes, parse_etime


def test_parse_etime_mm_ss():
    assert parse_etime("05:56") == 356


def test_parse_etime_hh_mm_ss():
    assert parse_etime("01:02:03") == 3723


def test_parse_etime_days():
    assert parse_etime("2-01:00:20") == 2 * 86400 + 3600 + 20


def test_classify_ignores_short_lived_vitest():
    rows = [{"pid": 1, "etime": "05:00",
             "command": "node .../vitest/dist/workers/forks.js"}]
    assert classify_processes(rows) == []


def test_classify_flags_long_running_vitest():
    rows = [{"pid": 1, "etime": "09:12:00",
             "command": "node .../vitest/dist/workers/forks.js"}]
    targets = classify_processes(rows)
    assert [t["pid"] for t in targets] == [1]


def test_classify_ignores_uvicorn_even_if_long_running():
    rows = [{"pid": 2, "etime": "5-00:00:00",
             "command": "/Library/.../Python -m uvicorn api_server.main:app"}]
    assert classify_processes(rows) == []


def test_classify_ignores_collector_process_even_if_long_running():
    rows = [{"pid": 3, "etime": "5-09:15:40",
             "command": "python -m research.run_cross_venue_skew_collect"}]
    assert classify_processes(rows) == []


def test_classify_ignores_next_dev_server():
    rows = [{"pid": 4, "etime": "10-00:00:00",
             "command": "node .../next dev"}]
    assert classify_processes(rows) == []


def test_classify_threshold_boundary_not_yet():
    rows = [{"pid": 1, "etime": "29:59",
             "command": "node .../vitest/dist/workers/forks.js"}]
    assert classify_processes(rows, max_elapsed_s=1800.0) == []


def test_classify_threshold_boundary_exactly():
    rows = [{"pid": 1, "etime": "30:00",
             "command": "node .../vitest/dist/workers/forks.js"}]
    targets = classify_processes(rows, max_elapsed_s=1800.0)
    assert [t["pid"] for t in targets] == [1]
