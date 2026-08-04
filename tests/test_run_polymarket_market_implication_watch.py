import json
from unittest.mock import patch

import research.run_polymarket_market_implication_watch as watch


def _pair(pattern_type="A", direction="a_implies_b"):
    return {
        "pair_key": "c1|c2", "condition_id_a": "c1", "condition_id_b": "c2",
        "token_id_a": "tok_a", "token_id_b": "tok_b",
        "pattern_type": pattern_type, "direction": direction,
    }


def test_check_pair_returns_none_when_book_missing():
    assert watch.check_pair(_pair(), lambda tid: None) is None


def test_check_pair_returns_none_when_no_violation():
    books = {"tok_a": {"best_bid": 0.39, "best_ask": 0.41}, "tok_b": {"best_bid": 0.49, "best_ask": 0.51}}
    result = watch.check_pair(_pair(), lambda tid: books[tid])
    assert result is None  # implying(A) mid=0.40 <= implied(B) mid=0.50, 위반 아님


def test_check_pair_detects_violation_past_cost():
    books = {"tok_a": {"best_bid": 0.69, "best_ask": 0.71}, "tok_b": {"best_bid": 0.49, "best_ask": 0.51}}
    result = watch.check_pair(_pair(), lambda tid: books[tid])
    assert result is not None
    assert result["pattern_type"] == "A"
    assert result["pair_key"] == "c1|c2"
    assert result["resolved"] is False


def test_check_pair_zero_width_spread_not_replaced_by_fallback():
    # tok_a: best_bid == best_ask -> spread_bps_from_book returns 0.0 (falsy but valid).
    # Must NOT be replaced by POLYMARKET_SPREAD_BPS(200) fallback.
    books = {"tok_a": {"best_bid": 0.70, "best_ask": 0.70}, "tok_b": {"best_bid": 0.49, "best_ask": 0.51}}
    result = watch.check_pair(_pair(), lambda tid: books[tid])
    assert result is not None
    # cost_frac = (0bps/2 + 400bps/2) / 10000 = 0.02, NOT (200/2 + 400/2)/10000 = 0.03
    assert result["cost_frac"] == 0.02


def test_run_once_appends_detected_violations(tmp_path):
    with patch.object(watch, "_DATA_DIR", tmp_path):
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "pairs.jsonl").write_text(json.dumps(_pair()) + "\n")
        books = {"tok_a": {"best_bid": 0.69, "best_ask": 0.71}, "tok_b": {"best_bid": 0.49, "best_ask": 0.51}}
        detected = watch.run_once(get_book_fn=lambda tid: books[tid])
        saved = watch.load_violations()
    assert len(detected) == 1
    assert len(saved) == 1
    assert saved[0]["pattern_type"] == "A"


def test_run_once_does_not_relog_still_open_violation(tmp_path):
    with patch.object(watch, "_DATA_DIR", tmp_path):
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "pairs.jsonl").write_text(json.dumps(_pair()) + "\n")
        books = {"tok_a": {"best_bid": 0.69, "best_ask": 0.71}, "tok_b": {"best_bid": 0.49, "best_ask": 0.51}}
        watch.run_once(get_book_fn=lambda tid: books[tid])
        watch.run_once(get_book_fn=lambda tid: books[tid])
        saved = watch.load_violations()
    unresolved = [v for v in saved if not v.get("resolved")]
    assert len(unresolved) == 1


def test_resolve_pnl_returns_none_when_not_both_closed():
    violation = {"pattern_type": "A", "direction": "a_implies_b", "price_a": 0.70, "price_b": 0.50, "cost_frac": 0.0}
    market_a = {"closed": True, "yes_price": 1.0}
    market_b = {"closed": False, "yes_price": 0.0}
    assert watch.resolve_pnl(violation, market_a, market_b) is None


def test_resolve_pnl_computes_pnl_pattern_a():
    violation = {"pattern_type": "A", "direction": "a_implies_b", "price_a": 0.70, "price_b": 0.50, "cost_frac": 0.05}
    market_a = {"closed": True, "yes_price": 1.0}
    market_b = {"closed": True, "yes_price": 1.0}
    result = watch.resolve_pnl(violation, market_a, market_b)
    # (0.70-1.0) + (1.0-0.50) - 0.05 = 0.15
    assert result["pnl_per_share"] == 0.15
    assert result["resolved"] is True


def test_resolve_pnl_computes_pnl_pattern_b():
    violation = {"pattern_type": "B", "price_a": 0.60, "price_b": 0.55, "cost_frac": 0.05}
    market_a = {"closed": True, "yes_price": 1.0}
    market_b = {"closed": True, "yes_price": 0.0}
    result = watch.resolve_pnl(violation, market_a, market_b)
    # (0.60-1.0) + (0.55-0.0) - 0.05 = 0.10
    assert result["pnl_per_share"] == 0.10


def test_resolve_pending_updates_violations_file(tmp_path):
    violation = {
        "pattern_type": "A", "direction": "a_implies_b", "price_a": 0.70, "price_b": 0.50,
        "cost_frac": 0.05, "condition_id_a": "c1", "condition_id_b": "c2", "resolved": False,
    }
    with patch.object(watch, "_DATA_DIR", tmp_path):
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "violations.jsonl").write_text(json.dumps(violation) + "\n")

        def get_market_fn(cid):
            return {"closed": True, "yes_price": 1.0}

        updated_count = watch.resolve_pending(get_market_fn=get_market_fn)
        saved = watch.load_violations()
    assert updated_count == 1
    assert saved[0]["resolved"] is True
    assert saved[0]["pnl_per_share"] == 0.15
