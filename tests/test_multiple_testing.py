"""BH-FDR 다중검정 보정 테스트."""
from __future__ import annotations

from research.validation.multiple_testing import benjamini_hochberg, prob_at_least_one_fp


def test_bh_all_insignificant():
    r = benjamini_hochberg([0.4, 0.6, 0.8, 0.9], alpha=0.1)
    assert r["n_survivors"] == 0
    assert all(s is False for s in r["survivors"])


def test_bh_one_strong_survives():
    # 아주 작은 p 하나 + 나머지 큰 값
    r = benjamini_hochberg([0.001, 0.5, 0.6, 0.7], alpha=0.1)
    assert r["n_survivors"] >= 1
    assert r["survivors"][0] is True


def test_bh_lone_005_in_30_does_not_survive():
    # 30개 중 하나만 0.048 → BH 통과 못함(노이즈)
    pvals = [0.048] + [0.5] * 29
    r = benjamini_hochberg(pvals, alpha=0.1)
    assert r["n_survivors"] == 0  # 0.048 > (1/30)*0.1=0.0033


def test_bh_preserves_order_mask():
    pvals = [0.9, 0.001, 0.8]
    r = benjamini_hochberg(pvals, alpha=0.1)
    assert r["survivors"][1] is True and r["survivors"][0] is False


def test_prob_fp_grows():
    assert abs(prob_at_least_one_fp(1, 0.05) - 0.05) < 1e-9
    assert 0.78 < prob_at_least_one_fp(30, 0.05) < 0.80
