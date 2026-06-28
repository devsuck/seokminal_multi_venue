import statistics
import pytest

from beta_analysis.beta import beta_for_pair


def test_beta_calculation_perfect_correlation():
    """
    Two returns series with identical varying values.
    Expected: beta ≈ 1.0, correlation ≈ 1.0.
    """
    inst_returns = [0.01, -0.01, 0.02, -0.02]
    bench_returns = [0.01, -0.01, 0.02, -0.02]

    expected_covariance = statistics.covariance(inst_returns, bench_returns)
    expected_variance = statistics.variance(bench_returns)
    expected_beta = expected_covariance / expected_variance
    expected_correlation = statistics.correlation(inst_returns, bench_returns)

    assert abs(expected_beta - 1.0) < 0.001
    assert abs(expected_correlation - 1.0) < 0.001


def test_beta_calculation_scaled_returns():
    """
    Instrument returns are 2x benchmark returns.
    Expected: beta ≈ 2.0, correlation ≈ 1.0.
    """
    bench_returns = [0.01, -0.01, 0.02, -0.02]
    inst_returns = [0.02, -0.02, 0.04, -0.04]

    expected_covariance = statistics.covariance(inst_returns, bench_returns)
    expected_variance = statistics.variance(bench_returns)
    expected_beta = expected_covariance / expected_variance

    assert abs(expected_beta - 2.0) < 0.001
