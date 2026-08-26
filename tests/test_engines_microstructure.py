import gzip
import json as _json

import pytest

from research.autoresearch import engines_microstructure as em


def _write_orderflow_day(dirpath, symbol, date, rows):
    dirpath.mkdir(parents=True, exist_ok=True)
    path = dirpath / f"{symbol}_{date}.jsonl"
    with path.open("w") as f:
        for r in rows:
            f.write(_json.dumps(r) + "\n")


def test_assemble_evidence_contract_shape():
    pv = {"p_value": 0.002, "percentile": 99.8, "n_random": 500, "random_beating": 1, "random_median": -0.0001}
    ev = em._assemble_evidence(net=0.001, median=0.0009, wf1=0.0011, wf2=0.0009,
                                pv=pv, net_stress=0.0005, n=40, n_variants=10)
    assert ev["n"] == 40
    assert ev["net"] == 0.001
    assert ev["net_stress"] == 0.0005
    assert ev["percentile"] == 99.8
    assert ev["p"] == 0.002
    assert ev["wf_first"] == 0.0011
    assert ev["wf_second"] == 0.0009
    assert ev["top_tail_share"] is None
    assert ev["_spec"] == {"market": "CRYPTO", "family": "microstructure", "n_variants": 10}
    assert ev["evidence"]["random_baseline"] == "passed"
    assert ev["evidence"]["walk_forward"] == "passed"
    assert ev["evidence"]["cost_stress"] == "passed"
    assert ev["evidence"]["survivorship"] == "na"
    assert ev["evidence"]["multiple_testing"] == "passed"
    assert ev["evidence"]["lookahead"] == "passed"


def test_assemble_evidence_fails_when_wf_second_negative():
    pv = {"p_value": 0.002, "percentile": 99.8, "n_random": 500, "random_beating": 1, "random_median": -0.0001}
    ev = em._assemble_evidence(net=0.001, median=0.0009, wf1=0.0011, wf2=-0.0002,
                                pv=pv, net_stress=0.0005, n=40, n_variants=10)
    assert ev["evidence"]["walk_forward"] == "failed"


def test_assemble_evidence_fails_when_stress_flips_negative():
    pv = {"p_value": 0.002, "percentile": 99.8, "n_random": 500, "random_beating": 1, "random_median": -0.0001}
    ev = em._assemble_evidence(net=0.001, median=0.0009, wf1=0.0011, wf2=0.0009,
                                pv=pv, net_stress=-0.0001, n=40, n_variants=10)
    assert ev["evidence"]["cost_stress"] == "failed"


def test_series_evidence_none_below_min_days():
    signs = [1.0] * 10
    outcomes = [0.01] * 10
    assert em._series_evidence(signs, outcomes, em.COST_BASE_BPS, em.COST_STRESS_BPS, n_variants=4) is None


def test_series_evidence_strong_signal_scores_high_percentile():
    # signs alternate, outcomes perfectly track sign*const -> near-unbeatable vs shuffled-outcome permutations
    n = 40
    signs = [1.0 if i % 2 == 0 else -1.0 for i in range(n)]
    outcomes = [0.02 if s > 0 else -0.02 for s in signs]
    ev = em._series_evidence(signs, outcomes, em.COST_BASE_BPS, em.COST_STRESS_BPS, n_variants=4)
    assert ev is not None
    assert ev["n"] == n
    assert ev["net"] > 0
    assert ev["percentile"] == 100.0
    assert ev["evidence"]["random_baseline"] == "passed"
    assert ev["evidence"]["walk_forward"] == "passed"


def test_event_pnl_evidence_splits_chronologically():
    pnls = [1.0] * 10 + [2.0] * 10  # first half mean 1.0, second half mean 2.0
    pv = {"p_value": 0.01, "percentile": 99.0, "n_random": 500, "random_beating": 5, "random_median": 0.1}
    ev = em._event_pnl_evidence(pnls, net_stress=0.5, pv=pv, n_variants=4)
    assert ev["n"] == 20
    assert ev["wf_first"] == 1.0
    assert ev["wf_second"] == 2.0
    assert ev["net"] == 1.5


