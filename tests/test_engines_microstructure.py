from research.autoresearch import engines_microstructure as em


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
