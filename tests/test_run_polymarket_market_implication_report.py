from research.run_polymarket_market_implication_report import compute_report


def _violation(pattern_type, resolved=True, pnl=0.1):
    v = {"pattern_type": pattern_type, "resolved": resolved}
    if resolved:
        v["pnl_per_share"] = pnl
    return v


def test_compute_report_splits_by_pattern_type():
    violations = [_violation("A", pnl=0.1), _violation("B", pnl=-0.2)]
    report = compute_report(violations)
    assert report["A"]["detected"] == 1
    assert report["B"]["detected"] == 1
    assert report["A"]["mean_pnl"] == 0.1
    assert report["B"]["mean_pnl"] == -0.2


def test_compute_report_ignores_unresolved_for_pnl():
    violations = [_violation("A", resolved=False), _violation("A", pnl=0.2)]
    report = compute_report(violations)
    assert report["A"]["detected"] == 2
    assert report["A"]["resolved"] == 1
    assert report["A"]["mean_pnl"] == 0.2


def test_compute_report_win_rate():
    violations = [_violation("A", pnl=0.1), _violation("A", pnl=-0.1), _violation("A", pnl=0.05)]
    report = compute_report(violations)
    assert report["A"]["win_rate"] == round(2 / 3, 4)


def test_compute_report_verdict_insufficient_sample_below_min_n():
    violations = [_violation("A", pnl=0.1)]
    report = compute_report(violations)
    assert report["A"]["verdict"] == "insufficient_sample"


def test_compute_report_no_data_returns_none_stats():
    report = compute_report([])
    assert report["A"] == {
        "detected": 0, "resolved": 0, "mean_pnl": None, "win_rate": None,
        "verdict": "insufficient_sample",
    }