def test_daily_ofi_and_price_aggregates_signed_size(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "_ORDERFLOW_DIR", tmp_path)
    _write_orderflow_day(tmp_path, "BTC", "2026-07-10", [
        {"ts": 1.0, "side": "buy", "size": 10.0, "price": 100.0},
        {"ts": 2.0, "side": "sell", "size": 4.0, "price": 101.0},
        {"ts": 3.0, "side": "buy", "size": 1.0, "price": 102.0},
    ])
    ofi, price = em._daily_ofi_and_price("BTC")
    assert ofi["2026-07-10"] == pytest.approx(7.0)
    assert price["2026-07-10"] == 102.0


def test_ofi_signs_outcomes_next_day_pairing(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "_ORDERFLOW_DIR", tmp_path)
    _write_orderflow_day(tmp_path, "BTC", "2026-07-10", [
        {"ts": 1.0, "side": "buy", "size": 10.0, "price": 100.0},
    ])
    _write_orderflow_day(tmp_path, "BTC", "2026-07-11", [
        {"ts": 1.0, "side": "sell", "size": 5.0, "price": 110.0},
    ])
    signs, outcomes = em._ofi_signs_outcomes("BTC")
    assert signs == [1.0]
    assert outcomes == [pytest.approx(0.10)]


def test_ofi_candidate_run_returns_none_with_no_data(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "_ORDERFLOW_DIR", tmp_path)
    cand = em._ofi_candidate("BTC", n_variants=4)
    assert cand.cid == "micro_ofi_momentum_BTC"
    assert cand.category == "microstructure"
    assert cand.direction == "research"
    assert cand.run() is None


from research.hypotheses import cross_venue_skew as cvs


def _write_skew_day(dirpath, venue, coin, date, rows):
    dirpath.mkdir(parents=True, exist_ok=True)
    path = dirpath / f"{venue}_{coin}_{date}.jsonl"
    with path.open("w") as f:
        for r in rows:
            f.write(_json.dumps(r) + "\n")


def test_daily_mid_computes_utc_date_and_mean(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "_SKEW_DIR", tmp_path)
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    # ts=1752105600 -> 2025-07-10T00:00:00Z-ish; use two snapshots same UTC date
    ts0 = 1752105600.0
    _write_skew_day(tmp_path, "binance", "BTC", "2025-07-10", [
        {"ts": ts0, "bids": [{"price": 100.0, "size": 1.0}], "asks": [{"price": 102.0, "size": 1.0}]},
        {"ts": ts0 + 60.0, "bids": [{"price": 104.0, "size": 1.0}], "asks": [{"price": 106.0, "size": 1.0}]},
    ])
    mids = em._daily_mid("binance", "BTC")
    assert set(mids.keys()) == {"2025-07-10"}
    assert mids["2025-07-10"] == pytest.approx((101.0 + 105.0) / 2.0)


def test_basis_signs_outcomes_reversion_direction(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "_SKEW_DIR", tmp_path)
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    ts0 = 1752105600.0
    ts1 = ts0 + 86400.0
    # day0: binance mid=110, okx mid=100 -> basis=+0.10 (binance rich)
    _write_skew_day(tmp_path, "binance", "BTC", "2025-07-10", [
        {"ts": ts0, "bids": [{"price": 109.0, "size": 1.0}], "asks": [{"price": 111.0, "size": 1.0}]}])
    _write_skew_day(tmp_path, "okx", "BTC", "2025-07-10", [
        {"ts": ts0, "bids": [{"price": 99.0, "size": 1.0}], "asks": [{"price": 101.0, "size": 1.0}]}])
    # day1: basis shrinks to +0.02 -> reversion bet (sign=+1) profits
    _write_skew_day(tmp_path, "binance", "BTC", "2025-07-11", [
        {"ts": ts1, "bids": [{"price": 101.0, "size": 1.0}], "asks": [{"price": 103.0, "size": 1.0}]}])
    _write_skew_day(tmp_path, "okx", "BTC", "2025-07-11", [
        {"ts": ts1, "bids": [{"price": 99.0, "size": 1.0}], "asks": [{"price": 101.0, "size": 1.0}]}])
    signs, outcomes, n_overlap = em._basis_signs_outcomes("BTC", "binance", "okx")
    assert n_overlap == 2
    assert signs == [1.0]
    assert outcomes[0] > 0  # basis shrank -> sign*outcome positive -> reversion profit


