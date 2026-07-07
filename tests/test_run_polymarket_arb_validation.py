import json

from research.run_polymarket_arb_validation import evaluate_runs, find_opportunity_runs, load_snapshots


def _row(condition_id, ts, is_opportunity, sum_ask=0.97, yes_ask_size=50.0, no_ask_size=40.0):
    return {
        "ts": ts, "condition_id": condition_id, "question": f"q-{condition_id}",
        "yes_bid": 0.45, "yes_ask": sum_ask / 2, "yes_ask_size": yes_ask_size,
        "no_bid": 0.45, "no_ask": sum_ask / 2, "no_ask_size": no_ask_size,
        "sum_ask": sum_ask, "liquidity": 9000.0, "is_opportunity": is_opportunity,
    }


def test_load_snapshots_reads_all_jsonl_files_in_dir(tmp_path):
    (tmp_path / "2026-07-01.jsonl").write_text(
        json.dumps(_row("a", "2026-07-01T00:00:00+00:00", True)) + "\n"
    )
    (tmp_path / "2026-07-02.jsonl").write_text(
        json.dumps(_row("a", "2026-07-02T00:00:00+00:00", False)) + "\n"
    )
    rows = load_snapshots(tmp_path)
    assert len(rows) == 2


def test_find_opportunity_runs_groups_consecutive_ticks_per_market():
    rows = [
        _row("a", "2026-07-01T00:00:00+00:00", True, sum_ask=0.95),
        _row("a", "2026-07-01T00:00:10+00:00", True, sum_ask=0.93),
        _row("a", "2026-07-01T00:00:20+00:00", False),
        _row("a", "2026-07-01T00:00:30+00:00", True, sum_ask=0.98),
    ]
    runs = find_opportunity_runs(rows)
    assert len(runs) == 2
    first = runs[0]
    assert first["condition_id"] == "a"
    assert first["ticks"] == 2
    assert first["duration_sec"] == 10.0
    assert first["min_sum_ask"] == 0.93
    second = runs[1]
    assert second["ticks"] == 1
    assert second["duration_sec"] == 0.0


def test_find_opportunity_runs_computes_capturable_margin():
    rows = [_row("a", "2026-07-01T00:00:00+00:00", True, sum_ask=0.90,
                  yes_ask_size=30.0, no_ask_size=50.0)]
    runs = find_opportunity_runs(rows)
    # capturable size = min(30, 50) = 30, margin = 30 * (1 - 0.90) = 3.0
    assert runs[0]["max_capturable_margin_usd"] == 3.0


def test_find_opportunity_runs_ignores_non_opportunity_ticks():
    rows = [_row("a", "2026-07-01T00:00:00+00:00", False)]
    assert find_opportunity_runs(rows) == []


def test_evaluate_runs_rejects_when_no_run_meets_min_duration():
    runs = [{"condition_id": "a", "start_ts": "2026-07-01T00:00:00+00:00",
             "end_ts": "2026-07-01T00:00:00+00:00", "duration_sec": 0.0,
             "min_sum_ask": 0.95, "ticks": 1, "max_capturable_margin_usd": 1.0}]
    report = evaluate_runs(runs, min_duration_sec=3.0)
    assert report["verdict"] == "REJECT_NO_PERSISTENT_RUNS"
    assert report["persistent_runs"] == 0


def test_evaluate_runs_candidate_when_persistent_runs_exist():
    runs = [
        {"condition_id": "a", "start_ts": "2026-07-01T00:00:00+00:00",
         "end_ts": "2026-07-01T00:00:10+00:00", "duration_sec": 10.0,
         "min_sum_ask": 0.93, "ticks": 2, "max_capturable_margin_usd": 3.0},
        {"condition_id": "b", "start_ts": "2026-07-03T00:00:00+00:00",
         "end_ts": "2026-07-03T00:00:20+00:00", "duration_sec": 20.0,
         "min_sum_ask": 0.90, "ticks": 3, "max_capturable_margin_usd": 5.0},
    ]
    report = evaluate_runs(runs, min_duration_sec=3.0)
    assert report["verdict"] == "CANDIDATE"
    assert report["persistent_runs"] == 2
    assert report["best_min_sum_ask"] == 0.90
    assert report["runs_per_week"] > 0


def test_find_opportunity_runs_splits_on_gap_exceeding_max_gap_sec():
    rows = [
        _row("a", "2026-07-01T00:00:00+00:00", True, sum_ask=0.95),
        _row("a", "2026-07-01T00:05:00+00:00", True, sum_ask=0.93),  # 300s gap, no False row between
    ]
    runs = find_opportunity_runs(rows, max_gap_sec=30.0)
    assert len(runs) == 2
    assert runs[0]["ticks"] == 1
    assert runs[1]["ticks"] == 1


def test_evaluate_runs_rejects_when_margin_not_positive():
    runs = [{"condition_id": "a", "start_ts": "2026-07-01T00:00:00+00:00",
             "end_ts": "2026-07-01T00:00:10+00:00", "duration_sec": 10.0,
             "min_sum_ask": 0.999, "ticks": 2, "max_capturable_margin_usd": 0.0}]
    report = evaluate_runs(runs, min_duration_sec=3.0, min_margin_usd=0.0)
    assert report["verdict"] == "REJECT_NO_POSITIVE_MARGIN"
    assert report["persistent_runs"] == 1
