import pandas as pd

import research.run_mlb_specialist_validate as val


def _labels(n, win=True):
    ex = 1.0 if win else 0.0
    return pd.DataFrame([
        {"condition_id": f"m{i}", "side": "YES", "entry_price": 0.5,
         "exit_price": ex, "direction": 1.0, "forward_return": (ex - 0.5) / 0.5}
        for i in range(n)
    ])


def test_enumerate_variants_grid():
    # 3 지표 × 2 임계 × 2 N = 12
    variants = val.enumerate_variants()
    assert len(variants) == 12
    assert "pnl:majority:N5" in variants
    assert "roi:unanimous:N4" in variants


def test_compute_report_no_data():
    rep = val.compute_report({})
    assert rep["hypothesis"] == "mlb_specialist_consensus"
    assert rep["verdict"] == "no_data"
    assert rep["pools"][0]["n_tested"] == 0


def test_compute_report_blocked_below_min_events():
    rep = val.compute_report({"pnl:majority:N5": _labels(3)})
    assert rep["variants"][0]["blocked"] is True
    assert rep["verdict"] == "no_data"  # 돌아간 변형 없음


def test_compute_report_single_pool_and_pvalue():
    rep = val.compute_report({
        "pnl:majority:N5": _labels(15, win=True),
        "roi:unanimous:N4": _labels(4),  # 미달 → blocked
    })
    assert len(rep["pools"]) == 1
    assert rep["pools"][0]["name"] == "mlb_specialist_consensus"
    done = [v for v in rep["variants"] if not v["blocked"]]
    assert len(done) == 1 and done[0]["n_events"] == 15
    assert done[0]["p_value"] is not None
    assert rep["pools"][0]["n_tested"] == 1
    assert rep["verdict"] in ("no_edge", "candidate")