def test_select_basis_pairs_filters_by_min_days(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "_SKEW_DIR", tmp_path)
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    # no data at all -> every pair has n_overlap=0 < _MIN_DAYS -> empty selection
    assert em._select_basis_pairs() == []


def test_select_basis_pairs_real_data_filters_and_truncates(monkeypatch):
    """_basis_signs_outcomes mocked per (coin, venue_a, venue_b) so the test isolates
    _select_basis_pairs' filter+truncate logic from date-overlap arithmetic.
    One pair sits at the exact n_overlap==_MIN_DAYS boundary but len(signs) < _MIN_DAYS
    (the off-by-one Finding #1 regression case) and must be excluded; the remaining 5
    pairs qualify, proving both the len(signs) filter and the top-4 truncation."""
    fixtures = {
        ("BTC", "binance", "okx"): (29, 30),   # n_overlap=30 (boundary) but signs=29 -> EXCLUDED
        ("BTC", "binance", "hl"): (37, 37),    # qualifies, rank 3
        ("BTC", "okx", "hl"): (43, 43),        # qualifies, rank 1 (top)
        ("ETH", "binance", "okx"): (36, 36),   # qualifies, rank 4
        ("ETH", "binance", "hl"): (40, 40),    # qualifies, rank 2
        ("ETH", "okx", "hl"): (32, 32),        # qualifies, rank 5 -> truncated by top-4 cap
    }

    def fake_signs_outcomes(coin, venue_a, venue_b):
        n_signs, n_overlap = fixtures[(coin, venue_a, venue_b)]
        return [1.0] * n_signs, [0.001] * n_signs, n_overlap

    monkeypatch.setattr(em, "_basis_signs_outcomes", fake_signs_outcomes)

    selected = em._select_basis_pairs()
    assert len(selected) == 4
    signs_counts = [sel[0] for sel in selected]
    assert signs_counts == [43, 40, 37, 36]
    selected_pairs = {(coin, va, vb) for _, coin, va, vb, _, _ in selected}
    assert ("BTC", "binance", "okx") not in selected_pairs  # boundary exclusion
    assert ("ETH", "okx", "hl") not in selected_pairs       # truncated (5th-best)


def test_basis_candidates_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "_SKEW_DIR", tmp_path)
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    # Use realistic selection output from _select_basis_pairs:
    # tuple is (len(signs), coin, venue_a, venue_b, signs, outcomes)
    # where len(signs) is the usable pair count (not n_overlap)
    selection = [(35, "BTC", "binance", "okx", [1.0] * 35, [0.001] * 35)]
    cands = em._basis_candidates(selection, n_variants=4)
    assert len(cands) == 1
    assert cands[0].cid == "micro_basis_reversion_BTC_binance_okx"
    assert cands[0].category == "microstructure"
    assert cands[0].direction == "research"
    result = cands[0].run()
    assert result is not None
    assert result["n"] == 35


def test_absorption_result_none_with_no_ticks(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "_ORDERFLOW_DIR", tmp_path)
    assert em._absorption_result("BTC") is None


def test_absorption_candidate_shape_and_none_run(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "_ORDERFLOW_DIR", tmp_path)
    cand = em._absorption_candidate("BTC", n_variants=4)
    assert cand.cid == "micro_absorption_momentum_BTC"
    assert cand.category == "microstructure"
    assert cand.direction == "research"
    assert cand.run() is None
