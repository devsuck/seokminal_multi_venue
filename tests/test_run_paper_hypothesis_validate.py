from unittest.mock import patch

import research.run_paper_hypothesis_validate as v


def _fake_result(name, pval, total_pnl=10.0):
    return {
        "name": name, "verdict": "INCONCLUSIVE — 보류",
        "pooled": {"empirical_p_value": pval, "total_pnl": total_pnl,
                   "percentile_vs_random": 50.0, "num_trades": 5,
                   "expectancy": 1.0, "profit_factor": 1.1, "win_rate": 0.5,
                   "random_median": 0.0},
    }


def test_discover_hypotheses_loads_modules_with_required_symbols(tmp_path):
    good = tmp_path / "good.py"
    good.write_text(
        'NAME = "good"\nDESCRIPTION = "d"\n'
        'def signal_fn(ohlc, feat, aux, params):\n    return {"entry": [], "eligible": []}\n'
    )
    bad = tmp_path / "bad.py"
    bad.write_text("X = 1\n")
    with patch.object(v, "_HYPOTHESES_DIR", str(tmp_path)):
        found = v.discover_hypotheses()
    assert [h["name"] for h in found] == ["good"]
    assert callable(found[0]["signal_fn"])


def test_main_with_no_hypotheses_returns_empty_results():
    with patch.object(v, "discover_hypotheses", return_value=[]):
        result = v.main()
    assert result["results"] == []
    assert result["bh_fdr"]["n_survivors"] == 0
    assert result["bh_fdr"]["survivors"] == []


def test_main_pools_pvalues_across_hypotheses_and_runs_bh_fdr():
    fake_hyps = [
        {"path": "a.py", "name": "paper_a", "desc": "d", "signal_fn": lambda *a: None},
        {"path": "b.py", "name": "paper_b", "desc": "d", "signal_fn": lambda *a: None},
    ]
    fake_results = [_fake_result("paper_a", 0.01), _fake_result("paper_b", 0.9)]
    with patch.object(v, "discover_hypotheses", return_value=fake_hyps), \
         patch.object(v, "run_universe", side_effect=fake_results):
        result = v.main()
    assert [r["name"] for r in result["results"]] == ["paper_a", "paper_b"]
    assert result["results"][0]["verdict"] == "INCONCLUSIVE — 보류"
    assert result["bh_fdr"]["names"] == ["paper_a", "paper_b"]


def test_main_skips_none_pvalue_when_pooling():
    fake_hyps = [{"path": "a.py", "name": "paper_a", "desc": "d", "signal_fn": lambda *a: None}]
    fake_results = [_fake_result("paper_a", None)]
    with patch.object(v, "discover_hypotheses", return_value=fake_hyps), \
         patch.object(v, "run_universe", side_effect=fake_results):
        result = v.main()
    assert result["bh_fdr"]["names"] == []
    assert result["bh_fdr"]["n_survivors"] == 0
