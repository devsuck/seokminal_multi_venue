from research.polymarket_arb.detector import evaluate_snapshot


def test_evaluate_snapshot_detects_opportunity_below_buffer():
    r = evaluate_snapshot(yes_ask=0.45, no_ask=0.50)
    assert r["sum_ask"] == 0.95
    assert r["is_opportunity"] is True


def test_evaluate_snapshot_no_opportunity_above_one():
    r = evaluate_snapshot(yes_ask=0.52, no_ask=0.50)
    assert r["sum_ask"] == 1.02
    assert r["is_opportunity"] is False


def test_evaluate_snapshot_respects_fee_buffer_boundary():
    # sum_ask=0.99, buffer=1% -> threshold=0.99, 0.99 < 0.99 is False (경계는 기회 아님)
    r = evaluate_snapshot(yes_ask=0.49, no_ask=0.50, fee_buffer=0.01)
    assert r["sum_ask"] == 0.99
    assert r["is_opportunity"] is False


def test_evaluate_snapshot_zero_buffer_only_needs_under_one():
    r = evaluate_snapshot(yes_ask=0.499, no_ask=0.50, fee_buffer=0.0)
    assert r["is_opportunity"] is True
